#!/usr/bin/env python3
#-*- encoding: utf-8 -*-

# main.py
# Simple bot example for pypeul.

# This file is part of pypeul IRC lib.
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
import time

class SimpleBot(IRC):
    def on_ready(self):
        """
        If you want your bot to join a channel when it connects, you should do
        that in the on_ready event handler.
        """
        self.join("#pypeul")

    def on_self_join(self, target):
        """
        There are various on_self_* event handlers. They're called when the bot
        does something related to itself (the usermask is the bot's one).
        In this case, this callback is triggered when the bot joins a channel.
        Let's welcome people, with some colors!
        """
        self.message(target, Tags.Red("Hello, ") + Tags.Blue("World!"))

    def on_channel_message(self, umask, target, msg):
        """
        Main event handler, called when someone speaks on a channel where the
        bot is.
        Here, we just send back what people say, mirrored for the fun. If user
        has got "lol" in its nickname, we answer him something special.
        """
        if "lol" in umask.nick.lower():
            self.message(target, "Please {0}, don't bother us.".format(umask))
        else:
            self.message(target, msg[::-1])

    def on_ctcp_version_request(self, umask, value):
        """
        There are event handlers for CTCP too.
        Here the bot replies its own __version__ string on a CTCP "version".
        """
        self.ctcp_reply(umask.nick, 'VERSION', "SimpleBot, powered by pypeul")

    def on_disconnected(self):
        logger.info('Disconnected. Trying to reconnect...')
        while True:
            try:
                self.connect('irc.freenode.net', 6667)
                self.ident('SimpleBot')
                self.run()
                break
            except:
                logger.error('Attempt failed. Retrying in 30s...')
            time.sleep(30)


if __name__ == '__main__':
    # Enable debug-level logging
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Instanciate our SimpleBot class and let it run
    bot = SimpleBot()
    bot.connect('irc.freenode.net', 6667)
    bot.ident('SimpleBot')
    bot.run()
