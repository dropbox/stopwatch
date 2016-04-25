from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import enum
import pytest

from mock import Mock

from stopwatch import (
    format_report,
    TraceAnnotation,
    StopWatch,
)

class MyBuckets(enum.Enum):
    BUCKET_A = 1
    BUCKET_B = 2

def add_timers(sw):
    with sw.timer('root', start_time=20, end_time=920):
        sw.add_annotation("Cooltag", event_time=50)
        sw.add_slow_annotation("Slowtag", 100)
        sw.add_slow_annotation("MegaSlowtag", 1000)

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
        sw = StopWatch()
        with sw.timer('root', start_time=20, end_time=120):
            for t in range(30, 100, 10):
                with sw.timer('child', start_time=t, end_time=t + 5):
                    pass

        agg_report = sw.get_last_aggregated_report()
        assert agg_report.aggregated_values == {
            'root': [100000.0, 1, None],
            'root#child': [35000.0, 7, None],
        }
        assert agg_report.root_timer_data.start_time == 20.0
        assert agg_report.root_timer_data.end_time == 120.0
        assert agg_report.root_timer_data.name == 'root'

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

        export_timers.assert_called_once_with(aggregated_report=agg_report)
        export_tracing.assert_called_once_with(reported_traces=traces)

        assert agg_report.aggregated_values == {
            'root': [900000.0, 1, None],
            'root#child1': [240000.0, 2, MyBuckets.BUCKET_A],
            'root#child1#grand_children1': [20000.0, 1, None],
            'root#child1#grand_children2': [80000.0, 2, None],
            'root#child1#grand_children3': [10000.0, 1, None],
            'root#child2': [560000.0, 1, MyBuckets.BUCKET_B],
            'root#child2#grand_children1': [260000.0, 1, None],
            'root#child2#grand_children3': [10000.0, 1, None],
        }
        assert agg_report.root_timer_data.start_time == 20.0
        assert agg_report.root_timer_data.end_time == 920.0
        assert agg_report.root_timer_data.name == 'root'
        assert agg_report.root_timer_data.trace_annotations == [
            TraceAnnotation('Cooltag', '1', 50),
            TraceAnnotation('Slowtag', '1', None),
        ]

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
            TraceAnnotation('Cooltag', '1', 50),
            TraceAnnotation('Slowtag', '1', None),
        ]

    def test_trace_annotations(self):
        sw = StopWatch()
        sw.add_annotation('key0', 'value0', event_time=0)
        with sw.timer('root', start_time=10, end_time=1000):
            with sw.timer('child', start_time=20, end_time=900):
                sw.add_span_annotation('key1', 'value1', event_time=101)
                sw.add_span_annotation('key2', 'value2', event_time=104)
                sw.add_annotation('key3', 'value3', event_time=107)
        trace_report = sw.get_last_trace_report()
        assert len(trace_report) == 2
        assert trace_report[0].name == 'child'
        assert trace_report[0].trace_annotations == [
            TraceAnnotation('key1', 'value1', 101),
            TraceAnnotation('key2', 'value2', 104),
        ]
        assert trace_report[1].name == 'root'
        assert trace_report[1].trace_annotations == [
            TraceAnnotation('key0', 'value0', 0),
            TraceAnnotation('key3', 'value3', 107),
        ]

    def test_exception_annotation(self):
        class SpecialError(Exception):
            pass

        sw = StopWatch()
        with pytest.raises(SpecialError):
            with sw.timer('root', start_time=10, end_time=1000):
                raise SpecialError("Ahhh")
        trace_report = sw.get_last_trace_report()
        assert trace_report[0].trace_annotations == [
            TraceAnnotation('Exception', 'SpecialError', 1000),
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
            "Annotations: Cooltag, Slowtag"

        formatted_report2 = sw.format_last_report()
        assert formatted_report == formatted_report2

    def test_time_func(self):
        """Test override of the time_func"""
        time_mock = Mock(side_effect=[50, 70])
        sw = StopWatch(time_func=time_mock)

        # Should call our timer func once on entry and once on exit
        with sw.timer('root'):
            pass

        agg_report = sw.get_last_aggregated_report()
        assert agg_report.aggregated_values == {
            'root': [20000.0, 1, None],
        }
        assert agg_report.root_timer_data.start_time == 50.0
        assert agg_report.root_timer_data.end_time == 70.0
        assert agg_report.root_timer_data.name == 'root'

    def test_time_func_default(self):
        """Make sure that the default time_func=None"""
        sw = StopWatch(time_func=None)
        with sw.timer('root'):
            pass
        agg_report = sw.get_last_aggregated_report()
        tr_data = agg_report.root_timer_data
        assert tr_data.name == 'root'
        assert tr_data.end_time >= tr_data.start_time

    def test_export_default(self):
        """Make sure that passing None in explicitly works"""
        sw = StopWatch(export_aggregated_timers_func=None, export_tracing_func=None)
        with sw.timer('root'):
            pass
