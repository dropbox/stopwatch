from setuptools import setup

setup(
    name="dbx-stopwatch",
    version="1.1",
    description='Scoped, nested, aggregated python timing library',
    keywords='stopwatch dropbox',
    license='Apache License 2.0',
    author='Nipunn Koorapati',
    author_email='nipunn@dropbox.com',
    py_modules=['stopwatch', 'stopwatch_global'],
    url='https://github.com/dropbox/stopwatch',
    download_url='https://github.com/dropbox/stopwatch/tarball/1.1',

    install_requires=[],
)
