#!/usr/bin/env python3
#-*- encoding: utf-8 -*-
"""
    Pypeul
    ~~~~~~

    Pypeul is an IRC client library written in Python.

    It mainly aims at creating IRC bots and provides an easy to use API
    based on callbacks. It also features a nice way to parse and write
    formatted text.

    :copyright: Copyright 2010-2012- by the Pypeul team, see AUTHORS.
    :license: LGPL, see COPYING for details.
"""

from distutils.core import setup

setup(
    name = 'Pypeul',
    version = '0.3.1',
    url = 'http://bitbucket.org/Zopieux/pypeul/',
    license = 'LGPL',
    author = 'mickael9; Zopieux',
    author_email = 'mickael9@gmail.com; zopieux@gmail.com',
    description = 'A Python 3 IRC library thought for the programmer.',
    long_description = __doc__,
    keywords = 'irc',
    py_modules = ['pypeul'],
    platforms = 'any',
)
