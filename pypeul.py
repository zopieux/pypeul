#!/usr/bin/env python3
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

__version__ = 'Pypeul python IRC client library v0.2 by Mick@el & Zopieux'

ENCODING = 'utf-8'

import socket
import threading
import re
import sys
from collections import namedtuple, Callable, UserDict
from textwrap import wrap

RE_COLOR = re.compile(r'\x03(\d{1,2})?(?:,(\d{1,2})?)?')

# Decorator used to specify that a callbacks needs to be run in a thread
def threaded(func):
    if not func.__name__.lower().startswith('on_'):
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
            if isinstance(other, str):
                return str(self) + other
            elif isinstance(other, _tags.callable_tag):
                return str(self) + str(other)
            else:
                raise TypeError

        def __radd__(self, other):
            if isinstance(other, str):
                return other + str(self)
            elif isinstance(other, _tags.callable_tag):
                return str(other) + str(self)
            else:
                raise TypeError

        def __str__(self):
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
        'MODES' : '3',
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
    def mode_targets(self):
        return int(self.info['MODES'])

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

        self.bans = IrcDict()
        self.users = IrcDict()
        self.myself = None
        self.serverconf = ServerConfig()
        self.handlers = {}

    def is_channel(self, text):
        return text.startswith('#') or text.startswith('&')

    def is_me(self, user):
        return irc_equals(str(user), str(self.myself))

    def users_in(self, channel):
        return [u for u in self.users.values() if u.is_in(channel)]

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
        file = self.sk.makefile('rb')

        while self.enabled:
            try:
                txt = file.readline()
            except IOError:
                break

            if txt == '':
                break

            self._process_message(txt.strip(b'\r\n'))

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
            print(txt)

    def raw(self, raw):
        '''Send a raw message to server'''
        # TODO make this thread-safe
        self.sk.send(raw.encode(ENCODING) + b'\r\n')

        self.log('> ' + raw)

    def send(self, *params, last=''):
        """
        Send a message to the server.
        Arguments can not contain space, newlines or begin with a ':'

        Only the "last" keywork argument can contain spaces and is prefixed
        with a ':' character in the raw message.
        """

        prefix = ''

        for prm in params:
            prm = str(prm)

            if not prm:
                continue

            if '\n' in prm or '\r' in prm:
                raise ValueError("newlines not allowed in parameters")

            if ' ' in prm or prm[0] == ':':
                raise ValueError("space or ':' prefix in non-last argument")

            prefix += prm + ' '

        prefix = prefix[:-1] # remove trailing space

        if '\n' in last or '\r' in last:
            raise ValueError("newlines not allowed in last argument")

        if last:
            self.raw(prefix + ' :' + last)
        else:
            self.raw(prefix)

    def send_multi(self, *params, last='', no_break=False, no_format=False):
        """
        Send a command multiple times to the server.
        For each newline in the last argument, the command will be repeated.

        If the last argument is too long, it will be split into multiple lines
        unless the no_break argument is set.

        The effective formatting at the end of each line will be repeated on the
        beginning of the next line unless the no_format argument is set.
        """

        if last:
            fgcolor = ''
            bgcolor = ''
            format = []

            for unwrapped_line in last.split('\n'):
                if not unwrapped_line.strip():
                    continue

                if no_break:
                    wraps = [unwrapped_line]
                else:
                    wraps = wrap(unwrapped_line, 460 - len(' '.join(params)))

                for wrapped_line in wraps:
                    line = ''.join(format)

                    if fgcolor or bgcolor:
                        line += '\x03' + fgcolor

                        if bgcolor:
                            line += ',' + bgcolor
                    line += wrapped_line

                    self.send(*params, last=line.replace('\r',''))

                    if no_format:
                        continue

                    i = 0
                    while i < len(line):
                        char = line[i]
                        i += 1

                        if char == Tags.Reset:
                            fgcolor = bgcolor = ''
                            format = []
                        elif char in Tags.tags.values():
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
            self.send(*params)

    def ident(self, nick, ident = None,
            realname=__version__, password = None):
        '''Identify with nick, password and real name.
        must be called after connect()'''

        if not ident:
            ident = nick

        self.myself = UserMask(self, nick).user
        self.myself.ident = ident

        self.nick(nick)
        self.send('USER', ident, nick, nick, last=realname)

        if password:
            self.send('PASS', password)

    def nick(self, nick):
        self.send('NICK', nick)

    def join(self, channel, password=''):
        '''Join a channel'''
        self.send('JOIN', channel, password)

    def part(self, channel, reason=''):
        self.send('PART', channel, last=reason)

    def message(self, target, text):
        '''Send a message to a nick / channel'''
        self.send_multi('PRIVMSG', target, last=text)

    def notice(self, target, text):
        '''Send a notice to a nick / channel'''
        self.send_multi('NOTICE', target, last=text)

    def topic(self, chan, newtopic):
        '''Change the topic of chan to newtopic'''

        self.send('TOPIC', chan, last=newtopic)

    def kick(self, chan, user, reason=''):
        '''Kick user on chan'''

        self.send('KICK', chan, user, last=reason)

    def quit(self, reason=''):
        self.send('QUIT', last=reason)

    def set_modes(self, target, *modes):
        """usage: set_modes('#foo', ('-o', 'Foo2'), ('+l', '30'), '-k')"""

        def _key(i):
            if isinstance(i, str):
                name = i
                val = ''
            else:
                name, val = i

            return (not bool(val), name, val)

        m = tuple(sorted(modes, key=_key))

        if not m:
            return

        j = 0

        while j < len(m):
            cur_sign = None
            modenames = ''
            modevals = []

            i = 0

            while len(target + modenames + ' '.join(modevals)) < 450 \
                and i < self.serverconf.mode_targets and j < len(m):

                if isinstance(m[j], str):
                    name = m[j]
                    val = None
                else:
                    name, val = m[j]

                if cur_sign != name[0]:
                    cur_sign = name[0]
                    modenames += name[0]

                modenames += name[1:]

                if val:
                    modevals += [val]

                i += 1
                j += 1

            self.send('MODE', target, modenames, *modevals)

    def retrieve_ban_list(self, chan):
        self.bans[chan] = []
        self.send('MODE', chan, '+b')

    def ctcp_request(self, to, type, value = None):
        type = str(type)
        value = str(value)
        self.message(to, '\1' + type + (' ' + value if value else '') + '\1')

    def ctcp_reply(self, to, type, value):
        text = '\1' + str(type)
        value = str(value)

        if value:
            text += ' ' + value

        text += '\1'
        self.notice(to, text)

    def to_unicode(self, string):
        if isinstance(string, str):
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
                raise ValueError("Modes have to begin with + or -")

            if char in self.serverconf.param_modes:
                out.append((last == '+', char, targets[i]))
                i += 1
            else:
                out.append((last == '+', char, None))
        return out

    def _callback(self, name, *parameters):
        for inst in [self] + list(self.handlers.values()):
            f = getattr(inst, name, None)

            if not isinstance(f, Callable):
                continue

            self.log('calling %s() on instance %r' % (name, inst))

            if self.thread_callbacks or getattr(f, 'threaded', None):
                t = threading.Thread(target = f, args = parameters)
                t.daemon = True
                t.start()
            else:
                f(*parameters)

    def _process_message(self, text):
        text = list(map(self.to_unicode, text.split(b' ')))
        self.log('< ' + ' '.join(text))

        prefix = ''

        umask = None

        if text[0].startswith(':'): # Prefix parsing
            prefix = text[0][1:]
            text   = text[1:]

            umask = UserMask(self, prefix)

        if len(text) > 1:
            cmd  = text[0]
            prms = text[1:]
        else:
            cmd  = text[0]
            prms = []

        # Parameters parsing

        params = []
        last   = False

        for prm in prms:
            if prm.startswith(':') and not last:
                last = True
                prm = prm[1:]
                params.append(prm)

            elif last:
                params[len(params) - 1] += ' ' + prm

            else:
                params.append(prm)

        cmd = numeric_events.get(cmd, cmd.upper())

        if cmd in ('JOIN', 'PART', 'KICK'):
            self._callback('on_pre_server_' + cmd.lower(), umask, *params)

            chan = params[0]
            target = (UserMask(self, params[1]) if cmd == 'KICK' else umask)

            if cmd == 'JOIN':
                target.user.joined(chan)
            else:
                target.user.left(chan)
        elif cmd == 'QUIT':
            umask.user.delete()

        self._callback('on_server_' + cmd.lower(), umask, *params)

        if cmd == 'PING':
            self.send('PONG', last=params[0])

        elif cmd == 'NICK' and umask:
            oldnick, newnick = umask.user.nick, params[0]
            self.users.rename_key(oldnick, newnick)
            umask.user.nick = newnick

        elif cmd == 'welcome':
            self._callback('on_ready')

        elif cmd == 'featurelist': # Server configuration string
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

        elif cmd == 'banlist':
            chan = params[1]

            if not chan in self.bans:
                self.bans[chan] = []

            self.bans[chan].append(params[2:])

        elif cmd == 'endofbanlist':
            chan = params[1]
            self._callback('on_banlist_received', chan, self.bans[chan])

        elif cmd == 'namreply':
            channel = params[2]

            for raw_nick in params[3].split():
                modes = [self.serverconf.prefixes_mapping[_]
                    for _ in raw_nick if _ in ('@', '%', '+')]

                nick = raw_nick[len(modes):]
                user = UserMask(self, nick).user
                user.joined(channel)
                user.channels[channel] = set(modes)

        elif cmd == 'PRIVMSG':
            if params[1].startswith('\1') and params[1].endswith('\1'):
                name = params[1][1:][:-1]
                value = None

                pos = name.find(' ')
                if pos > -1:
                    name, value = name[:pos], name[pos + 1:]

                if name == 'ACTION':
                    self._callback('on_action', umask, params[0], value)
                else:
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
                    mode_set =  user.modes_in(chan)

                    if add:
                        mode_set.add(mode)
                    elif mode in mode_set:
                        mode_set.remove(mode)

        elif umask and self.is_me(umask):
            self._callback('on_self_' + cmd.lower(), *params)


