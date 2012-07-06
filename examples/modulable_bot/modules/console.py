# console.py
# Interactive Python console over IRC

# This file is part of pypeul.
#
# Copyright (c) 2012 - mickael9
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

import code
import sys
from io import StringIO
from threading import Thread, RLock
from queue import Queue

class RedirectedStream(object):
    def __init__(self, original):
        self.original = original
        self.redirect = original
        self.lock = RLock()

    def redirect_start(self, redirect):
        self.lock.acquire()
        self.redirect = redirect

    def redirect_end(self):
        self.redirect = self.original
        self.lock.release()

    def __getattr__(self, name):
        self.lock.acquire()
        ret = getattr(self.redirect, name)
        self.lock.release()
        return ret

sys.stdout = RedirectedStream(sys.__stdout__)

class IRCConsole(code.InteractiveConsole):
    def __init__(self, bot, user):
        super().__init__({'bot': bot})
        self.bot = bot
        self.user = user
        self.thread = None
        self.read_buffer = Queue()
        self.write_buffer = ''

    def runcode(self, code):
        sys.stdout.redirect_start(self)
        try:
            super().runcode(code)
        finally:
            sys.stdout.redirect_end()

    def write(self, data):
        self.write_buffer += data

        while '\n' in self.write_buffer:
            self.bot.message(self.user, self.write_buffer.split('\n')[0])
            self.write_buffer = '\n'.join(self.write_buffer.split('\n')[1:])

    def raw_input(self, prompt=''):
        if prompt:
            self.write(prompt + '\n')
        return self.read_buffer.get()

    def shutdown(self):
        self.thread._stop()
        self.thread.join()

class Console(object):
    def __init__(self, bot):
        self.bot = bot
        self.consoles = {}

    def on_message(self, umask, target, msg):
        if umask.host not in self.bot.admins:
            return

        user = umask.user

        if msg == '!console':
            if user in self.consoles:
                self.consoles[user].shutdown()
                del self.consoles[user]

            self.consoles[user] = IRCConsole(self.bot, user)
            self.consoles[user].thread = Thread(target=self.consoles[user].interact)
            self.consoles[user].thread.start()

        elif msg == '!exit' and user in self.consoles:
            self.consoles[user].shutdown()
            del self.consoles[user]

        elif self.bot.is_me(target) and user in self.consoles:
            if msg == '.':
                msg = ''
            self.consoles[user].read_buffer.put(msg)
