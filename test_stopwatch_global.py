from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import pytest

from mock import Mock

from stopwatch_global import (
    global_sw,
    global_sw_del,
    global_sw_init,
)


@pytest.fixture
def global_sw_fixture(request):
    request.addfinalizer(global_sw_del)


@pytest.mark.usefixtures('global_sw_fixture')
class TestStopWatchGlobal(object):
    def test_global_sw(self):
        global_sw_init()
        with global_sw().timer('root'):
            pass
        last_report = global_sw().get_last_aggregated_report()
        assert list(last_report.aggregated_values.keys()) == ['root']

    @staticmethod
    def add_spans():
        with global_sw().timer('parent', start_time=20, end_time=80):
            global_sw().add_span_annotation('parent_annotation', 1)
            with global_sw().timer('child', start_time=40, end_time=60):
                global_sw().add_span_annotation('child_annotation', 1)

    def test_callbacks(self):
        tracing_function = Mock()
        agg_timers_and_tracing_func = Mock()
        global_sw_init(export_tracing_func=tracing_function,
                       export_aggregated_timers_and_tracing_func=agg_timers_and_tracing_func)
        self.add_spans()
        last_report = global_sw().get_last_aggregated_report()
        reported_traces = global_sw().get_last_trace_report()

        assert last_report.aggregated_values.keys() == ['parent', 'parent#child']

        assert len(reported_traces) == 2
        assert reported_traces[0].trace_annotations[0].key == 'child_annotation'
        assert reported_traces[1].trace_annotations[0].key == 'parent_annotation'

        tracing_function.assert_called_once_with(reported_traces=reported_traces)
        agg_timers_and_tracing_func.assert_called_once_with(aggregated_report=last_report,
                                                            reported_traces=reported_traces)