class UserMask(object):
    maskRegex = re.compile(r'([^!]+)!([^@]+)@(.+)')

    def __init__(self, irc, mask):
        self.irc = irc
        self.nick = ''
        self.ident = ''
        self.host = ''
        self.user = None
        mask = str(mask)

        match = self.maskRegex.match(mask)

        if match:
            self.nick, self.ident, self.host = match.groups()
        else:
            self.nick = mask

        if self.nick in self.irc.users:
            self.user = self.irc.users[self.nick]

            if self.host and self.host != self.user.host:
                self.user.host = self.host # host can change (mode x)
            if self.ident and not self.user.ident:
                self.user.ident = self.ident
        else:
            self.user = User(self)
            self.irc.users[self.nick] = self.user

    def __repr__(self):
        return '<UserMask: {0}!{1}@{2}>'.format(self.nick, self.ident, self.host)

    def __str__(self):
        return self.nick

class User:
    def __init__(self, mask):
        self.nick = mask.nick
        self.ident = mask.ident
        self.host = mask.host
        self.irc = mask.irc
        self.channels = IrcDict()
        self.deleted = False
        
        if self.nick in self.irc.users:
            raise AssertionError('This is not supposed to happen.')

    def is_in(self, channel):
        return channel in self.channels

    def is_ghost_of(self, nick):
        return self.host == UserMask(self.irc, nick).user.host

    def modes_in(self, channel):
        return self.channels[channel]

    def joined(self, channel):
        assert not self.deleted, 'Deleted user'

        if self.is_in(channel):
            return

        self.channels[channel] = set()

    def left(self, channel):
        assert not self.deleted, 'Deleted user'
        if not self.is_in(channel):
            return
        try:
            del self.channels[channel]
        except KeyError:
            pass

    def delete(self):
        self.channels = IrcDict()
        self.deleted = True
        del self.irc.users[self.nick]

    def __repr__(self):
        return '<{0}User: {1}!{2}@{3}>'.format('Deleted ' if self.deleted else '',
            self.nick, self.ident, self.host)

    def __str__(self):
        return self.nick

