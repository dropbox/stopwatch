"""StopWatch - library for adding timers and tags in your code for performance monitoring

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
            self.log_name = "{}#{}".format(parent_name, name)
        else:
            self.log_name = name

    def __repr__(self):
        return 'name=%r, span_id=%r start_time=%r end_time=%r annotations=%r, parent_span_id=%r,' \
               'log_name=%r' % (
            self.name,
            self.span_id,
            self.start_time,
            self.end_time,
            self.trace_annotations,
            self.parent_span_id,
            self.log_name,
        )

KeyValueAnnotation = collections.namedtuple('KeyValueAnnotation', ['key', 'value'])

def format_report(aggregated_report):
    """returns a pretty printed string of reported values"""
    reported_values, tags = aggregated_report

    # fetch all values only for main stopwatch, ignore all the tags
    log_names = sorted(
        log_name for log_name in reported_values if "+" not in log_name
    )
    if not log_names:
        return

    root = log_names[0]
    root_time, root_count, bucket = reported_values[root]
    buf = [
        "************************",
        "*** StopWatch Report ***",
        "************************",
        "%s    %.3f (%.f%%)" % (root.ljust(20), root_time / root_count, 100),
    ]
    for log_name in log_names[1:]:
        delta, count, bucket = reported_values[log_name]
        depth = log_name[len(root):].count("#")
        short_name = log_name[log_name.rfind("#") + 1:]
        bucket_name = bucket.name if bucket else ""

        buf.append("%s%s    %s %4d  %.3f (%.f%%)" % (
            "    " * depth, bucket_name.ljust(12),
            short_name.ljust(20),
            count,
            delta,
            delta / root_time * 100.0,
        ))
    buf.append("Tags: %s" % (', '.join(sorted(tags))))
    return "\n".join(buf)

def default_export_tracing(reported_traces):
    """Default implementation of non-aggregated trace logging"""
    pass

def default_export_aggregated_timers(reported_values, tags, total_time_ms, root_span_name):
    """Default implementation of aggregated timer logging"""
    pass

class StopWatch(object):
    """StopWatch - main class for storing timer stack and exposing timer functions/contextmanagers
    to the rest of the code"""

    def __init__(self,
                 strict_assert=True,
                 export_tracing_func=default_export_tracing,
                 export_aggregated_timers_func=default_export_aggregated_timers,
                 max_tracing_spans_for_path=1000,
                 min_tracing_milliseconds=3,
                 time_func=time.time):
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
        self._export_tracing_func = export_tracing_func
        self._export_aggregated_timers_func = export_aggregated_timers_func
        self._time_func = time_func
        self.MAX_REQUEST_TRACING_SPANS_FOR_PATH = max_tracing_spans_for_path
        self.TRACING_MIN_NUM_MILLISECONDS = min_tracing_milliseconds
        self._last_trace_report = None
        self._last_aggregated_report = None
        self._last_tags = None

        self._reset()

    def _reset(self):
        """Reset internal timer stack when stack is cleared"""
        if self._timer_stack:
            assert not self._strict_assert, \
                "StopWatch reset() but stack not empty: %r" % (self._timer_stack,)
        self._reported_values = {}
        self._reported_traces = []
        self._tags = set()
        self._slowtags = dict()

    ################
    # Public methods
    ################
    @contextlib.contextmanager
    def timer(self, name, bucket=None, start_time=None, end_time=None):
        """Context manager to wrap a stopwatch span"""
        self.start(name, start_time=start_time)
        try:
            yield
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

        self._timer_stack.append(TimerData(
            name=name,
            start_time=start_time or self._time_func(),
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
        tr_delta = max((tr_data.end_time - tr_data.start_time) * 1000.0, 0.001)
        if log_name in self._reported_values:
            self._reported_values[log_name][0] += tr_delta
            self._reported_values[log_name][1] += 1
        else:
            self._reported_values[log_name] = [tr_delta, 1, bucket]

        # go through slow tags and add them as tags if enough time has passed
        if not self._timer_stack:
            for tag, timelimit in self._slowtags.items():
                if timelimit * 1000.0 <= tr_delta:
                    self.addtag(tag)

        if self._should_trace_timer(log_name, tr_delta):
            tr_data.parent_span_id = self._timer_stack[-1].span_id if self._timer_stack else None

            if not self._timer_stack:
                # Add all stopwatch tags to the annotations.
                tr_data.trace_annotations += list(sorted(
                    KeyValueAnnotation(tag, '1')
                    for tag in self._tags
                ))

            self._reported_traces.append(tr_data)

        # report stopwatch tag values once the final 'end' call has been made
        if not self._timer_stack:
            self._export_tracing_func(reported_traces=self._reported_traces)
            self._export_aggregated_timers_func(
                reported_values=self._reported_values,
                tags=self._tags,
                total_time_ms=tr_delta,
                root_span_name=tr_data.name,
            )
            self._last_trace_report = self._reported_traces
            self._last_aggregated_report = self._reported_values
            self._last_tags = self._tags
            self._reset()  # Clear out stats to prevent duplicate reporting

    def addtag(self, tag):
        """Add a tag to the existing stopwatch report
        Arguments:
            tag: String to add as a tag
        """
        self._tags.add(tag)

    def addslowtag(self, tag, timelimit):
        """add tag that will only be used if root scope takes longer than
        timelimit amount of seconds
        Arguments:
            tag: String tag name for the slowtag
            timelimit: Lower bound for the root scope after which tag is applied
        """
        self._slowtags[tag] = timelimit

    def get_tags(self):
        """
        Returns a copy of the list of tags this stopwatch is using.  Use a copy so that the caller
        can't accidently alter it.
        """
        if self._tags:
            return list(self._tags)
        else:
            return None

    def get_last_trace_report(self):
        """Returns the last trace report from when the last root_scope completed"""
        return self._last_trace_report

    def get_last_aggregated_report(self):
        """Returns the last aggregated report and tags as a 2-tuple"""
        return self._last_aggregated_report, self._last_tags

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
