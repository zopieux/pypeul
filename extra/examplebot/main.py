#!/usr/bin/env python
#-*- encoding: utf-8 -*-

# main.py
# Test bot for pypeul.

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

from pypeul import *
import sys

class ModuleNotFound(Exception): pass

class TestBot(IRC):
    def on_ready(self):
        self.join('#irclib-dev')

    def on_server_privmsg(self, umask, target, msg):

        try:
            if msg.startswith('!colorize '):
                words = msg[10:].split()
                self.message(target, u' '.join(
                    (Tags.__getattr__(_.title()) if _.lower() in Tags.colors \
                    else  _ + Tags.Uncolor) for _ in words))

            elif msg.startswith('!guess '):
                guessed = map(lambda t: Tags.Bold(unicode(t)), self.nick_guess(msg[7:], target))
                if len(guessed) == 0:
                    self.message(target, u'Connaît pas.')
                elif len(guessed) == 1:
                    self.message(target, u'Lol tu veux dire ' + guessed[0] + u' !')
                else:
                    self.message(target, u'Euh, tu veux dire ' +
                        u', '.join(guessed[:-1]) + u' ou ' + guessed[-1] +  u' ?')

            elif msg.startswith('!load '):
                for modname in map(unicode.lower, msg[6:].split()):
                    if not modname:
                        continue
                    try:
                        self.load_module(modname)
                        self.message(target, 'Module %s (re)loaded.' % Tags.Bold(modname))
                    except ModuleNotFound:
                        self.message(target, 'Module %s not found.' % Tags.Bold(modname))

            elif msg.startswith('!unload '):
                for modname in map(unicode.lower, msg[8:].split()):
                    if not modname:
                        continue
                    try:
                        self.unload_module(modname)
                        self.message(target, 'Module %s unloaded.' % Tags.Bold(modname))
                    except ModuleNotFound:
                        self.message(target, 'Module %s not found.' % Tags.Bold(modname))

            if umask.host not in ('mickael.is-a-geek.net', 'home.zopieux.com'):
                return

            if msg.startswith('!dump '):
                self.message(target, unicode(eval(msg[6:])))

            elif msg.startswith('!exec '):
                exec msg[6:] in locals(), globals()


        except Exception as ex:
            self.message(target, Tags.Bold('Exception : ') + repr(ex))
            raise

    def on_ctcp_ping_request(self, umask, value):
        self.ctcp_reply(umask.nick, 'PING', value)

    def on_ctcp_version_request(self, umask, value):
        self.ctcp_reply(umask.nick, 'VERSION', sys.modules['irclib'].__version__)

    def nick_guess(self, part, channel):
        """
        Useful function that returns a list of 0, 1 or several possible users
        """
        return [user for lnick, user in self.users.items() if irc_lower(part) in lnick and channel in user.channels]

    def load_module(self, modname):
        modname = modname.lower()

        try:
            if modname in self.handlers:
                module = reload(sys.modules['modules.' + modname])
            else:
                module = getattr(__import__('modules.' + modname), modname)

            self.handlers[modname] = getattr(module, modname.title())(self)
        except ImportError:
            raise ModuleNotFound

    def unload_module(self, modname):
        modname = modname.lower()

        try:
            del sys.modules['modules.' + modname]
            del self.handlers[modname]
        except KeyError:
            raise ModuleNotFound

bot = TestBot()
bot.connect('irc.epiknet.net', 7002, True)
bot.ident('TestBot')
bot.load_module('arok')
bot.load_module('chain')

bot.run()
