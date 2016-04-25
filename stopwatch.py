"""StopWatch - library for adding timers and tags in your code for performance monitoring
https://github.com/dropbox/stopwatch

StopWatch operates on a notion of "spans" which represent scopes of code for which we
want to measure timing. Spans can be nested and placed inside loops for aggregation.

For example:
```
with sw.timer('root'):
    for i in range(50):
        with sw.timer('inner_task'):
            do_inner_task(i)
```

StopWatch requires a root scope which upon completion signifies the end of the round
of measurements. On a server, you might use a single request as your root scope.

StopWatch produces two kinds of reports.
1) Aggregated (see _reported_values).
2) Non-aggregated or "tracing" (see _reported_traces)

Aggregated reports have one value for each timer name. Great for averaging across
various root scopes / requests. The above example would have 2 reports.

Tracing reports keep one trace every time we enter a scope. The above example would
have 51 reports. This is great for digging into a data for a particular request,
or constructing waterfall graphs.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import contextlib
import random as insecure_random
import time

TraceAnnotation = collections.namedtuple('TraceKeyValueAnnotation', ['key', 'value', 'time'])
AggregatedReport = collections.namedtuple('AggregatedReport',
                                          ['aggregated_values', 'root_timer_data'])

class TimerData(object):
    """
    Simple object that wraps all data needed for a single timer span.
    The StopWatch object maintains a stack of these timers.
    """

    __slots__ = (
        'span_id',
        'name',
        'start_time',
        'end_time',
        'trace_annotations',
        'parent_span_id',
        'log_name',
    )

    def __init__(self, name, start_time, parent_name):
        # Generate new span id.
        self.span_id = '%032x' % insecure_random.getrandbits(128)
        self.name = name
        self.start_time = start_time
        self.end_time = None  # Gets filled in later
        self.trace_annotations = []
        self.parent_span_id = None  # Gets filled in at the end

        if parent_name:
            self.log_name = parent_name + '#' + name
        else:
            self.log_name = name

    def __repr__(self):
        return ('name=%r, span_id=%r start_time=%r end_time=%r annotations=%r, parent_span_id=%r,'
                'log_name=%r') % (
            self.name,
            self.span_id,
            self.start_time,
            self.end_time,
            self.trace_annotations,
            self.parent_span_id,
            self.log_name,
        )

def format_report(aggregated_report):
    """returns a pretty printed string of reported values"""
    values = aggregated_report.aggregated_values
    root_tr_data = aggregated_report.root_timer_data

    # fetch all values only for main stopwatch, ignore all the tags
    log_names = sorted(
        log_name for log_name in values if "+" not in log_name
    )
    if not log_names:
        return

    root = log_names[0]
    root_time_ms, root_count, bucket = values[root]
    buf = [
        "************************",
        "*** StopWatch Report ***",
        "************************",
        "%s    %.3fms (%.f%%)" % (root.ljust(20), root_time_ms / root_count, 100),
    ]
    for log_name in log_names[1:]:
        delta_ms, count, bucket = values[log_name]
        depth = log_name[len(root):].count("#")
        short_name = log_name[log_name.rfind("#") + 1:]
        bucket_name = bucket.name if bucket else ""

        buf.append("%s%s    %s %4d  %.3fms (%.f%%)" % (
            "    " * depth, bucket_name.ljust(12),
            short_name.ljust(20),
            count,
            delta_ms,
            delta_ms / root_time_ms * 100.0,
        ))

    annotations = sorted(ann.key for ann in root_tr_data.trace_annotations)
    buf.append("Annotations: %s" % (', '.join(annotations)))
    return "\n".join(buf)

def default_export_tracing(reported_traces):
    """Default implementation of non-aggregated trace logging"""
    pass

def default_export_aggregated_timers(aggregated_report):
    """Default implementation of aggregated timer logging"""
    pass

class StopWatch(object):
    """StopWatch - main class for storing timer stack and exposing timer functions/contextmanagers
    to the rest of the code"""

    def __init__(self,
                 strict_assert=True,
                 export_tracing_func=None,
                 export_aggregated_timers_func=None,
                 max_tracing_spans_for_path=1000,
                 min_tracing_milliseconds=3,
                 time_func=None):
        """
        Arguments:
          strict_assert: If True, assert on callsite misuse

          export_tracing_func: Function to log tracing data when stack empties

          export_aggregated_timers_func: Function to log timers when stack empties

          max_tracing_spans_for_path:
            The maximum number of spans to be logged per root scope for
            each unique path, so we make sure we aren't too excessive on the
            non-aggregated tracing report

          min_tracing_milliseconds:
            To reduce the large number of trivial spans, don't trace
            anything that takes less then this amount of time.

          time_func:
            Function which returns the current time in seconds. Defaults to time.time
        """

        self._timer_stack = []
        self._strict_assert = strict_assert
        self._export_tracing_func = export_tracing_func or default_export_tracing
        self._export_aggregated_timers_func = (
            export_aggregated_timers_func or default_export_aggregated_timers
        )
        self._time_func = time_func or time.time
        self.MAX_REQUEST_TRACING_SPANS_FOR_PATH = max_tracing_spans_for_path
        self.TRACING_MIN_NUM_MILLISECONDS = min_tracing_milliseconds
        self._last_trace_report = None
        self._last_aggregated_report = None

        self._reset()

    def _reset(self):
        """Reset internal timer stack when stack is cleared"""
        if self._timer_stack:
            assert not self._strict_assert, \
                "StopWatch reset() but stack not empty: %r" % (self._timer_stack,)
        self._reported_values = {}
        self._reported_traces = []
        self._root_annotations = []
        self._slow_annotations = {}

    ################
    # Public methods
    ################
    @contextlib.contextmanager
    def timer(self, name, bucket=None, start_time=None, end_time=None):
        """Context manager to wrap a stopwatch span"""
        self.start(name, start_time=start_time)
        try:
            yield
        except Exception as e:
            self.add_annotation('Exception', type(e).__name__, event_time=end_time)
            raise
        finally:
            self.end(name, end_time=end_time, bucket=bucket)

    def start(self, name, start_time=None):
        """Begin a stopwatch span
        Arguments:
            name:
                Name of the span to start
            start_time:
                Time (s) at which the scope began if set. (if not, use the current time)
        """
        if start_time is None:
            start_time = self._time_func()
        self._timer_stack.append(TimerData(
            name=name,
            start_time=start_time,
            parent_name=self._timer_stack[-1].log_name if self._timer_stack else None
        ))

    def end(self, name, end_time=None, bucket=None):
        """End a stopwatch span (must match latest started span)
        Arguments:
            name:
                Name of the scope that's completed. Must match the latest start()
            end_time:
                Time (s) at which the scope completed if set (if not use the current time)
            bucket:
                optional enum.Enum value describing bucket for additional reporting.
                For example, you might bucket all database queries together to see
                overall how much time is spent in databases.
        """
        if not self._timer_stack:
            assert not self._strict_assert, \
                "StopWatch end called but stack is empty: %s" % (name, )
            return

        if not end_time:
            end_time = self._time_func()

        tr_data = self._timer_stack.pop()
        assert (not self._strict_assert) or (tr_data.name == name), \
            "StopWatch end: %s, does not match latest start: %s" % (name, tr_data.name)

        # if the top element on stack doesn't match "name", need to pop off things from the stack
        # till it matches to maximally negate the possible inconsistencies
        while name != tr_data.name and self._timer_stack:
            tr_data = self._timer_stack.pop()

        tr_data.end_time = end_time
        log_name = tr_data.log_name

        # Aggregate into a single bucket per concatenated log name. This makes sure that code like
        # the following code stopwatches as expected.
        #
        # with StopWatch.timer('cool_loop_time'):
        #     for x in cool_loop:
        #         cool_stuff(x)
        tr_delta_ms = max((tr_data.end_time - tr_data.start_time) * 1000.0, 0.001)
        if log_name in self._reported_values:
            self._reported_values[log_name][0] += tr_delta_ms
            self._reported_values[log_name][1] += 1
        else:
            self._reported_values[log_name] = [tr_delta_ms, 1, bucket]

        # go through slow tags and add them as tags if enough time has passed
        if not self._timer_stack:
            tr_data.trace_annotations.extend(self._root_annotations)

            threshold_s = tr_delta_ms / 1000.0
            for slowtag, timelimit in self._slow_annotations.items():
                if timelimit <= threshold_s:
                    tr_data.trace_annotations.append(
                        TraceAnnotation(slowtag, '1', tr_data.end_time)
                    )

        if self._should_trace_timer(log_name, tr_delta_ms):
            tr_data.parent_span_id = self._timer_stack[-1].span_id if self._timer_stack else None
            self._reported_traces.append(tr_data)

        # report stopwatch values once the final 'end' call has been made
        if not self._timer_stack:
            agg_report = AggregatedReport(self._reported_values, tr_data)
            # Stash information internally
            self._last_trace_report = self._reported_traces
            self._last_aggregated_report = agg_report
            # Hit callbacks
            self._export_tracing_func(reported_traces=self._reported_traces)
            self._export_aggregated_timers_func(aggregated_report=agg_report)

            self._reset()  # Clear out stats to prevent duplicate reporting

    def add_annotation(self, key, value='1', event_time=None):
        """Add an annotation to the root scope. Note that we don't do this directly
        in order to support this case:

        if x > 1000:
            sw.add_annotation('big_work')
        with sw.timer('root'):
            do_work(x)

        """
        if event_time is None:
            event_time = self._time_func()
        self._root_annotations.append(
            TraceAnnotation(key, value, event_time)
        )

    def add_span_annotation(self, key, value='1', event_time=None):
        """Add an annotation to the current scope"""
        if event_time is None:
            event_time = self._time_func()
        self._timer_stack[-1].trace_annotations.append(
            TraceAnnotation(key, value, event_time)
        )

    def add_slow_annotation(self, tag, timelimit):
        """add annotation that will only be used if root scope takes longer than
        timelimit amount of seconds
        Arguments:
            tag: String tag name for the slowtag
            timelimit: Lower bound for the root scope after which tag is applied
        """
        self._slow_annotations[tag] = timelimit

    def get_last_trace_report(self):
        """Returns the last trace report from when the last root_scope completed"""
        return self._last_trace_report

    def get_last_aggregated_report(self):
        """Returns the last aggregated report and tags as a 2-tuple"""
        return self._last_aggregated_report

    def format_last_report(self):
        """Return formatted report from the last aggregated report. Simply calls
        format_last_report() on the get_last_aggregated_report()"""
        return format_report(self._last_aggregated_report)

    #################
    # Private methods
    #################

    def _should_trace_timer(self, log_name, delta_ms):
        """
        Helper method to determine if we should log the message or not.
        """
        if delta_ms < self.TRACING_MIN_NUM_MILLISECONDS:
            return False

        # Check if we have logged too many spans with the same full path already.
        # If yes, we should stop logging so we don't overload. E.g. if someone
        # is making for loop with 50k stopwatches, we will log only the first
        # MAX_REQUEST_TRACING_SPANS_FOR_PATH spans.

        return bool(log_name not in self._reported_values or
                    self._reported_values[log_name][1] <= self.MAX_REQUEST_TRACING_SPANS_FOR_PATH)
