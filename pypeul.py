#!/usr/bin/env python
# -*- encoding: utf-8 -*-

# pypeul.py
# An IRC client library designed to write bots in a fast and easy way.

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

__version__ = 'Pypeul python IRC client library v0.1 by Mick@el & Zopieux'

ENCODING = 'utf-8'

import socket
import threading
import re
import sys
from collections import namedtuple
from textwrap import wrap

RE_COLOR = re.compile(r'\x03(\d{1,2})?(?:,(\d{1,2})?)?')

# Decorator used to specify that a callbacks needs to be run in a thread
def threaded(func):
    if not func.func_name.lower().startswith('on_'):
        raise TypeError("threaded decorator can only be used on callback functions")

    func.threaded = True
    return func

def irc_lower(s):
	# TODO: better implementation
    return s.encode('utf-8').lower().decode('utf-8')

def irc_equals(s1, s2):
    return irc_lower(s1) == irc_lower(s2)

class _tags(object):
    Reset = '\x0f'
    Uncolor = '\x03'

    colors = {
        'white' : '00',
        'black' : '01',
        'blue' : '02',
        'green': '03',
        'red': '04',
        'brown ' : '05',
        'purple' : '06',
        'orange' : '07',
        'yellow' : '08',
        'ltgreen' : '09',
        'teal' : '10',
        'cyan' : '11',
        'ltblue' : '12',
        'pink' : '13',
        'grey' : '14',
        'ltgrey' : '15'}

    tags = {
        'bold' : '\x02',
        'underline' : '\x1f',
        'reverse' : '\x16',
    }

    def strip(self, text):
        text = RE_COLOR.sub('', text)
        for val in _tags.tags.values():
            text = text.replace(val[0], '')
        return text

    class callable_tag(object):
        def __init__(self, start, end=''):
            self.start = start
            self.end = end

        def __add__(self, other):
            if isinstance(other, basestring):
                return unicode(self) + other
            elif isinstance(other, _tags.callable_tag):
                return unicode(self) + unicode(other)
            else:
                raise TypeError

        def __radd__(self, other):
            if isinstance(other, basestring):
                return other + unicode(self)
            elif isinstance(other, _tags.callable_tag):
                return unicode(other) + unicode(self)
            else:
                raise TypeError

        def __unicode__(self):
            return self.start

        def __call__(self, *params):
            return self.start + ' '.join(params) + self.end

    def __getattr__(self, name):
        fg = None
        bg = None
        format = ''
        buffer = ''

        for char in name:
            buffer += char.lower()
            found = True
            if buffer in self.colors:
                if fg is None:
                    fg = self.colors[buffer]
                elif bg is None:
                    bg = self.colors[buffer]
                else:
                    raise AttributeError(name)
            elif buffer in self.tags:
                if self.tags[buffer] in format:
                    raise AttributeError(name)
                format += self.tags[buffer]
            elif buffer == 'none':
                if fg is None and bg is None:
                    fg = ''
                else:
                    raise AttributeError(name)
            else:
                found = False

            if found:
                buffer = ''

        if buffer or (fg == '' and bg is None):
            raise AttributeError(name)

        color = ''
        uncolor = ''
        if fg is not None:
            uncolor = '\x03'
            color = '\x03' + fg
            if bg:
                color += ',' + bg

        return self.callable_tag(format + color, format + uncolor)

Tags = _tags()

class ServerConfig(object):
    def __init__(self):
        self.info = {
        'CHANMODES': 'ovb,k,l,psitnm',
        'PREFIX': '(ov)@+',
        'MAXLIST': 'b:10,e:10,I:10', # arbitrary
        }

    def __getitem__(self, item):
        return self.info[item]

    def __setitem__(self, item, value):
        self.info[item] = value

    def __contains__(self, item):
        return item in self.info

    @property
    def chanmodes(self):
        return namedtuple('chanmodes', ['user', 'string', 'numeric', 'normal'])._make(map(set, self.info['CHANMODES'].split(',')))

    @property
    def maxlists(self):
        return dict((_.split(':')[0], int(_.split(':')[1]))
            for _ in self.info['MAXLIST'].split(','))

    @property
    def lists(self):
        return set(self.maxlists.keys())

    @property
    def prefixes_mapping(self):
        left, right = self.info['PREFIX'].split(')')
        return dict(zip(right, left[1:]))

    @property
    def prefixes_modes(self):
        return set(self.prefixes_mapping.values())

    @property
    def user_level_modes(self):
        '''Returns modes that apply to channel users (except lists like bans)'''
        return (self.chanmodes.user - self.lists) | self.prefixes_modes

    @property
    def param_modes(self):
        '''Returns modes that take a parameter.'''
        return self.chanmodes.user | self.chanmodes.string | \
            self.chanmodes.numeric | self.prefixes_modes

