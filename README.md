# stopwatch [![Build Status](https://travis-ci.org/dropbox/stopwatch.svg?branch=master)](https://travis-ci.org/dropbox/stopwatch)
Scoped, nested, aggregated python timing library

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

Aggregated reports have one value for each timer name. The above example would have 2 reports.

Tracing reports keep one trace every time we enter a scope. The above example would
have 51 reports.

By default, StopWatch dumps aggregated report to stdout after the root scope completes and
resets internal state.

Installation
------------

```
pip install dbx-stopwatch
```

Usage
-----

Basic Usage
```
import stopwatch

sw = stopwatch.StopWatch()
with sw.timer('root'):
    for i in range(50):
        with sw.timer('inner_task'):
            time.sleep(0.1)
    with sw.timer('outer_task'):
        time.sleep(1.0)
print stopwatch.format_report(sw.get_last_aggregated_report())
```
yields
```
************************
*** StopWatch Report ***
************************
root                    6206.833 (100%)
                    inner_task             50  5200.742 (84%)
                    outer_task              1  1002.351 (16%)
Tags:
```
Multiple reports
```
sw = stopwatch.StopWatch()

while request_in_queue():
    r = get_request()
    with sw.timer('request'):
        process(request)
```
Tag your reports
```
while request_in_queue():
    r = get_request()
    with sw.timer('request'):
        sw.addtag(r.get_endpoint_name())
        sw.addslowtag('500ms', 0.500)  # Tag only if request takes >= 500ms
        process(request)
```
Report to your own backend
```
sw = stopwatch.StopWatch(
    export_aggregated_timers_func=my_export_aggregated_timers,
    export_tracing_func=my_export_tracing_func,
)
```

Contributing
------------
Contributions are welcome. Tests can be run with [tox][tox]. Lint with [flake8][flake8]
You'll have to agree to Dropbox's [CLA][CLA].

Issues
------
If you encounter any problems, please [file an issue][issues] along with a detailed description.

[flake8]: https://flake8.readthedocs.org/en/latest/
[issues]: https://github.com/dropbox/stopwatch/issues
[tox]: https://tox.readthedocs.org/en/latest/
[CLA]: https://opensource.dropbox.com/cla/
