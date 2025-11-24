#!/usr/bin/env python3
from setuptools import setup

setup(
    name='lspylex',
    version='0.1.0',
    description='A simple LSP multiplexer',
    py_modules=['lspylex'],
    python_requires='>=3.10',
    entry_points={
        'console_scripts': [
            'lspylex=lspylex:main',
        ],
    },
)
