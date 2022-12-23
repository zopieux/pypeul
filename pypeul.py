#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

# pypeul.py
# An IRC client library designed to write bots in a fast and easy way.

# This file is part of pypeul.
#
# Copyright (c) 2010-2012 Mick@el, Zopieux and seirl
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

__version__ = 'Pypeul python IRC client library v0.3.2 by Mick@el & Zopieux'

ENCODING = 'utf-8'

import socket
import threading
import re
import sys
import io
import logging
from collections import namedtuple, UserDict, OrderedDict
from collections.abc import Callable
from textwrap import wrap
import time


# Decorator used to specify that a callbacks needs to be run in a thread
def threaded(func):
    if not func.__name__.lower().startswith('on_'):
        raise TypeError(
                "threaded decorator can only be used on callback functions")

    func.threaded = True
    return func

logger = logging.getLogger(__name__)


def irc_lower(s):
    # TODO: better implementation
    return s.encode('utf-8').lower().decode('utf-8')


def irc_equals(s1, s2):
    return irc_lower(s1) == irc_lower(s2)


class Tags:
    '''
    This class is used to represent mIRC-style formatted text

    Here are a few examples of the syntax :

    >>> Tags.Bold('foo') + 'bar'
    ChunkList([<Chunk('foo', bold)>, <Chunk('bar')>])

    >>> Tags.BoldRed('foo') + 'bar'
    ChunkList([<Chunk('foo', fgcolor='red', bold)>, <Chunk('bar')>])

    >>> Tags.UnderlineRed("This is " + Tags.BoldBlue("SPARTAAAAA!!!"))
    ChunkList([<Chunk('This is ', fgcolor='red', underline)>,
        <Chunk('SPARTAAAAA!!!', fgcolor='blue', bold, underline)>])

    >>> Tags.BoldYellowBlue("This text is yellow on a blue background")
    ChunkList([<Chunk('This text is yellow on a blue background',
        fgcolor='yellow', bgcolor='blue', bold)>])

    The first and second color names are respectively foreground and background
    colors.  Other tags may be put in any other place.  The keywords are
    case-insensitive (Tags.boldred("hello") works as well)

    The result is a ChunkList object that will be automatically converted when
    sent over IRC.  str() can also be used to force the conversion

    The following tags are defined : Bold, Underline, Reverse, Reset

    Some notes about nested tags :
        - child tag will inherit the parent's background color, unless it has
          Reset or Uncolor attribute (or another background color)
        - child tag always has priority over the parent :
            Tags.Red(Tags.Blue("...")) will be blue '''

    RE_COLOR = re.compile(r'\x03(\d{1,2})?(?:,(\d{1,2})?)?')
    colors = {
        'white': '00',
        'black': '01',
        'blue': '02',
        'green': '03',
        'red': '04',
        'brown': '05',
        'purple': '06',
        'orange': '07',
        'yellow': '08',
        'ltgreen': '09',
        'teal': '10',
        'cyan': '11',
        'ltblue': '12',
        'pink': '13',
        'grey': '14',
        'ltgrey': '15'
    }

    color_names = list(colors.keys())
    color_codes = [int(x) for x in colors.values()]

    formats = {
        'reset': '\x0f',
        'uncolor': '\x03',
        'bold': '\x02',
        'underline': '\x1f',
        'reverse': '\x16'
    }

    formats_names = list(formats.keys())
    formats_codes = list(formats.values())

    def color_name_by_code(self, n):
        return self.color_names[self.color_codes.index(n)]

    def format_name_by_code(self, code):
        return self.formats_names[self.formats_codes.index(code)]

    keywords = tuple(colors) + tuple(formats)

    def strip(self, text):
        '''
        Strip all mIRC formatting codes in a string
        '''

        text = Tags.RE_COLOR.sub('', text)
        for val in Tags.formats.values():
            text = text.replace(val, '')

        return text

    def parse(self, text):
        '''
        Parse a mIRC-formatted text into a ChunkList object
        '''

        chunks = []
        chunk = Tags.Chunk()
        i = 0

        while i < len(text):
            char = text[i]

            try:
                fmt = self.format_name_by_code(char)
            except ValueError:
                fmt = None

            if fmt and chunk.text:
                chunks.append(chunk)
                chunk = Tags.Chunk()
                chunk.tags |= chunks[-1].tags - {'reset', 'uncolor'}
                chunk.fgcolor = chunks[-1].fgcolor
                chunk.bgcolor = chunks[-1].bgcolor

            if fmt == 'reset':
                chunk.fgcolor = ''
                chunk.bgcolor = ''
                chunk.tags = set()

            if fmt == 'uncolor':
                match = self.RE_COLOR.search(text[i:])
                fg, bg = match.groups()

                if fg:
                    chunk.fgcolor = self.color_name_by_code(int(fg))
                    if bg:
                        chunk.bgcolor = self.color_name_by_code(int(bg))
                else:
                    chunk.fgcolor = ''
                    chunk.bgcolor = ''
                    chunk.tags.add('uncolor')

                i += len(match.group(0))
                continue

            if fmt:
                if fmt in chunk.tags:
                    chunk.tags.remove(fmt)
                else:
                    chunk.tags.add(fmt)
            else:
                chunk.text += char

            i += 1

        chunks.append(chunk)
        return self.ChunkList(chunks)

    def _next_keyword(self, name):
        found = ''

        for keyword in self.keywords:
            if name.lower().startswith(keyword):
                found = keyword
                name = name[len(keyword):]
                break

        if not found:
            raise AttributeError(name)

        return keyword, name

    def __getattr__(self, name):
        fgcolor = ''
        bgcolor = ''
        formats = set()

        while name:
            keyword, name = self._next_keyword(name)

            if keyword in self.colors:
                if not fgcolor:
                    fgcolor = keyword
                elif not bgcolor:
                    bgcolor = keyword
                else:
                    raise AttributeError("You can't have more than 2 colors !")
            elif keyword in self.formats:
                if keyword in formats:
                    raise AttributeError(
                            "You specified the same format twice !")
                else:
                    formats.add(keyword)
            else:
                raise AttributeError("Invalid keyword : %r" % keyword)

        class Tag:
            def __call__(self, value):
                return Tags.ChunkList([value], fgcolor, bgcolor, formats)

            def __str__(self):
                return Tags.ChunkList(
                        [''], fgcolor, bgcolor, formats).to_string()

            def __add__(self, other):
                return str(self) + str(other)

            def __radd__(self, other):
                return str(other) + str(self)

        return Tag()

    class ChunkList:
        def __init__(self, children=None, fgcolor='', bgcolor='', tags=None):
            children = children or []
            self.children = []

            for child in children:
                if isinstance(child, Tags.Chunk):
                    self.children.append(child)

                elif isinstance(child, Tags.ChunkList):
                    self.children.extend(child.children)
                else:
                    self.children.append(Tags.Chunk(str(child)))

            for child in self.children:
                if 'reset' not in child.tags and 'uncolor' not in child.tags:
                    child.fgcolor = child.fgcolor or fgcolor
                    child.bgcolor = child.bgcolor or bgcolor

                if tags:
                    child.tags |= tags

        def __add__(self, right):
            return Tags.ChunkList([self, right])

        def __radd__(self, left):
            return Tags.ChunkList([left, self])

        def __repr__(self):
            return "<ChunkList(%r)>" % (self.children,)

        def split_lines(self):
            result = []
            curr_chunklist = Tags.ChunkList()

            for chunk in self.children:
                if '\n' not in chunk.text:
                    curr_chunklist.children.append(chunk)
                    continue

                lines = chunk.text.split('\n')
                for i, line in enumerate(lines):
                    newchunk = chunk.copy()
                    newchunk.text = line

                    if i > 0:
                        newchunk.tags -= {'reset', 'uncolor'}
                        result.append(curr_chunklist)
                        curr_chunklist = Tags.ChunkList()

                    curr_chunklist.children.append(newchunk)

            result.append(curr_chunklist)
            return result

        def split_words(self):
            new_chunklist = Tags.ChunkList()

            for chunk in self.children:
                words = chunk.text.split(' ')

                for i, word in enumerate(words):
                    newchunk = chunk.copy()
                    newchunk.text = word + ' '

                    if i == len(words) - 1:
                        newchunk.text = newchunk.text[:-1]
                    new_chunklist.children.append(newchunk)

            return new_chunklist

        def __str__(self):
            return self.to_string(end=True)

        def to_string(self, end=False):
            fg, bg = '', ''
            tags = set()
            ret = ''

            for chunk in self.children:
                for tag in (tags ^ chunk.tags):
                    ret += Tags.formats[tag]

                    if tag == 'reset' or tag == 'uncolor':
                        fg, bg = '', ''
                        if tag == 'reset':
                            tags = set()

                if (fg, bg) != (chunk.fgcolor, chunk.bgcolor):
                    ret += '\x03'

                    if chunk.fgcolor or chunk.bgcolor:
                        ret += Tags.colors[chunk.fgcolor]

                    if chunk.bgcolor and bg != chunk.bgcolor:
                        ret += ',' + Tags.colors[chunk.bgcolor]

                if ret.endswith(Tags.formats['uncolor']) and (
                        chunk.text[:1].isdigit() or
                        chunk.text[:1] == ','):
                    ret += 2 * Tags.formats['bold']  # workaround

                ret += chunk.text

                fg, bg = chunk.fgcolor, chunk.bgcolor
                tags = chunk.tags.copy() - {'reset', 'uncolor'}

            if end:
                if fg or bg:
                    ret += Tags.formats['uncolor']
                for tag in tags - {'uncolor', 'reset'}:
                    ret += Tags.formats[tag]

            return ret

    class Chunk:
        fgcolor = ''
        bgcolor = ''
        tags = None

        def __init__(self, text=''):
            self.text = text
            self.tags = set()

        def copy(self):
            other = Tags.Chunk(self.text)
            other.tags = self.tags.copy()
            other.fgcolor = self.fgcolor
            other.bgcolor = self.bgcolor
            return other

        def __repr__(self):
            attrlist = [repr(self.text)]
            if self.fgcolor:
                attrlist.append('fgcolor=%r' % self.fgcolor)
            if self.bgcolor:
                attrlist.append('bgcolor=%r' % self.bgcolor)

            attrlist.extend(self.tags)

            return '<Chunk(%s)>' % (', '.join(attrlist))

