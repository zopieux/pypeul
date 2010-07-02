#!/usr/bin/env python
#-*- encoding: utf-8 -*-
#
# lodgeit.py
# Module to paste files to lodgeit
#
# This file is part of pypeul.
#
# Copyright (c) 2010 Pierre Bourdon <delroth@gmail.com>
#
# irclib is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# irclib is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with pypeul. If not, see <http://www.gnu.org/licenses/>.

import xmlrpc
import os
from pypeul import Tags

XMLRPC = 'http://paste.pocoo.org/xmlrpc/'
SHOW = 'http://paste.pocoo.org/show/%s/'

class Lodgeit(object):
    def __init__(self, bot):
        self.bot = bot
        self.lodgeit = xmlrpc.client.ServerProxy(XMLRPC, allow_none=True)

    def on_server_privmsg(self, umask, target, msg):
        if msg.startswith('!paste'):
            cmd, args = msg.split()[0], msg.split()[1:]
            if cmd == '!paste':
                self.react(target, args, private=False)
            elif cmd == '!pasteprivate':
                self.react(target, args, private=True)

    def help(self, cmd, args):
        out = '%s: %s %s' % (Tags.Green('usage'), Tags.Bold(cmd), args)
        self.bot.message(target, out)

    def react(self, target, args, private):
        if len(args) == 0:
            cmd = '!paste' if not private else '!pasteprivate'
            self.help(cmd, '<filename> [filename2] ... [filenameN]')
        else:
            for fn in args:
                id = self.paste(fn, private)
                out = '%s : %s' % (fn, SHOW % id)
                self.bot.message(target, out)

    def paste(self, fn, private):
        if '..' in fn:
            raise AttributeError

        fn = './' + fn

        id = self.lodgeit.pastes.newPaste(None, open(fn).read(), None, fn, None, private)
        return id
