#!/usr/bin/env python
#
# TrillStat
# Copyright (C) 2010 sk89q <http://www.sk89q.com>
#
# This program is free software: you can redistribute it and/or modify it under 
# the terms of the GNU General Public License as published by the Free
# Software Foundation: either version 2 of the License, or (at your option) 
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more 
# details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# $Id$

import sys
import os.path
from optparse import OptionParser
import ConfigParser
import re
from glob import glob
import time
import urllib
import xml.dom
from xml.dom import minidom
try:
    import ctypes
    from ctypes import wintypes, windll
except: pass

class DefaultDict(dict):
    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return 0

class TopDict(dict):
    def __setitem__(self, key, value):
        if key in self and self[key] > value: return
        return dict.__setitem__(self, key, value)

class UsersDict(dict):
    def __setitem__(self, key, value):
        key = (key[0], key[1].lower().strip())
        return dict.__setitem__(self, key, value)
    
    def __getitem__(self, key):
        key = (key[0], key[1].lower().strip())
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return key[1]

def get_trillian_users_dir():
    try:
        CSIDL_APPDATA = 26

        _SHGetFolderPath = windll.shell32.SHGetFolderPathW
        _SHGetFolderPath.argtypes = [wintypes.HWND,
                                    ctypes.c_int,
                                    wintypes.HANDLE,
                                    wintypes.DWORD, wintypes.LPCWSTR]

        path_buf = wintypes.create_unicode_buffer(wintypes.MAX_PATH)
        result = _SHGetFolderPath(0, CSIDL_APPDATA, 0, 0, path_buf)
        value = os.path.join(path_buf.value.strip(), "Trillian/users")
        if os.path.isdir(value): return value
        return None
    except:
        return None

def super_url_quote(s):
    new_s = ""
    i = 0
    while i < len(s):
        o = ord(s[i])
        if (o >= 48 and o <= 57) or (o >= 65 and o <= 90) or \
            (o >= 97 and o <= 122):
            new_s += s[i]
        else:
            new_s += "%" + s[i].encode('hex').upper()
        i = i + 1
    return new_s

def uniquify(lst):
    keys = {} 
    for entry in lst: 
        keys[entry] = 1 
    return keys.keys()

def sort_results(lst):
    lst = [(k, lst[k]) for k in lst]
    lst.sort(lambda a, b: b[1] - a[1])
    return lst

def format_time(t):
    mins, secs = divmod(t, 60)
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 25)
    return "%03sd %02sh %02sm %02ss" % (days, hrs, mins, secs)

