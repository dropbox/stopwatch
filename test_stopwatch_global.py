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
    @staticmethod
    def add_spans():
        with global_sw().timer('parent', start_time=20, end_time=80):
            global_sw().add_span_annotation('parent_annotation', 1)
            with global_sw().timer('child', start_time=40, end_time=60):
                global_sw().add_span_annotation('child_annotation', 1)

    def test_reported_traces(self):
        tracing_function = Mock()
        global_sw_init(export_tracing_func=tracing_function)
        self.add_spans()
        reported_traces = global_sw().get_last_trace_report()

        assert len(reported_traces) == 2
        assert reported_traces[0].trace_annotations[0].key == 'child_annotation'
        assert reported_traces[1].trace_annotations[0].key == 'parent_annotation'
        tracing_function.assert_called_once_with(reported_traces=reported_traces)

    def test_global_sw(self):
        global_sw_init()
        with global_sw().timer('root'):
            pass
        last_report = global_sw().get_last_aggregated_report()
        assert list(last_report.aggregated_values.keys()) == ['root']
