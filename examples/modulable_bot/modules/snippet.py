#!/usr/bin/env python
#-*- encoding: utf-8 -*-

# snippet.py
# Creates code snippets that can be executed later.

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

from pypeul import Tags

class Snippet(object):
    def __init__(self, bot):
        self.bot = bot
        self.snippets = {}

    def on_message(self, umask, target, msg):
        if umask.host not in self.bot.admins:
            return

        parts = msg.split()
        if msg.startswith('!snip ') and len(parts) >= 3:
            self.snippets[parts[1]] = ' '.join(parts[2:])

        if msg.startswith('!unsnip ') and len(parts) >= 2:
            try:
                del self.snippets[parts[1]]
            except KeyError:
                pass

        if msg.startswith('.') and parts[0][1:] in self.snippets:
            try:
                exec(self.snippets[parts[0][1:]], locals(), globals())
            except Exception as ex:
                self.bot.message(target, Tags.Bold('Exception: ') + repr(ex))

