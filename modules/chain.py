#!/usr/bin/env python
#-*- encoding: utf-8 -*-

# Chain module.

import re

class Chain(object):
    class _BasicChain:
        def __init__(self, parent):
            self.last = None
            self.parent = parent

        def handle(self, umask, target, msg):
            if len(self.parent.msgs) >= self.parent.repeats_needed:
                if len(set(self.parent.msgs.values())) == 1:
                    if msg.lower() != self.last:
                        self.last = msg.lower()
                        return msg
                else:
                    self.last = None

    class _NumericChain:
        def __init__(self, parent):
            self.parent = parent

        def format_float(self, f):
            if f - int(f) < 0.0000000001:
                return unicode(int(f))
            else:
                return unicode(f)

        def get_reason(self, type, numbers):
            prev_r = None
            for i, num in enumerate(numbers):
                if i == 0:
                    continue
                if type == '+':
                    r = num - numbers[i - 1]
                elif type == '*':
                    r = num / numbers[i - 1]
                else:
                    raise AttributeError('type')

                if r != prev_r and prev_r is not None:
                    return
                prev_r = r

            return prev_r

        def handle(self, umask, target, msg):
            numbers = []
            for i, number in enumerate(self.parent.msgs_[-3:]):
                number = number.replace(u'pi', u'3.14159265758979')
                try:
                    numbers.append(float(number))
                except ValueError:
                    return

                if i == self.parent.repeats_needed:
                    break

            add_r = self.get_reason('+', numbers)
            if add_r:
                return self.format_float(numbers[-1] + add_r)

            mul_r = self.get_reason('*', numbers)
            if mul_r:
                return self.format(numbers[-1] * mul_r)

    class _CompleteChain:
        def __init__(self, parent):
            self.parent = parent
            self.complete = {
                u'koi': u'feur',
                u'alo': u'alo',
                u'kikoo': u'lol',
                u'lol alo': u'alo ui ?',
                u'sava': u'œ',
             }

        def handle(self, umask, target, msg):
            msg = msg.lower().strip()
            if msg in self.complete:
                return self.complete[msg]


    class _AccumulationChain:
        def __init__(self, parent):
            self.parent = parent
            self.reg_d = re.compile(ur'^:(\s*)(d|p)$', re.I)

        def find_shortest_pattern(self, msg):
            # TODO have fun
            # fsp(":d:d:d") :d
            # fsp("...") .
            # fsp("lol mdr caca") lol mdr caca
            # fsp("\o//o\\o//o\") \o//o\
            pass

        def handle(self, umask, target, msg):
            rd = self.reg_d.match(msg.strip())
            if rd:
                rdg = rd.groups()
                return u':%s%s' % ('-'*len(rdg[0]), rdg[1])

    def __init__(self, bot):
        self.bot = bot
        self.msgs = {}
        self.msgs_ = []
        self.repeats_needed = 3
        self.handlers = []

        for chain in ('Basic', 'Numeric', 'Accumulation', 'Complete'):
            inst = getattr(self, '_' + chain + 'Chain')(self)
            setattr(self, chain + 'Chain', inst)
            self.handlers.append(inst)

    def on_server_privmsg(self, umask, target, msg):
        self.msgs[umask.user] = msg
        self.msgs_.append(msg)
        
        if len(self.msgs) > self.repeats_needed:
            self.msgs = {}
            self.msgs_ = []

        for handler in self.handlers:
            output = handler.handle(umask, target, msg)
            if output:
                self.bot.message(target, output)