class IRC(object):
    def __init__(self, loggingEnabled = True, thread_callbacks = False):
        self.thread_callbacks = thread_callbacks
        self.loggingEnabled = loggingEnabled

        self.connected = False
        self.enabled = True

        self.bans = {}
        self.users = {}
        self.myself = None
        self.serverconf = ServerConfig()
        self.handlers = {}

    def is_channel(self, text):
        return text.startswith('#') or text.startswith('&')

    def is_me(self, user):
        return irc_equals(unicode(user), unicode(self.myself))

    def connect(self, host, port = 6667, use_ssl=False):
        '''Etablish a connection to a server'''
        self.log('@ Connecting to %s port %d' % (host, port))

        self.sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        if use_ssl:
            import ssl
            self.sk = ssl.wrap_socket(self.sk)
        
        self.sk.connect((host, port))

        self.log('@ Connected')

        self.connected = True

        self._callback('on_connected')

    def run(self):
        file = self.sk.makefile()

        while self.enabled:
            try:
                txt = file.readline()
            except:
                break

            if txt == '':
                break

            self._process_message(txt.strip('\r\n'))

        self.connected = False

        self.log('@ Disconnected')

        self._callback('on_disconnnected')
        self.enabled = False

    def run_threaded(self):
        thread = threading.Thread(target=self.run)
        thread.setDaemon(True)
        thread.start()

        return thread

    def log(self, txt):
        if self.loggingEnabled:
            print txt

    def raw(self, raw):
        '''Send a raw message to server'''
        # TODO make this thread-safe
        self.sk.send(raw.encode(ENCODING) + '\r\n')

        self.log('> ' + raw)

    def send(self, command, *params, **kwargs):
        """
        Send a message to the server.
        If an argument contains a newline or a space or if it begins with a ':',
        it will be considered as the "last" argument.
        You can also use the "last=..." keyword argument.
        The "last" argument is prefixed with a ':' character in the raw message.
        If a newline is found in the "last" argument, the command is repeated
        with only the "last" argument being split.
        If a line is too long (460 chars), the "last" argument will be broken as well.
        The last argument will also be parsed for format codes, so that the formatting
        can continue on the next line.
        The no_break keyword argument disables breaking of too long lines.
        The no_format keyword argument disables format parsing.
        """

        prefix = command
        last = False
        last_prm = ''
        no_break = False
        no_format = False

        for arg, val in kwargs.items():
            if arg == 'last':
                last_prm = val
            elif arg == 'no_break':
                no_break = val
            elif arg == 'no_format':
                no_format = val
            else:
                raise ValueError(arg)


        for prm in params:
            prm = unicode(prm)
            if not prm: continue
            if (' ' in prm or '\n' in prm or prm[0] == ':') and not last:
                if last_prm:
                    raise ValueError('space or newline in non-last argument')
                last = True
                last_prm = prm
                continue

            if last:
                last_prm += ' ' + prm
            else:
                prefix += ' ' + prm

        if last_prm:
            fgcolor = ''
            bgcolor = ''
            format = []

            for unwrapped_line in last_prm.split('\n'):
                if not unwrapped_line.strip():
                    continue

                if no_break:
                    wraps = [unwrapped_line]
                else:
                    wraps = wrap(unwrapped_line, 460 - len(prefix))

                for wrapped_line in wraps:
                    line = ''.join(format)
                    if fgcolor or bgcolor:
                        line += '\x03' + fgcolor
                        if bgcolor:
                            line += ',' + bgcolor
                    line += wrapped_line
                    self.raw(prefix + ' :' + line.replace('\r',''))

                    if no_format:
                        continue

                    i = 0
                    while i < len(line):
                        char = line[i]
                        i += 1
                        if char == '\x0f': # reset
                            fgcolor = bgcolor = ''
                            format = []
                        elif char in ('\x02', '\x1f', '\x16'):
                            if char in format:
                                format.remove(char)
                            else:
                                format.append(char)
                        elif char == '\x03':
                            match = RE_COLOR.match(line[i-1:])
                            if not match: # uncolor
                                fgcolor = bgcolor = ''
                            else:
                                if match.group(1):
                                    fgcolor = match.group(1)
                                if match.group(2):
                                    bgcolor = match.group(2)
                                i += match.end() - 1
        else:
            self.raw(prefix)

    def ident(self, nick, ident = None,
            realname=__version__, password = None):
        '''Identify with nick, password and real name.
        must be called after connect()'''

        if not ident:
            ident = nick

        self.myself = UserMask(self, nick).user
        self.myself.ident = ident

        self.send('NICK', nick)
        self.send('USER', ident, nick, nick, realname)

        if password:
            self.send('PASS', password)

    def join(self, channel, password=''):
        '''Join a channel'''

        if password:
            self.send('JOIN', channel, password)

        else:
            self.send('JOIN', channel)

    def part(self, channel, reason=''):
        if reason:
            self.send('PART', channel, reason)
        else:
            self.send('PART', channel)

    def message(self, target, text):
        '''Send a message to a nick / channel'''
        self.send('PRIVMSG', target, last=text)

    def notice(self, target, text):
        '''Send a notice to a nick / channel'''
        self.send('NOTICE', target, last=text)

    def topic(self, chan, newtopic):
        '''Change the topic of chan to newtopic'''

        self.send('TOPIC', chan, newtopic, no_break=True)

    def kick(self, chan, user, reason=''):
        '''Kick user on chan'''

        self.send('KICK', chan, user, reason, no_break=True)

    def quit(self, reason=''):
        self.send('QUIT', reason, no_break=True)

    def retrieve_ban_list(self, chan):
        self.bans[irc_lower(chan)] = []
        self.send('MODE', chan, '+b')

    def ctcp_request(self, to, type, value = None):
        type = unicode(type)
        value = unicode(value)
        self.message(to, '\1' + type + (' ' + value if value else '') + '\1')

    def ctcp_reply(self, to, type, value):
        text = '\1' + unicode(type)
        value = unicode(value)

        if value:
            text += ' ' + value

        text += '\1'
        self.notice(to, text)

    def to_unicode(self, string):
        if isinstance(string, unicode):
            return string

        try:
            return string.decode('ascii')
        except UnicodeDecodeError:
            try:
                return string.decode('utf-8')
            except UnicodeDecodeError:
                return string.decode('iso-8859-15', 'replace')

    def parse_modes(self, modestr, targets):
        last = None
        i = 0
        out = []

        for char in modestr:
            if char in ('+', '-'):
                last = char
                continue

            if last is None:
                raise ValueError, "Modes have to begin with + or -"

            if char in self.serverconf.param_modes:
                out.append((last == '+', char, targets[i]))
                i += 1
            else:
                out.append((last == '+', char, None))
        return out

    def _callback(self, name, *parameters):
        for inst in [self] + self.handlers.values():
            f = getattr(inst, name, None)

            if not callable(f):
                continue

            self.log('calling %s() on instance %r' % (name, inst))

            if self.thread_callbacks or getattr(f, 'threaded', None):
                self.log('(threaded)')
                t = threading.Thread(target = f, args = parameters)
                t.daemon = True
                t.start()
            else:
                self.log('(not threaded)')
                f(*parameters)

    def _process_message(self, text):
        self.log('< ' + text)

        prefix = ''

        umask = None

        if text.startswith(':'): # Prefix parsing
            pos = text.find(' ')

            if pos > 0:
                prefix = text[1:pos]
                text   = text[pos + 1:]

                umask = UserMask(self, prefix)

        pos = text.index(' ') # Command name

        if pos > 0:
            cmd  = text[:pos]
            prms =  text[pos + 1:]
        else:
            cmd  = text
            prms = ''

        # Parameters parsing

        params = []
        last   = False

        for prm in prms.split(' '):
            if prm.startswith(':') and not last:
                last = True
                prm = prm[1:]
                params.append(self.to_unicode(prm))

            elif last:
                params[len(params) - 1] += self.to_unicode(' ' + prm)

            else:
                params.append(self.to_unicode(prm))

        cmd = cmd.upper()

        self._callback('on_server_' + cmd.lower(), umask, *params)

        if cmd == 'PING':
            self.send('PONG', params[0])

        elif cmd == 'NICK' and umask:
            olduser = irc_lower(umask.user.nick)
            umask.user.nick = params[0]
            self.users[irc_lower(params[0])] = umask.user
            del self.users[olduser]

        elif cmd == '001': # Welcome server message
            self._callback('on_ready')

        elif cmd == '005': # Server configuration string
            for i, param in enumerate(params):
                if i == len(params) - 1:
                    break

                try:
                    name, value = param.split('=')
                    self.serverconf[name] = value

                except ValueError:
                    self.serverconf[param] = True
                    
                    if param == 'NAMESX':
                        self.send('PROTOCTL', 'NAMESX')

        elif cmd == '367': # Ban list item
            chan = irc_lower(params[1])

            if not chan in self.bans:
                self.bans[chan] = []

            self.bans[chan].append(params[2:])

        elif cmd == '368': # End of ban list
            chan = irc_lower(params[1])
            self._callback('on_banlist_received', params[1], self.bans[chan])

        elif cmd == '353': # Names reply
            channel = params[2]

            for raw_nick in params[3].split():
                modes = [self.serverconf.prefixes_mapping[_]
                    for _ in raw_nick if _ in ('@', '%', '+')]

                nick = raw_nick[len(modes):]
                user = UserMask(self, nick).user
                user.joined(channel)
                user.channel_modes[irc_lower(channel)] = set(modes)

        elif cmd == 'PRIVMSG':
            if params[1].startswith('\1') and params[1].endswith('\1'):
                name = params[1][1:][:-1]
                value = None

                pos = name.find(' ')
                if pos > -1:
                    name, value = name[:pos], name[pos + 1:]

                self._callback('on_ctcp_request', umask, name, value)
                self._callback('on_ctcp_' + name.lower() + '_request', umask, value)
            else:
                self._callback('on_message', umask, *params)

                if self.is_channel(params[0]):
                    self._callback('on_channel_message', umask, *params)

                elif self.is_me(params[0]):
                    self._callback('on_private_message', umask, params[1])

        elif cmd == 'NOTICE' and umask is not None:
            if params[1].startswith('\1') and params[1].endswith('\1'):
                name = params[1][1:][:-1]
                value = None

                pos = name.find(' ')
                if pos > -1:
                    name, value = name[:pos], name[pos + 1:]

                self._callback('on_ctcp_reply', umask, name, value)
                self._callback('on_ctcp_'+ name.lower() + '_reply', umask, value)
            else:
                self._callback('on_notice', umask, *params)

                if self.is_channel(params[0]):
                    self._callback('on_channel_notice', umask, *params)

                elif self.is_me(params[0]):
                    self._callback('on_private_notice', umask, params[1])

        elif cmd == 'MODE' and umask and len(params) > 2 and self.is_channel(params[0]):
            chan = params[0]
            modestr = params[1]
            targets = params[2:]

            for add, mode, value in self.parse_modes(modestr, targets):
                if mode in self.serverconf.user_level_modes:
                    user = UserMask(self, value).user
                    mode_set =  user.channel_modes[irc_lower(chan)]

                    if add:
                        mode_set.add(mode)
                    elif mode in mode_set:
                        mode_set.remove(mode)

        elif umask and self.is_me(umask):
            self._callback('on_self_' + cmd.lower(), *params)

        if cmd in ('JOIN', 'PART', 'KICK'):
            chan = params[0]
            target = (UserMask(self, params[1]) if cmd == 'KICK' else umask)

            if cmd == 'JOIN':
                target.user.joined(chan)
            else:
                target.user.left(chan)
        elif cmd == 'QUIT':
            umask.user.delete()

