#!/usr/bin/env python
#-*- encoding: utf-8 -*-

# arok.py
# Auto-rejoin on kick module.

# This file is part of pypeul.
#
# Copyright (c) 2010 Mick@el and Zopieux
#
# pypeul is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# pypeul is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with pypeul. If not, see <http://www.gnu.org/licenses/>.

class Arok(object):
    def __init__(self, bot):
        self.bot = bot

    def on_server_kick(self, umask, chan, target, reason):
        if self.bot.is_me(target):
            self.bot.join(chan)