Tags = Tags()


class ServerConfig:
    '''
    This classed is used to allow easy access to the RPL_ISUPPORT line returned
    by most IRC servers, Please see http://www.irc.org/tech_docs/005.html for
    more information.
    '''
    def __init__(self):
        self.info = {
            'CHANMODES': 'b,k,l,psitnm',
            'CHANTYPES': '#',
            'PREFIX': '(ov)@+',
            'MAXLIST': 'beI:10',  # arbitrary
            'MODES': '3',
        }

    def __getitem__(self, item):
        return self.info[item]

    def __setitem__(self, item, value):
        self.info[item] = value

    def __contains__(self, item):
        return item in self.info

    @property
    def chan_prefixes(self):
        """
        Returns the possible channel prefixes characters
        """
        return set(self.info['CHANTYPES'])

    @property
    def chan_modes(self):
        '''
        This is a list of channel modes according to 4 types.
        A = Mode that adds or removes a nick or address to a list. Always has a
        parameter.
        B = Mode that changes a setting and always has a parameter.
        C = Mode that changes a setting and only has a parameter when set.
        D = Mode that changes a setting and never has a parameter.

        Note: Modes of type A return the list when there is no parameter
              present.
        Note: Some clients assumes that any mode not listed is of type D.
        Note: Modes in PREFIX are not listed but could be considered type B.
        '''
        return [set(_) for _ in self.info['CHANMODES'].split(',')]

    @property
    def max_lists_entries(self):
        '''
        Maximum number of entries in the list for each mode.
        '''
        ret = {}
        for token in self.info['MAXLIST'].split(','):
            modes, limit = token.split(':')
            for mode in modes:
                ret[mode] = int(limit)

        return ret

    @property
    def list_modes(self):
        '''
        A set of all type A modes (that add or remove to a list
        such as a ban list)
        '''
        return set(self.max_lists_entries.keys()) | self.chan_modes[0]

    @property
    def prefixes(self):
        '''
        A list of channel modes a person can get and the respective prefix a
        channel or nickname will get in case the person has it. The order of
        the modes goes from most powerful to least powerful. Those prefixes are
        shown in the output of the WHOIS, WHO and NAMES command.

        Note: Some servers only show the most powerful, others may show all of
        them.

        The result is an ordered dict of mode -> prefix
        '''
        left, right = self.info['PREFIX'].split(')')
        return OrderedDict(zip(left[1:], right))

    def mode_for_prefix(self, prefix):
        '''
        Get the mode for the given prefix
        '''
        index = list(self.prefixes.values()).index(prefix[0])
        return list(self.prefixes.keys())[index]

    @property
    def prefixes_modes(self):
        '''
        A set containing all the channel modes a person can get
        '''
        return set(self.prefixes.keys())

    @property
    def max_modes(self):
        '''
        Maximum number of channel modes with a parameter
        allowed for each MODE command.
        '''
        return int(self.info['MODES'])

    @property
    def param_modes(self):
        '''
        A set of all type B modes (which always have a parameter associated)
        '''
        return set(self.chan_modes[1]) | self.prefixes_modes

    @property
    def param_set_modes(self):
        '''
        A set of all type C modes (which always have a parameter when set)
        '''
        return set(self.chan_modes[2])

    @property
    def noparam_modes(self):
        '''
        A set of all type D modes (which never have a parameter associated)
        '''
        return set(self.chan_modes[3])


