#!/usr/bin/env python
#-*- encoding: utf-8 -*-

# chain.py
# Chain module.

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

import re
import urllib.request, urllib.parse, urllib.error
import operator

class Chain(object):
    class _BasicChain:
        msg = ''
        users = []
        repeats = 3

        def handle(self, umask, target, msg):
            if self.msg != msg: # chain broken...
                self.msg = msg
                self.users = [umask.user]
                return

            if umask.user in self.users: # cheating user, just ignore him
                return

            self.users.append(umask.user)

            if len(self.users) == self.repeats:
                return msg

    class _NumericChain:
        numbers = []
        last_r = None
        repeats = 5
        special_seqs = {}
        url = 'http://www.research.att.com/~njas/sequences/?q=%s&n=1&fmt=3'

        def format_float(self, f):
            if round(f, 10) == int(f):
                return str(int(f))
            else:
                return str(f)

        def get_reason(self, type, numbers):
            if 0 in numbers and type == '*':
                return

            prev_r = None
            for i, num in enumerate(numbers):
                if i == 0:
                    continue
                if type == '+':
                    r = round(num - numbers[i - 1], 8)
                elif type == '*':
                    r = round(num / numbers[i - 1], 8)
                else:
                    raise AttributeError('type')

                if r != prev_r and prev_r is not None:
                    return
                prev_r = r

            return prev_r

        def get_special_seq(self, numbers):
            numbers = numbers[:]
            for i, number in enumerate(numbers):
                if round(number, 10) != int(number):
                    return
                numbers[i] = str(int(number))

            find_re = re.compile('(?:^|,)' + ','.join(numbers) + ',(\d+)(?:,|$)')
            match = None

            for id, seq in self.special_seqs.items():
                match = find_re.search(seq)
                if match:
                    return id, match.group(1)

            data = [line.split()[1:] for line in urllib.request.urlopen(
                self.url % (','.join(numbers))
                ).read().split('\n')
                if line[:2] in ('%S', '%T', '%')]
            if not data:
                return

            id = data[0][0]
            seq = ''.join(map(operator.itemgetter(1), data))

            match = find_re.search(seq)

            if not match:
                return

            self.special_seqs[id] = seq
            return id, match.group(1)

        def handle(self, umask, target, msg):
            try:
                self.numbers.append(float(msg))
            except ValueError: # no number, no sequence
                self.numbers = []
                self.last_r = None
                return

            if len(self.numbers) > self.repeats:
                self.numbers.pop(0)

            if len(self.numbers) < self.repeats:
                return

            add_r = self.get_reason('+', self.numbers)
            mul_r = self.get_reason('*', self.numbers)

            if add_r:
                if self.last_r == ('+', add_r):
                    return

                ret = self.format_float(self.numbers[-1] + add_r)
                self.last_r = ('+', add_r)
                self.numbers = []
                return ret

            elif mul_r:
                if self.last_r == ('*', mul_r):
                    return

                ret =  self.format_float(self.numbers[-1] * mul_r)
                self.last_r = ('*', mul_r)
                self.numbers = []
                return ret

            else:
                try:
                    id, next = self.get_special_seq(self.numbers)
                except:
                    self.last_r = None
                    return

                if self.last_r == ('?', id):
                    return

                self.last_r = ('?', id)
                self.numbers = []
                return next

    class _CompleteChain:
        complete = {
            'koi': 'feur',
            'alo': 'alo',
            'kikoo': 'lol',
            'lol alo': 'alo ui ?',
            'sava': 'œ',
         }

        def handle(self, umask, target, msg):
            msg = msg.lower().strip()
            if msg in self.complete:
                return self.complete[msg]


    class _AccumulationChain:
        reg_d = re.compile(r'^:(\s*)(d|p)$', re.I)

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
                return ':%s%s' % ('-'*len(rdg[0]), rdg[1])

    def __init__(self, bot):
        self.bot = bot
        self.handlers = []

        for chain in ('Basic', 'Accumulation', 'Complete', 'Numeric'):
            inst = getattr(self, '_' + chain + 'Chain')()
            setattr(self, chain + 'Chain', inst)
            self.handlers.append(inst)

    def on_server_privmsg(self, umask, target, msg):
        for handler in self.handlers:
            output = handler.handle(umask, target, msg)
            if output:
                self.bot.message(target, output)
                return
