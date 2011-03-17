#!/usr/bin/env python
#
# Copyright (C) 2010, 2011 sk89q <http://www.sk89q.com>
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
#

import asyncore
import socket
import cStringIO as StringIO
import struct
import sys
from optparse import OptionParser

def write_str(str):
    return struct.pack('>h', len(str)) + str

class SignPostHandler(asyncore.dispatcher_with_send):
    def __init__(self, sock, msg):
        asyncore.dispatcher_with_send.__init__(self, sock)
        self.msg = msg
    
    def handle_read(self):
        data = self.recv(8192)
        if data[0] == "\x02":
            self.send("\x02" + write_str("-"))
        else:
            self.send("\xFF" + write_str(self.msg.replace("^", u"\u00A7").encode("utf-8")))
            self.close()

class SignPostServer(asyncore.dispatcher):
    def __init__(self, host, port, msg):
        asyncore.dispatcher.__init__(self)
        self.msg = msg
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is None:
            pass
        else:
            sock, addr = pair
            print "Connected: %s" % repr(addr)
            handler = SignPostHandler(sock, self.msg)

def main():
    parser = OptionParser()
    parser.add_option("-b", "--bind-ip", dest="ip", metavar="IP",
                      help="bind to an IP", default="0.0.0.0")
    parser.add_option("-p", "--port", dest="port", metavar="PORT",
                      help="port to listen on", default=25565, type="int")

    (options, args) = parser.parse_args()
    
    if len(args) != 1:
        parser.error("message required")
    
    server = SignPostServer(options.ip, options.port, args[0])
    print "Starting server..."
    asyncore.loop()

if __name__ == "__main__":
    main()