class IRC:
    def __init__(self, thread_callbacks=False):
        self.thread_callbacks = thread_callbacks
        self.connected = False
        self.enabled = True

        self.bans = IrcDict()
        self.users = IrcDict()
        self.myself = None
        self.serverconf = ServerConfig()
        self.handlers = {}
        self.send_lock = threading.RLock()

        self.fsock = None
        self.waiting_queue = []

        self.reconnect_obj = None

    def is_channel(self, text):
        return text[0:1] in self.serverconf.chan_prefixes

    def is_me(self, user):
        return irc_equals(str(user), str(self.myself))

    def users_in(self, channel):
        return [u for u in self.users.values() if u.is_in(channel)]

    def connect(self, host, port=6667, use_ssl=False):
        '''Etablish a connection to a server'''
        logger.info('Connecting to %s port %d ...', host, port)

        self.host = host
        self.port = port
        self.sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if use_ssl:
            import ssl
            self.sk = ssl.wrap_socket(self.sk)

        self.sk.connect((host, port))
        self.sk.settimeout(512)
        self.fsock = self.sk.makefile('rb')

        logger.info('Connected successfully')
        self.connected = True
        self.enabled = True
        self._callback('on_connected')

    def get_raw_message(self):
            try:
                txt = self.fsock.readline()
            except IOError:
                return None
            if txt == b'':
                return None
            return txt

    def run_loop(self):
        while self.enabled:
            for waiting_msg in self.waiting_queue:
                if waiting_msg is None:
                    return
                try:
                    self._process_message(waiting_msg)
                except:
                    logger.exception(
                            "Exception raised while processing a message")

            self.waiting_queue = []

            txt = self.get_raw_message()
            if txt is None:
                break
            try:
                self._process_message(txt)
            except:
                logger.exception("Exception raised while processing a message")

    def run(self):
        self.run_loop()
        self.connected = False
        self.enabled = False
        logger.info('Disconnected from server.')
        self._callback('on_disconnected')

        if self.reconnect_obj:
            i = 0
            while True:
                if callable(self.reconnect_obj):
                    t = self.reconnect_obj(i)
                elif isinstance(self.reconnect_obj, (int, float)):
                    t = self.reconnect_obj
                else:
                    raise TypeError("reconnect: not a number nor a callable")

                logger.info('Trying to reconnect in {}s.'.format(t))
                time.sleep(t)
                i += 1

                try:
                    self.connect(self.host, self.port)
                    self.ident(self.myself.nick, self.myself.ident,
                               self.myself.realname, self.myself.password)
                    break
                except Exception as e:
                    logger.error('Reconnect failed: {}.'.format(e))

            self.run()

    def run_threaded(self):
        thread = threading.Thread(target=self.run)
        thread.setDaemon(True)
        thread.start()

        return thread

    def raw(self, raw):
        '''
        Send a raw string to server

        This method is thread-safe
        '''
        with self.send_lock:
            self.sk.send(raw.encode(ENCODING) + b'\r\n')

            logger.debug('> ' + raw)

    def _get_prefix(self, params):
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

        prefix = prefix[:-1]  # remove trailing space
        return prefix

    def send(self, *params, last=''):
        """
        Send a single-line message to the server.

        Only the "last" keywork argument can contain spaces and is prefixed
        with a ':' character in the raw message. Newlines will be replaced with
        a space.

        Other arguments can not contain space, newlines or begin with a ':'
        Every argument will be converted into a string using str()
        """

        prefix = self._get_prefix(params)

        if isinstance(last, Tags.ChunkList):
            last = last.to_string()
        else:
            last = str(last)

        last = ' '.join(x.strip('\r') for x in last.split('\n'))

        if last:
            self.raw(prefix + ' :' + last)
        else:
            self.raw(prefix)

    def send_multi(self, *params, last='', no_break=False):
        """
        Send a command multiple times to the server.
        For each newline in the last argument, the command will be repeated.

        The 'last' argument will be parsed for format codes and will be split
        into words to allow intelligent line breaking of too long line.
        Whenever possible, the line breaking algorithm will cut at a chunk
        boundary (at the end of a word or before a formatting tag)

        This behaviour can be disabled by passing the no_break=True argument.
        Keep in mind that by doing so, lines that are too long will be
        truncated by the IRC server.

        Every other argument will be converted into a string using str()

        This method is thread-safe
        """

        prefix = self._get_prefix(params)

        if no_break:
            if isinstance(last, Formats.ChunkList):
                last = last.to_string()
            else:
                last = str(last)

            with self.send_lock:
                for line in last.split('\n'):
                    self.raw(prefix + ' :' + line)
            return

        # FIXME: might be too small if you have a long nickname
        max_limit = 450 - len(prefix)  # forced break at this limit

        if not isinstance(last, Tags.ChunkList):
            last = Tags.parse(str(last))

        last = last.split_words()
        lines = []

        for line in last.split_lines():
            next_chunks = line.children[:]

            while next_chunks:
                nb_chunks = len(next_chunks)

                # try to fit the maximum number of complete chunks
                for complete_chunks in range(nb_chunks, 0, -1):
                    left_chunks = Tags.ChunkList(next_chunks[:complete_chunks])
                    length = len(str(left_chunks))

                    if length <= max_limit:  # it fits!
                        break

                if length > max_limit:
                    # looks like we'll need to break the first chunk
                    chunk = next_chunks[0]
                    to_chop = length - max_limit
                    half1 = chunk.copy()
                    half2 = chunk.copy()
                    half1.text = chunk.text[:-to_chop]
                    half2.text = chunk.text[-to_chop:]
                    next_chunks[0] = half1
                    next_chunks.insert(1, half2)

                chunklist = Tags.ChunkList(next_chunks[:complete_chunks])
                lines.append(chunklist.to_string())
                next_chunks = next_chunks[complete_chunks:]

        with self.send_lock:
            for line in lines:
                self.raw(prefix + ' :' + line)

    def ident(self, nick, ident=None,
            realname=__version__, password=None):
        '''Identify with nick, password and real name.
        must be called after connect()'''

        if not ident:
            ident = nick

        self.myself = UserMask(self, nick).user
        self.myself.ident = ident
        self.myself.realname = realname
        self.myself.password = password

        if password:
            self.send('PASS', password)

        self.nick(nick)
        self.send('USER', ident, nick, nick, last=realname)

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

    def action(self, target, text):
        '''Send an action to a nick / channel'''
        self.message(target, '\x01ACTION ' + text + '\x01')

    def notice(self, target, text):
        '''Send a notice to a nick / channel'''
        self.send_multi('NOTICE', target, last=text)

    def topic(self, chan, newtopic):
        '''Change the topic of chan to newtopic'''
        self.send('TOPIC', chan, last=newtopic)

    def kick(self, chan, user, reason=''):
        '''Kick user on chan'''
        self.send('KICK', chan, user, last=reason)

    def invite(self, chan, user):
        '''Invite an user on a channel'''
        self.send('INVITE', chan, user)

    def quit(self, reason=''):
        self.send('QUIT', last=reason)

    def set_reconnect(self, obj):
        '''If 'obj' is a number, the bot will try to reconnect every 'obj'
        seconds after its disconnection.
        If 'obj' is a callable, it will be called at each disconnection with
        the number of reconnections attempts since the beginning.

        Examples:

        bot.set_reconnect(15)
        # Trying to reconnect in 15s...
        # Trying to reconnect in 15s...
        # Trying to reconnect in 15s...
        # Trying to reconnect in 15s...

        bot.set_reconnect(lambda x: max(30 * (2 ** x), 1800))
        # Trying to reconnect in 30s...
        # Trying to reconnect in 60s...
        # Trying to reconnect in 120s...
        # Trying to reconnect in 240s...
        '''

        self.reconnect_obj = obj

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
                and i < self.serverconf.max_modes and j < len(m):

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

    def get_list(self, target, getcmd, listname, timeout=0):
        '''
        Synchronously retrieves a list of items and returns it.
        If the timeout is set, this function won't wait for the endoflist
        signal and will return the list retrieved so far.
        '''
        l = []
        self.send(*getcmd)
        start_time = time.time()
        while True:
            if timeout != 0 and time.time() > start_time + timeout:
                break
            txt = self.get_raw_message()
            if txt is None:
                self.waiting_queue.append(txt)
                break
            umask, cmd, params = self._parse_message(txt)
            if cmd == listname and params[1] == target:
                l.append(params[2:])
            elif cmd == 'endof' + listname and target == params[1]:
                break
            else:
                self.waiting_queue.append(txt)
        return l

    def get_banlist(self, chan, timeout=0):
        banlist = self.get_list(chan, ('MODE', chan, '+b'), 'banlist',
                timeout=timeout)
        if not chan in self.bans:
            self.bans[chan] = []
        self.bans[chan] = banlist
        return banlist

    def ctcp_request(self, to, type, value=''):
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
            if char in '+-':
                last = char
                continue

            if last is None:
                raise ValueError("Modes have to begin with + or -")

            param_modes = (self.serverconf.param_modes |
                           self.serverconf.list_modes)
            if last == '+':
                param_modes |= self.serverconf.param_set_modes

            if char in param_modes:
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

            logger.debug('calling %s() on instance %r' % (name, inst))

            if self.thread_callbacks or getattr(f, 'threaded', None):
                t = threading.Thread(target=f, args=parameters)
                t.daemon = True
                t.start()
            else:
                f(*parameters)

    def _parse_message(self, text):
        text = text.strip(b'\r\n')
        text = list(map(self.to_unicode, text.split(b' ')))
        logger.debug('< ' + ' '.join(text))

        prefix = ''

        umask = None

        if text[0].startswith(':'):  # Prefix parsing
            prefix = text[0][1:]
            text = text[1:]

            umask = UserMask(self, prefix)

        if len(text) > 1:
            cmd = text[0]
            prms = text[1:]
        else:
            cmd = text[0]
            prms = []

        # Parameters parsing

        params = []
        last = False

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
        return umask, cmd, params

    def _process_message(self, text):
        umask, cmd, params = self._parse_message(text)

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

        elif cmd == 'featurelist':  # Server configuration string
            for i, param in enumerate(params[1:]):
                if i == len(params):
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
                modes = [self.serverconf.mode_for_prefix(_) for _ in raw_nick
                         if _ in self.serverconf.prefixes.values()]

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
                    self._callback('on_ctcp_' + name.lower() + '_request',
                            umask, value)
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
                self._callback('on_ctcp_' + name.lower() + '_reply', umask,
                        value)
            else:
                self._callback('on_notice', umask, *params)

                if self.is_channel(params[0]):
                    self._callback('on_channel_notice', umask, *params)

                elif self.is_me(params[0]):
                    self._callback('on_private_notice', umask, params[1])

        elif (cmd == 'MODE' and umask and len(params) > 2 and
             self.is_channel(params[0])):
            chan = params[0]
            modestr = params[1]
            targets = params[2:]

            for add, mode, value in self.parse_modes(modestr, targets):
                if mode in (self.serverconf.prefixes_modes
                            | self.serverconf.list_modes
                            - set(self.serverconf.max_lists_entries)):
                    user = UserMask(self, value).user
                    mode_set = user.modes_in(chan)

                    if add:
                        mode_set.add(mode)
                    elif mode in mode_set:
                        mode_set.remove(mode)

        elif umask and self.is_me(umask):
            self._callback('on_self_' + cmd.lower(), *params)