class UserMask(object):
    maskRegex = re.compile(r'([^!]+)!([^@]+)@(.+)')

    def __init__(self, irc, mask):
        self.irc = irc
        self.nick = ''
        self.ident = ''
        self.host = ''
        self.user = None
        mask = unicode(mask)

        match = self.maskRegex.match(mask)

        if match:
            self.nick, self.ident, self.host = match.groups()
        else:
            self.nick = mask

        if irc_lower(self.nick) in self.irc.users:
            self.user = self.irc.users[irc_lower(self.nick)]

            if self.host and self.host != self.user.host:
                self.user.host = self.host # host can change (mode x)
            if self.ident and not self.user.ident:
                self.user.ident = self.ident
        else:
            self.user = User(self)
            self.irc.users[irc_lower(self.nick)] = self.user

    def __repr__(self):
        return u'<UserMask: %s!%s@%s>' % (self.nick, self.ident, self.host)

    def __unicode__(self):
        return self.nick

class User:
    def __init__(self, mask):
        self.nick = mask.nick
        self.ident = mask.ident
        self.host = mask.host
        self.irc = mask.irc
        self.channels = []
        self.channel_modes = {}
        self.deleted = False
        
        if irc_lower(self.nick) in self.irc.users:
            raise AssertionError, 'OH SHIT!'

    def is_in(self, channel):
        return irc_lower(channel) in map(irc_lower, self.channels)

    def is_ghost_of(self, nick):
        return self.host == UserMask(self.irc, nick).user.host

    def joined(self, channel):
        assert not self.deleted, 'Deleted user'

        if self.is_in(channel):
            return

        self.channels.append(channel)
        self.channel_modes[irc_lower(channel)] = set()

    def left(self, channel):
        assert not self.deleted, 'Deleted user'
        if not self.is_in(channel):
            return

        for chan in self.channels:
            if irc_equals(chan, channel):
                self.channels.remove(chan)

        try:
            del self.channel_modes[irc_lower(channel)]
        except KeyError:
            pass

    def delete(self):

        for chan in self.channels:
            self.left(chan)

        self.deleted = True
        del self.irc.users[irc_lower(self.nick)]

    def __repr__(self):
        return u'<%sUser: %s!%s@%s>' % ('Deleted ' if self.deleted else '',
            self.nick, self.ident, self.host)

    def __unicode__(self):
        return self.nick