def generate(buddies_file, logs_dir, min_time):
    url_re = re.compile("(?:ht|f)tps?://[^ \"<>]+")

    users = UsersDict()
    recvd_from = DefaultDict()
    said_to = DefaultDict()
    session_time = DefaultDict()
    top_outgoing = DefaultDict()
    top_words = DefaultDict()
    top_urls = DefaultDict()

    dom = minidom.parse(buddies_file)

    for node in dom.getElementsByTagName("buddy"):
        medium, uri = node.getAttribute("uri").split(":", 1)
        uri = urllib.unquote(uri).split(':')
        id = uri[1] if len(uri) > 1 else uri[0]
        name = id
        
        try:
            name = urllib.unquote(node.childNodes[0].data)
            
            if node.parentNode.localName == "metacontact":
                title = node.parentNode.getElementsByTagName("title")
                name = urllib.unquote(title[0].childNodes[0].data)
        except: pass
        
        users[(medium, id)] = name

    logs = glob(os.path.join(logs_dir, "*/Query/*.xml"))

    for log in logs:
        print >>sys.stderr, log
        
        nodes = []
        session_start = None
        last_time = 0
        
        f = open(log, "r")
        data = f.read()
        f.close()
        
        # Wrap the document in XML tags to make it valid
        dom = minidom.parseString("<log>%s</log>" % data)
        
        # Build a list of nodes which we will sort
        for node in dom.documentElement.childNodes:
            if node.nodeType == xml.dom.Node.ELEMENT_NODE:
                try:
                    time = int(node.getAttribute('time'))
                except Exception, e:
                    time = 0
                if min_time != None and time < min_time: continue
                nodes.append((time, node))
        
        nodes.sort(lambda a, b: a[0] - b[0])
        nodes = [n[1] for n in nodes]
        
        for node in nodes:
            medium = node.getAttribute("medium")
            sender = users[(medium, urllib.unquote(node.getAttribute("from")))]
            recipient = users[(medium, urllib.unquote(node.getAttribute("to")))]
            type = node.getAttribute("type")
            try:
                time = int(node.getAttribute('time'))
            except:
                time = 0
            
            if node.localName == "session": # Track session time
                if type == "start":
                    if session_start != None:
                        print >>sys.stderr, "warning: Found session start without a stop of a previous session"
                        
                        if last_time > 0:
                            session_time[recipient] = session_time[recipient] + (last_time - session_start)
                    if time > 0:
                        session_start = time
                    else:
                        print >>sys.stderr, "warning: Timestamp of 0 or less"
                elif type == "stop":
                    if session_start == None:
                        print >>sys.stderr, "warning: Found session stop without a start"
                    elif time < 0:
                        print >>sys.stderr, "warning: Timestamp of 0 or less"
                    else:
                        session_time[recipient] = session_time[recipient] + (time - session_start)
                    session_start = None
            elif node.localName == "message": # Track messages
                text = urllib.unquote(node.getAttribute("text"))
                text_norm = text.lower().strip()
                
                urls = uniquify(url_re.findall(text))
                for url in urls: top_urls[url] = top_urls[url] + 1
                
                if type == "incoming_privateMessage":
                    recvd_from[sender] = recvd_from[sender] + 1
                elif type == "outgoing_privateMessage":
                    said_to[recipient] = said_to[recipient] + 1
                    top_outgoing[text_norm] = top_outgoing[text_norm] + 1
                    words = filter(lambda t: t != "", text_norm.split(" "))
                    for w in words: top_words[w] = top_words[w] + 1
            
            last_time = time
        
        if session_start != None:
            print >>sys.stderr, "warning: Session is currently active"
            session_time[recipient] = session_time[recipient] + (last_time - session_start)

    print >>sys.stderr, "Statistics collection completed!"
    print >>sys.stderr, ""

    print "=== # of Messages Received ==="
    for row in sort_results(recvd_from)[:20]:
        print "%5s %s"  % (row[1], row[0].encode('utf-8'))

    print
    print "=== # of Messages Sent ==="
    for row in sort_results(said_to)[:20]:
        print "%5s %s"  % (row[1], row[0].encode('utf-8'))

    print
    print "=== Longest Times You Kept the Window Open ==="
    for row in sort_results(session_time)[:40]:
        print "%12s %s"  % (format_time(row[1]), row[0].encode('utf-8'))

    print
    print "=== Top Lines You Said ==="
    for row in sort_results(top_outgoing)[:30]:
        print "%5s %s"  % (row[1], row[0].encode('utf-8'))

    print
    print "=== Top Words You Said ==="
    for row in sort_results(top_words)[:30]:
        print "%5s %s"  % (row[1], row[0].encode('utf-8'))

    print
    print "=== Top URLs Sent/Received ==="
    for row in sort_results(top_urls)[:30]:
        print "%5s %s"  % (row[1], row[0].encode('utf-8'))

def main():
    print >>sys.stderr, "TrillStat"
    print >>sys.stderr, "Copyright (C) 2010 sk89q <http://www.sk89q.com>"
    print >>sys.stderr, ""
    
    parser = OptionParser("%prog [options]")
    parser.add_option("-d", "--users-dir", dest="dir",
                      help="AppData users directory", action="store",
                      default=None)
    parser.add_option("-u", "--user", dest="user", help="User", action="store",
                      default=None)
    parser.add_option("--max-days", dest="days", help="Max. age in days", action="store",
                      type="int", default=None)
    (options, args) = parser.parse_args()
    
    dir = get_trillian_users_dir()
    user = super_url_quote(options.user) if options.user else None
    
    if options.dir:
        if not os.path.isdir(options.dir):
            parser.error("The specified users directory does not exist.")
        else:
            dir = options.dir
    else:
        if not dir or not os.path.isdir(dir):
            parser.error("Your Trillian users directory could not be detected.")
    
    if user:
        if not os.path.isfile(os.path.join(dir, user, "talk.ini")) or \
            not os.path.isfile(os.path.join(dir, user, "Buddies.xml")):
            parser.error("The specified user does not exist.")
    else:
        users = []
        for o in os.listdir(dir):
            if o != "global" and os.path.isdir(os.path.join(dir, o)):
                users.append(o)
        if len(users) >= 1:
            user = users[0]
        else:
            parser.error("No user was found.")
    
    print "Getting stats for user %s" % urllib.unquote(user)
    
    base_dir = os.path.join(dir, user)
    buddies_file = os.path.join(base_dir, "Buddies.xml")
    talk_file = os.path.join(base_dir, "talk.ini")
    
    try:
        talk = ConfigParser.RawConfigParser()
        talk.read(talk_file)
        log_dir = talk.get("Logging", "Directory")
    except:
        print >>sys.stderr, "error: Could not read log directory from talk.ini"
        sys.exit(2)
    
    min_time = time.time() - options.days * 60 * 60 * 24 if options.days else None
    
    generate(buddies_file, log_dir, min_time=min_time)

if __name__ == "__main__":
    main()