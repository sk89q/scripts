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

import SocketServer
import socket
from struct import *
import sys
import threading
from optparse import OptionParser
import re

class BinaryStream:
    def __init__(self, base_stream):
        self.base_stream = base_stream
    def read_byte(self):
        r = self.base_stream.recv(1)
        if len(r) == 0: raise EOFError
        return r
    def read_bytes(self, length):
        r = self.base_stream.recv(length)
        if len(r) == 0: raise EOFError
        return r
    def read_char(self):
        return self.unpack('b')
    def read_uchar(self):
        return self.unpack('B')
    def read_short(self):
        return self.unpack('>h', 2)
    def read_ushort(self):
        return self.unpack('>H', 2)
    def read_string16(self):
        length = self.read_short()
        if length > 240: raise EOFError
        return self.read_bytes(length * 2).decode('utf-16_be')
    def write_bytes(self, v):
        self.base_stream.send(v)
    def write_char(self, v):
        self.pack('b', v)
    def write_uchar(self, v):
        self.pack('B', v)
    def write_short(self, v):
        self.pack('>h', v)
    def write_ushort(self, v):
        self.pack('>H', v)
    def write_int(self, v):
        self.pack('>i', v)
    def write_uint(self, v):
        self.pack('>I', v)
    def write_long(self, v):
        self.pack('>q', v)
    def write_ulong(self, v):
        self.pack('>Q', v)
    def write_string16(self, v):
        length = len(v)
        self.write_short(length)
        self.write_bytes(v.encode('utf-16_be'))
    def pack(self, fmt, data):
        return self.write_bytes(pack(fmt, data))
    def unpack(self, fmt, length = 1):
        return unpack(fmt, self.read_bytes(length))[0]

class SignPostClient(SocketServer.BaseRequestHandler):
    NAME_PATTERN = re.compile("[^A-Za-z0-9_]")
    def log(self, msg):
        print "[{0}] {1}".format(self.client_address[0], msg)
    def handle(self):
        self.log("Connected")
        stream = BinaryStream(self.request)
        try:
            while 1:
                self.process(stream.read_uchar(), stream)
        except (EOFError, socket.error), e:
            self.request.close()
            self.log("Disconnected")
    def process(self, packet_id, stream):
        if packet_id == 0xFE: # Status packet
            stream.write_uchar(0xFF)
            stream.write_string16(self.server.status)
            raise EOFError()
        elif packet_id == 0x02:
            self.name = stream.read_string16()
            self.log("{0} tried to join".format(self.NAME_PATTERN.sub("", self.name)))
            stream.write_uchar(0xFF)
            stream.write_string16(self.server.message)
            raise EOFError()
        else:
            self.log("Got unknown packet type: {0}".format(packet_id))
            raise EOFError()
        
class SignPostServer(SocketServer.TCPServer):
    def __init__(self, server_address, message, status, max_clients=30):
        SocketServer.TCPServer.__init__(self, server_address, SignPostClient, True)
        self.message = message
        self.status = status
        self.lock = threading.Lock()
        self.client_count = 0
        self.max_clients = max_clients
    def increment(self):
        self.lock.acquire()
        self.client_count = self.client_count + 1
        self.lock.release()
    def decrement(self):
        self.lock.acquire()
        self.client_count = self.client_count - 1
        self.lock.release()
    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
            self.shutdown_request(request)
        except:
            self.handle_error(request, client_address)
            self.shutdown_request(request)
        finally:
            self.decrement()
    def process_request(self, request, client_address):
        self.lock.acquire()
        try:
            # Don't want to allow someone to exhaust resources
            if self.client_count >= self.max_clients:
                print "Out of clients!"
                try: request.close()
                except: pass
                return
        finally:
            self.lock.release()
        self.increment()
        t = threading.Thread(target = self.process_request_thread,
                             args = (request, client_address))
        t.start()

def colorize(s):
    return s.replace("^", u"\u00A7")

def main():
    parser = OptionParser()
    parser.add_option("-b", "--bind-ip", dest="ip", metavar="IP",
                      help="bind to an IP", default="0.0.0.0")
    parser.add_option("-p", "--port", dest="port", metavar="PORT",
                      help="port to listen on", default=25565, type="int")
    parser.add_option("-m", "--maxclients", dest="max_clients", metavar="NUM",
                      help="maximum number of clients", default=20, type="int")

    (options, args) = parser.parse_args()
    
    if len(args) != 2:
        parser.error("message and status required")
    
    message = colorize(args[0])
    status = colorize(args[1]) # Has no effect
    
    if len(status) > 50:
        parser.error("status should be 50 characters or shorter")
    
    server = SignPostServer((options.ip, options.port),
        message, status, options.max_clients)
    print "Starting server..."
    server.serve_forever()

if __name__ == "__main__":
    main()