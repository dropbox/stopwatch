from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import enum

from mock import Mock

from stopwatch import (
    format_report,
    KeyValueAnnotation,
    StopWatch,
)

class MyBuckets(enum.Enum):
    BUCKET_A = 1
    BUCKET_B = 2

def add_timers(sw):
    sw.addtag("Cooltag")
    sw.addslowtag("Slowtag", 100)
    sw.addslowtag("MegaSlowtag", 1000)

    with sw.timer('root', start_time=20, end_time=920):
        # First child span.
        with sw.timer('child1', start_time=40, end_time=140, bucket=MyBuckets.BUCKET_A):
            with sw.timer('grand_children1', start_time=60, end_time=80):
                pass
            with sw.timer('grand_children2', start_time=100, end_time=120):
                pass
        # Second child span with same name.
        with sw.timer('child1', start_time=160, end_time=300, bucket=MyBuckets.BUCKET_A):
            with sw.timer('grand_children3', start_time=180, end_time=190):
                pass
            with sw.timer('grand_children2', start_time=220, end_time=280):
                pass
        # Third child span with different name.
        with sw.timer('child2', start_time=320, end_time=880, bucket=MyBuckets.BUCKET_B):
            with sw.timer('grand_children3', start_time=380, end_time=390):
                pass
            with sw.timer('grand_children1', start_time=520, end_time=780):
                pass

class TestStopWatch(object):
    def test_default_exports(self):
        sw = StopWatch()
        add_timers(sw)

    def test_scope_in_loop(self):
        export_timers = Mock()
        sw = StopWatch(
            export_aggregated_timers_func=export_timers,
        )
        with sw.timer('root', start_time=20, end_time=120):
            for t in range(30, 100, 10):
                with sw.timer('child', start_time=t, end_time=t + 5):
                    pass

        export_timers.assert_called_once_with(
            reported_values={
                'root': [100000.0, 1, None],
                'root#child': [35000.0, 7, None],
            },
            tags=set(),
            total_time_ms=100000.0,
            root_span_name="root",
        )

    def test_override_exports(self):
        export_tracing = Mock()
        export_timers = Mock()
        sw = StopWatch(
            export_tracing_func=export_tracing,
            export_aggregated_timers_func=export_timers,
        )
        add_timers(sw)
        agg_report = sw.get_last_aggregated_report()
        traces = sw.get_last_trace_report()

        assert export_timers.call_args[1]['reported_values'] == agg_report[0]
        assert export_timers.call_args[1]['tags'] == agg_report[1]
        export_tracing.assert_called_once_with(reported_traces=traces)

        export_timers.assert_called_once_with(
            reported_values={
                'root': [900000.0, 1, None],
                'root#child1': [240000.0, 2, MyBuckets.BUCKET_A],
                'root#child1#grand_children1': [20000.0, 1, None],
                'root#child1#grand_children2': [80000.0, 2, None],
                'root#child1#grand_children3': [10000.0, 1, None],
                'root#child2': [560000.0, 1, MyBuckets.BUCKET_B],
                'root#child2#grand_children1': [260000.0, 1, None],
                'root#child2#grand_children3': [10000.0, 1, None],
            },
            tags=set(["Cooltag", "Slowtag"]),
            total_time_ms=900000.0,
            root_span_name="root",
        )

        # Traces are listed in the same order that scopes close
        assert [(trace.name, trace.log_name, trace.start_time,
                 trace.end_time, trace.parent_span_id) for trace in traces] == [
            ('grand_children1', 'root#child1#grand_children1', 60, 80, traces[2].span_id),
            ('grand_children2', 'root#child1#grand_children2', 100, 120, traces[2].span_id),
            ('child1', 'root#child1', 40, 140, traces[9].span_id),
            ('grand_children3', 'root#child1#grand_children3', 180, 190, traces[5].span_id),
            ('grand_children2', 'root#child1#grand_children2', 220, 280, traces[5].span_id),
            ('child1', 'root#child1', 160, 300, traces[9].span_id),
            ('grand_children3', 'root#child2#grand_children3', 380, 390, traces[8].span_id),
            ('grand_children1', 'root#child2#grand_children1', 520, 780, traces[8].span_id),
            ('child2', 'root#child2', 320, 880, traces[9].span_id),
            ('root', 'root', 20, 920, None),
        ]
        assert all(trace.trace_annotations == [] for trace in traces[:9])
        assert traces[9].trace_annotations == [
            KeyValueAnnotation('Cooltag', '1'),
            KeyValueAnnotation('Slowtag', '1'),
        ]

    def test_format_report(self):
        sw = StopWatch()
        add_timers(sw)

        agg_report = sw.get_last_aggregated_report()
        formatted_report = format_report(agg_report)
        assert formatted_report == \
            "************************\n" \
            "*** StopWatch Report ***\n" \
            "************************\n" \
            "root                    900000.000ms (100%)\n" \
            "    BUCKET_A        child1                  2  240000.000ms (27%)\n" \
            "                        grand_children1         1  20000.000ms (2%)\n" \
            "                        grand_children2         2  80000.000ms (9%)\n" \
            "                        grand_children3         1  10000.000ms (1%)\n" \
            "    BUCKET_B        child2                  1  560000.000ms (62%)\n" \
            "                        grand_children1         1  260000.000ms (29%)\n" \
            "                        grand_children3         1  10000.000ms (1%)\n" \
            "Tags: Cooltag, Slowtag"

    def test_time_func(self):
        export_mock = Mock()
        time_mock = Mock(side_effect=[50, 70])
        sw = StopWatch(export_aggregated_timers_func=export_mock, time_func=time_mock)

        # Should call our timer func once on entry and once on exit
        with sw.timer('root'):
            pass

        export_mock.assert_called_once_with(
            reported_values={
                'root': [20000.0, 1, None],
            },
            tags=set(),
            total_time_ms=20000.0,
            root_span_name="root",
        )

    def test_time_func_default(self):
        export_mock = Mock()
        sw = StopWatch(export_aggregated_timers_func=export_mock, time_func=None)
        with sw.timer('root'):
            pass
        assert export_mock.call_count == 1
        assert export_mock.call_args[1]['root_span_name'] == 'root'
        assert export_mock.call_args[1]['total_time_ms'] >= 0.0