class NormalizedDict(UserDict):
    function = staticmethod(str.lower)

    def __init__(self, *args,  **kwargs):
        self._map = {}
        super(NormalizedDict, self).__init__(*args, **kwargs)

    def __contains__(self, key):
        return self.function(key) in self._map

    def __getitem__(self, key):
        return self.data[self._map[self.function(key)]]

    def __setitem__(self, key, value):
        if key in self:
            self.data[self._map[self.function(key)]] = value
        else:
            self._map[self.function(key)] = key
            self.data[key] = value

    def __delitem__(self, key):
        del self.data[self._map[self.function(key)]]
        del self._map[self.function(key)]

    def rename_key(self, oldkey, newkey):
        val = self[oldkey]
        del self[oldkey]
        self[newkey] = val

class IrcDict(NormalizedDict):
    function = staticmethod(irc_lower)

numeric_events = {
    "001": "welcome",
    "002": "yourhost",
    "003": "created",
    "004": "myinfo",
    "005": "featurelist",
    "200": "tracelink",
    "201": "traceconnecting",
    "202": "tracehandshake",
    "203": "traceunknown",
    "204": "traceoperator",
    "205": "traceuser",
    "206": "traceserver",
    "207": "traceservice",
    "208": "tracenewtype",
    "209": "traceclass",
    "210": "tracereconnect",
    "211": "statslinkinfo",
    "212": "statscommands",
    "213": "statscline",
    "214": "statsnline",
    "215": "statsiline",
    "216": "statskline",
    "217": "statsqline",
    "218": "statsyline",
    "219": "endofstats",
    "221": "umodeis",
    "231": "serviceinfo",
    "232": "endofservices",
    "233": "service",
    "234": "servlist",
    "235": "servlistend",
    "241": "statslline",
    "242": "statsuptime",
    "243": "statsoline",
    "244": "statshline",
    "250": "luserconns",
    "251": "luserclient",
    "252": "luserop",
    "253": "luserunknown",
    "254": "luserchannels",
    "255": "luserme",
    "256": "adminme",
    "257": "adminloc1",
    "258": "adminloc2",
    "259": "adminemail",
    "261": "tracelog",
    "262": "endoftrace",
    "263": "tryagain",
    "265": "n_local",
    "266": "n_global",
    "300": "none",
    "301": "away",
    "302": "userhost",
    "303": "ison",
    "305": "unaway",
    "306": "nowaway",
    "311": "whoisuser",
    "312": "whoisserver",
    "313": "whoisoperator",
    "314": "whowasuser",
    "315": "endofwho",
    "316": "whoischanop",
    "317": "whoisidle",
    "318": "endofwhois",
    "319": "whoischannels",
    "321": "liststart",
    "322": "list",
    "323": "listend",
    "324": "channelmodeis",
    "329": "channelcreate",
    "331": "notopic",
    "332": "currenttopic",
    "333": "topicinfo",
    "341": "inviting",
    "342": "summoning",
    "346": "invitelist",
    "347": "endofinvitelist",
    "348": "exceptlist",
    "349": "endofexceptlist",
    "351": "version",
    "352": "whoreply",
    "353": "namreply",
    "361": "killdone",
    "362": "closing",
    "363": "closeend",
    "364": "links",
    "365": "endoflinks",
    "366": "endofnames",
    "367": "banlist",
    "368": "endofbanlist",
    "369": "endofwhowas",
    "371": "info",
    "372": "motd",
    "373": "infostart",
    "374": "endofinfo",
    "375": "motdstart",
    "376": "endofmotd",
    "377": "motd2",        # 1997-10-16 -- tkil
    "381": "youreoper",
    "382": "rehashing",
    "384": "myportis",
    "391": "time",
    "392": "usersstart",
    "393": "users",
    "394": "endofusers",
    "395": "nousers",
    "401": "nosuchnick",
    "402": "nosuchserver",
    "403": "nosuchchannel",
    "404": "cannotsendtochan",
    "405": "toomanychannels",
    "406": "wasnosuchnick",
    "407": "toomanytargets",
    "409": "noorigin",
    "411": "norecipient",
    "412": "notexttosend",
    "413": "notoplevel",
    "414": "wildtoplevel",
    "421": "unknowncommand",
    "422": "nomotd",
    "423": "noadmininfo",
    "424": "fileerror",
    "431": "nonicknamegiven",
    "432": "erroneusnickname", # Thiss iz how its speld in thee RFC.
    "433": "nicknameinuse",
    "436": "nickcollision",
    "437": "unavailresource",  # "Nick temporally unavailable"
    "441": "usernotinchannel",
    "442": "notonchannel",
    "443": "useronchannel",
    "444": "nologin",
    "445": "summondisabled",
    "446": "usersdisabled",
    "451": "notregistered",
    "461": "needmoreparams",
    "462": "alreadyregistered",
    "463": "nopermforhost",
    "464": "passwdmismatch",
    "465": "yourebannedcreep", # I love this one...
    "466": "youwillbebanned",
    "467": "keyset",
    "471": "channelisfull",
    "472": "unknownmode",
    "473": "inviteonlychan",
    "474": "bannedfromchan",
    "475": "badchannelkey",
    "476": "badchanmask",
    "477": "nochanmodes",  # "Channel doesn't support modes"
    "478": "banlistfull",
    "481": "noprivileges",
    "482": "chanoprivsneeded",
    "483": "cantkillserver",
    "484": "restricted",   # Connection is restricted
    "485": "uniqopprivsneeded",
    "491": "nooperhost",
    "492": "noservicehost",
    "501": "umodeunknownflag",
    "502": "usersdontmatch",
}
