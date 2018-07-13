#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import codecs
from setuptools import setup

if sys.version_info < (3, 4):
    sys.exit("Sorry, Python < 3.4 is not supported (you're using an old version of pip/setuptools)")


def read(fname):
    file_path = os.path.join(os.path.dirname(__file__), fname)
    return codecs.open(file_path, encoding='utf-8').read()


setup(
    name='pytest-circuitpython',
    version='0.0.1',
    author='Noralf Trønnes',
    author_email='noralf@tronnes.org',
    maintainer='Noralf Trønnes',
    maintainer_email='noralf@tronnes.org',
    license='MIT',
    url='https://github.com/notro/pytest-circuitpython',
    description='A pytest plugin for running tests on CircuitPython',
    long_description=read('README.rst'),
    packages=['pytest_circuitpython'],
    py_modules=['cpboard'],
    include_package_data=True,
    python_requires='>=3.4',
    install_requires=['pytest>=3.5.0', 'pyserial>=3.4', 'pyusb>=1.0.2', 'sh>=1.12.14'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Pytest',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Testing',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: CircuitPython',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: MIT License',
    ],
    entry_points={
        'pytest11': [
            'circuitpython = pytest_circuitpython',
        ],
    },
)
