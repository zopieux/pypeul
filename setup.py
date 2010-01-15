#!/usr/bin/env python
#-*- encoding: utf-8 -*-
"""
    Pypeul
    ~~~~~~

    Pypeul is an IRC client library written in Python.

    It mainly aims at creating IRC bots and provides an easy to use API
    based on callbacks.

    :copyright: Copyright 2010 by the Pypeul team, see AUTHORS.
    :license: LGPL, see COPYING for details.
"""

from distutils.core import setup

setup(
    name = 'Pypeul',
    version = '0.1',
    url = 'http://bitbucket.org/zopieux/pypeul/',
    license = 'LGPL',
    author = 'Mick@el; Zopieux',
    author_email = 'mickael9@gmail.com; zopieux@gmail.com',
    description = 'Pypeul is an IRC client library written in Python.',
    long_description = __doc__,
    keywords = 'irc',
    py_modules = ['pypeul'],
    platforms = 'any',
)
