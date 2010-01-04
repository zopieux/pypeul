#!/usr/bin/env python
#-*- encoding: utf-8 -*-

# Auto-rejoin on kick plugin.

class Arok(object):
    def __init__(self, bot):
        self.bot = bot

    def on_server_kick(self, umask, chan, target, reason):
        if self.bot.is_me(target):
            self.bot.join(chan)
