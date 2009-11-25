#!/usr/bin/python

# Copyright 2008,2009 Peter Poeml
#
#     This program is free software; you can redistribute it and/or
#     modify it under the terms of the GNU General Public License version 2
#     as published by the Free Software Foundation;
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program; if not, write to the Free Software
#     Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
#
#
#
# Analyze Apache logfiles in order to count downloads
#
#
# This script parses a MirrorBrain-enhanced access_log and does the following:
#   - a little ring buffer filters requests recurring within a sliding time window (keyed by ip+url+referer+user-agent)
#   - strip trailing http://... cruft
#   - remove duplicated slashes
#   - remove accidental query strings
#   - remove a possible .metalink suffix
#   - remove the /files/ prefix
# 
# It applies filtering by
#   - status code being 200 or 302
#   - requests must be GET
#   - bouncer's IP which keeps coming back to download all files (from OOo)
# 
# It also captures the country where the client requests originate from.
#
# This script uses Python generators, which means that it doesn't allocate
# memory according to the log size. It rather works like a Unix pipe.
# (The implementation of the generator pipeline is based on David Beazley's
# PyCon UK 08 great talk about generator tricks for systems programmers.)
#
# 
# I baked a first regexp which is able to parse most (OpenOffice.org) requests
# from /stable and /extended. There are some exceptions (language code with 3
# letters) and I didn't take care of /localized yet.
# 
# The script should serve as model implementation for the Apache module which
# does the same in realtime.
#
#
# Usage: 
# ./dlcount.py /var/log/apache2/download.services.openoffice.org/2009/11/download.services.openoffice.org-20091123-access_log.bz2 | sort -u
#
# Uncompressed, gzip or bzip2 compressed files are transparently opened.
# 
#
# 


__version__='0.9'
__author__='Peter Poeml <poeml@cmdline.net>'
__copyright__='Peter poeml <poeml@cmdline.net>'
__license__='GPLv2'
__url__='http://mirrorbrain.org/'


import re

try:
    set
except NameError:
    from sets import Set as set     # Python 2.3 fallback

try:
    sorted
except NameError:
    def sorted(in_value):           # Python 2.3 fallback
        "A naive implementation of sorted"
        out_value = list(in_value)
        out_value.sort()
        return out_value


def gen_open(filenames): 
    """Open a sequence of filenames"""
    import gzip, bz2 
    for name in filenames: 
        if name.endswith(".gz"): 
             yield gzip.open(name) 
        elif name.endswith(".bz2"): 
             yield bz2.BZ2File(name) 
        else: 
             yield open(name) 

def gen_cat(sources): 
    """Concatenate items from one or more 
    source into a single sequence of items"""
    for s in sources: 
        for item in s: 
            yield item 


def gen_grep(pat, lines): 
    import re 
    patc = re.compile(pat) 
    for line in lines: 
        if patc.search(line): yield line 

def gen_fragments(pat, lines): 
    """Generate a sequence of line fragments, according to
    a given regular expression"""
    import re 
    patc = re.compile(pat) 
    for line in lines: 
        m = patc.match(line)
        if m:
            yield m.groups()


class RingBuffer:
    """Here is a simple circular buffer, or ring buffer, implementation in
    Python. It is a first-in, first-out (FIFO) buffer with a fixed size.

    Here is an example where the buffer size is 4. Ten integers, 0-9, are
    inserted, one at a time, at the end of the buffer. Each iteration, the first
    element is removed from the front of the buffer.
    
    buf = RingBuffer(4)
    for i in xrange(10):
        buf.append(i)
        print buf.get()
    
    
    Here are the results:
    
    [None, None, None, 0]
    [None, None, 0, 1]
    [None, 0, 1, 2]
    [0, 1, 2, 3]
    [1, 2, 3, 4]
    [2, 3, 4, 5]
    [3, 4, 5, 6]
    [4, 5, 6, 7]
    [5, 6, 7, 8]
    [6, 7, 8, 9]
    
    from http://www.saltycrane.com/blog/2007/11/python-circular-buffer/
    """
    def __init__(self, size):
        self.data = [None for i in xrange(size)]

    def append(self, x):
        self.data.pop(0)
        self.data.append(x)

    def get(self):
        return self.data


