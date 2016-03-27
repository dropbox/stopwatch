from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import pytest

from stopwatch_global import (
    global_sw,
    global_sw_del,
    global_sw_init,
)

@pytest.fixture
def global_sw_fixture(request):
    global_sw_init()
    request.addfinalizer(global_sw_del)

@pytest.mark.usefixtures('global_sw_fixture')
class TestStopWatchGlobal(object):
    def test_global_sw(self):
        with global_sw().timer('root'):
            pass
        last_report = global_sw().get_last_aggregated_report()
        assert list(last_report.aggregated_values.keys()) == ['root']
