# stopwatch
Scoped, nested, aggregated python timing library

Usage
-----

Basic Usage
```
sw = stopwatch.StopWatch()
with sw.timer('root'):
    for i in range(50):
        with sw.timer('inner_task'):
            time.sleep(0.1)
    with sw.timer('outer_task'):
        time.sleep(1.0)
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

Contributing
------------
Contributions are welcome. Tests can be run with `tox`.

Issues
------
If you encounter any problems, please `file an issue`_ along with a detailed description.

.. _`file an issue`: https://github.com/dropbox/stopwatch/issues
.. _`tox`: https://tox.readthedocs.org/en/latest/