class UserMask:
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
                self.user.host = self.host  # host can change (mode x)
            if self.ident and not self.user.ident:
                self.user.ident = self.ident
        else:
            self.user = User(self)
            self.irc.users[self.nick] = self.user

    def __repr__(self):
        return '<UserMask: {0}!{1}@{2}>'.format(self.nick, self.ident,
                self.host)

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
            logger.error('''Tried instanciating multiple User instances for the
                    same user.''')

    def is_in(self, channel):
        return channel in self.channels

    def is_ghost_of(self, nick):
        return self.host == UserMask(self.irc, nick).user.host

    def modes_in(self, channel):
        return self.channels[channel]

    def joined(self, channel):
        if self.deleted:
            logger.error("joined() called on a deleted user")
            return

        if self.is_in(channel):
            return

        self.channels[channel] = set()

    def left(self, channel):
        if self.deleted:
            logger.error("left() called on a deleted user")
            return

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
        return '<{0}User: {1}!{2}@{3}>'.format('Deleted ' if self.deleted else
                '', self.nick, self.ident, self.host)

    def __str__(self):
        return self.nick


class NormalizedDict(UserDict):
    function = staticmethod(str.lower)

    def __init__(self, *args, **kwargs):
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
    "432": "erroneusnickname",  # Thiss iz how its speld in thee RFC.
    "433": "nicknameinuse",
    "436": "nickcollision",
    "437": "unavailresource",   # "Nick temporally unavailable"
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
    "465": "yourebannedcreep",  # I love this one...
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