def readconf(filename):
    """we'd need Apache's config parser here..."""
    known_directives = ['StatsDupWindow', 'StatsIgnoreIP', 'StatsPreFilter', 'StatsCount', 'StatsPostFilter']
    known_directives_lower = [ i.lower() for i in known_directives ]

    # dictionary to hold the config
    # each item is a list
    cf = {}
    for i in known_directives_lower:
        cf[i] = list()

    for line in open(filename):
        line = line.strip()
        if line.startswith('#'):
            continue

        d = line.split(None, 1)
        if not len(d):
            continue
        if d[0].lower() not in known_directives_lower:
            print 'not found:', d[0]
            continue
        d, val = d
        d = d.lower()

        print d, val
        cf[d].append(val)

    cf['statsdupwindow'] = int(cf['statsdupwindow'][0])

    return cf
    


def main():
    """
    Create a generator pipeline for the matching log file lines
    and process them.
    """
    import re
    import sys
    import hashlib

    if not len(sys.argv[2:]):
        sys.exit('Usage: dlcount CONFIGFILE LOGFILE [LOGFILE ...]')

    conf = readconf(sys.argv[1])
    print; print
    import pprint
    pprint.pprint(conf)



    matchlist = [ 
        # FIXME: grab list of regexp from config

    ]
    re_matchlist = []
    for match, sub in matchlist:
        re_matchlist.append((re.compile(match), sub, match))


    known = RingBuffer(conf['statsdupwindow'])

    filenames = sys.argv[2:]
    logfiles = gen_open(filenames)
    loglines = gen_cat(logfiles)

    # 123.123.123.123 - - [23/Nov/2009:18:19:14 +0100] "GET /files/stable/3.1.1/OOo_3.1.1_MacOSXIntel_install_en-US.dmg HTTP/1.1" 302 399 "http://download.openoffice.org/all_rc.html" "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; Media Center PC 5.0; .NET CLR 1.1.4322; .NET CLR 3.5.30729; .NET CLR 3.0.30618)" ftp.astral.ro r:country 913 844 EU:RO ASN:9050 P:92.81.0.0/16 size:24661382 -
    # 200 is returned for files that are not on mirrors, and for metalinks
    pat = r'^(\S+).+"GET (\S*) HTTP.*" (200|302) [^"]+ "([^"]*)" "([^"]*)".* \w\w:(\w\w) ASN:'
    reqs = gen_fragments(pat, loglines)

    # pretreatment (filtering, fixups), applied in order
    # FIXME: read prefilter expressions here


    for req in reqs:

        (ip, url, status, referer, ua, country) = req

        # over a window of StatsDupWindow last requests, the same request must
        # not have occured already
        m = hashlib.md5()
        m.update(repr(req))
        md = m.digest()

        for i in conf['statsignoreip']:
            if ip.startswith(i):
                #print 'ignoring ip %s because it matches %s' %(ip, i)
                continue

        # was the requests seen recently? If yes, ignore it.
        # otherwise, put it into the ring buffer.
        if md in known.data:
            continue
        known.append(md)


        # apply prefiltering
        # FIXME

        print '%-80s ' % url, 

        matched = False
        for m, s, mreg in re_matchlist:
            if matched:
                sys.exit('warning: %r matches\n   %r\nbut already matched a pevious regexp:\n   %r' % (url, mreg, matched))
            if m.match(url):
                print m.sub(s, url)
                matched = mreg
        if not matched:
            print '-'


    sys.exit(0)


if __name__ == '__main__':
    main()

