#!/usr/bin/env python3
from setuptools import setup

setup(
    name='rass',
    version='0.1.0',
    description='A simple LSP multiplexer',
    py_modules=['rass'],
    python_requires='>=3.10',
    entry_points={
        'console_scripts': [
            'rass=rass:main',
        ],
    },
)
