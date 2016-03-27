"""StopWatch - library for adding timers and tags in your code for performance monitoring
https://github.com/dropbox/stopwatch

This module provides an easy mechanism for using one-stopwatch-per-thread by storing
it at global scope.

For example:
```
with global_sw().timer('root'):
    for i in range(50):
        with global_sw().timer('inner_task'):
            do_inner_task(i)
```
"""

import threading

from stopwatch import StopWatch

_GLOBAL_SW = None

class _GlobalSw(object):
    """A global store for thread-local stopwatches. Helps with the common case where
    the caller only wants one stopwatch per thread.
    """
    def __init__(self, time_func=None, export_aggregated_timers_func=None):
        self.threadlocal_sws = threading.local()
        self.time_func = time_func
        self.export_agg_timers_func = export_aggregated_timers_func

    def global_sw(self):
        """Returns the thread local stopwatch (creating if it doesn't exists)"""
        if not hasattr(self.threadlocal_sws, 'sw'):
            self.threadlocal_sws.sw = StopWatch(
                export_aggregated_timers_func=self.export_agg_timers_func,
                time_func=self.time_func,
            )
        return self.threadlocal_sws.sw

def global_sw_init(*args, **kwargs):
    """Initialize global stopwatch with the completion callbacks"""
    global _GLOBAL_SW
    assert _GLOBAL_SW is None, "Cannot initialize global_sw twice"
    _GLOBAL_SW = _GlobalSw(*args, **kwargs)

def global_sw_del():
    """Delete the global stopwatch. Typically not necessary, as stopwatch is reusable
    but can useful for tests"""
    global _GLOBAL_SW
    assert _GLOBAL_SW is not None, "Cannot del global_sw since it was never initialized"
    _GLOBAL_SW = None

def global_sw():
    """Return the stopwatch for the current thread"""
    assert _GLOBAL_SW is not None, "Must initialize global_sw_init first"
    return _GLOBAL_SW.global_sw()
