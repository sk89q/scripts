#!/usr/bin/env python
#
# srcdswatch
# Copyright (C) 2010 sk89q <http://www.sk89q.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# $Id$

#
# Example config:
#     [server]
#     addr=127.0.0.1
#     port=27018
#     check_key=game_directory
#     check_value=garrysmod
#     cmd=orangebox\srcds -console -game garrysmod -port 27018 +exec server.cfg
#     steam_update_cmd=update.bat
#     http_enable=on
#     http_port=8081
#     http_username=admin
#     http_password=changeme
#

import subprocess
from threading import Thread
from SRCDS import SRCDS
import ConfigParser
from optparse import OptionParser
import BaseHTTPServer
import SocketServer
import time
import sys
import socket, cgi
from base64 import b64decode
import logging

class SRCDSMonitorThread(Thread):
    def __init__(self, addr, port=27015, check_freq=5, threshold_time=30,
                 check_key="game_directory", check_value=""):
        Thread.__init__(self)
        self.addr = addr
        self.port = port
        self.check_key = check_key
        self.check_value = check_value
        self.query = SRCDS(addr, port=port)
        self.active = True
        self.check_freq = check_freq
        self.threshold_time = threshold_time
        self.enabled = False
        self.last_check = 0
        self.last_ok = time.time()
        self.alerted = False
    def run(self):
        while self.active:
            now = time.time()
            if self.enabled:
                if self.last_check < now - self.check_freq:
                    self.last_check = now
                    try:
                        details = self.query.details()
                        if self.check_key in details and \
                            details[self.check_key] == self.check_value:
                            self.last_ok = time.time()
                            self.alerted = False
                        else:
                            logging.debug("{0}:{1}: check key ({2}) differs as '{3}'" \
                                .format(self.addr, self.port, self.check_key,
                                details[self.check_key] if self.check_key in details else "N/A"))
                    except socket.error, e:
                        logging.debug("{0}:{1}: not responding".format(self.addr, self.port))
                    except Exception, e:
                        logging.debug("{0}:{1}: unknown monitoring error: {3!s}" \
                            .format(self.addr, self.port, e))
                if self.last_ok < now - self.threshold_time and not self.alerted:
                    self.alerted = True
                    self.on_alert()
            time.sleep(1)
    def enable(self):
        self.enabled = True
        self.reset()
    def disable(self):
        self.enabled = False
    def reset(self):
        self.last_ok = time.time()
        self.alerted = False
    def on_alert(self):
        pass

class SRCDSThread(Thread):
    def __init__(self, args, monitor):
        Thread.__init__(self)
        self.proc = None
        self.args = args
        self.running = False
        self.active = True
        self.enabled = False
        self.monitor = monitor
        self.monitor.on_alert = self.handle_alert
        self.start()
        self.monitor.start()
    def run(self):
        while self.active:
            if self.proc:
                self.proc.communicate()
                self.proc = None # Service died
                logging.error("Server process has died.")
                time.sleep(2)
            if self.enabled:
                logging.info("Starting: {0!s}".format(self.args))
                self.open()
                time.sleep(1)
            time.sleep(1)
    def open(self):
        self.monitor.reset()
        try:
            self.proc = subprocess.Popen(self.args)
        except Exception, e:
            logging.error("Failed to start: {0!s}".format(e))
    def enable(self):
        self.enabled = True
        self.monitor.enable()
    def disable(self):
        self.enabled = False
        self.monitor.disable()
        if self.proc:
            self.terminate()
    def terminate(self):
        if self.proc:
            try: self.proc.terminate()
            except: pass
            self.proc = None
    def handle_alert(self):
        if not self.enabled:
            return
        logging.info("Server has not been responding; terminating")
        self.terminate()

class SteamUpdateThread(Thread):
    def __init__(self, args):
        Thread.__init__(self)
        self.proc = None
        self.args = args
        self.active = True
        self.running = False
        self.need_run = False
        self.start()
    def run(self):
        while self.active:
            if self.need_run:
                self.need_run = False
                self.running = True
                logging.info("Starting Steam update...")
                try:
                    self.proc = subprocess.Popen(self.args)
                    self.proc.communicate()
                    logging.info("Steam update finished.")
                except Exception, e:
                    logging.error("Failed to update: {0!s}".format(e))
                self.running = False
                self.proc = None
            time.sleep(1)
    def update(self):
        if not self.running:
            self.need_run = True

class WebServerThread(Thread):
    def __init__(self, addr, port, username, password, srcds_thread, updater):
        Thread.__init__(self)
        self.server = BaseHTTPServer.HTTPServer((addr, port), WebRequestHandler)
        self.server.srcds_thread = srcds_thread
        self.server.updater = updater
        self.server.username = username
        self.server.password = password
    def run(self):
        self.server.serve_forever()

class WebRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def verify_auth(self):
        header = self.headers.get('authorization')
        if header == None:
            return False
        t, data = header.split(' ')
        if t == 'Basic':
            username, _, password = b64decode(data).partition(':')
            if username == self.server.username and \
                password == self.server.password:
                return True
            else:
                return False
        else:
            return False
    
    def do_GET(self):
        if not self.verify_auth():
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Basic realm=\"srcdswatch\"")
            self.end_headers()
            return
        
        if self.path.find('?') != -1:
            self.path, self.query_string = self.path.split('?', 1)
        else:
            self.query_string = ''
        
        vars = dict(cgi.parse_qsl(self.query_string))
        
        if self.path == "/":
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            if self.server.srcds_thread.enabled:
                content = """<p><strong>Status:</strong> Enabled
    (last response was {last_response:.2f} second(s) ago)</p>
<ul>
    <li><a href="/disable">Stop</a></li>
    <li><a href="/restart">Restart</a></li>
</ul>""".format(last_response=time.time() - self.server.srcds_thread.monitor.last_ok)
            else:
                update_link = "<li>Steam update disabled</li>"
                if self.server.updater:
                    if self.server.updater.running:
                        update_link = "<li>Steam update is working.</li>"
                    else:
                        update_link = "<li><a href=\"/update\">Steam Update</a></li>"
                
                content = """<p><strong>Status:</strong> Disabled</p>
<ul>
    <li><a href="/enable">Start</a></li>
    {0}
</ul>""".format(update_link)
            
            # Write page
            self.wfile.write("""<!DOCTYPE html>
<html>
<head>
<title>srcdswatch Administration</title>
</title>
</head>
<body>
<h1>{server_addr}:{port}</h1>
{content}
<p><em>Powered by srcdswatch</em></p>
</body>
</html>
""".format(server_addr=self.server.srcds_thread.monitor.addr,
           port=self.server.srcds_thread.monitor.port,
           content=content))
        elif self.path == "/enable":
            if not self.server.updater or not self.server.updater.running:
                if not self.server.srcds_thread.enabled:
                    self.server.srcds_thread.enable()
            self.redirect("/")
        elif self.path == "/disable":
            if self.server.srcds_thread.enabled:
                self.server.srcds_thread.disable()
            self.redirect("/")
        elif self.path == "/restart":
            if self.server.srcds_thread.enabled:
                self.server.srcds_thread.terminate()
            self.redirect("/")
        elif self.path == "/update":
            if self.server.updater and not self.server.srcds_thread.enabled:
                self.server.updater.update()
            self.redirect("/")
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write("""
<!DOCTYPE html>
<html>
<head>
<title>Not Found</title>
</title>
</head>
<body>
<p>Page not found!</p>
<p><em>Powered by srcdswatch</em></p>
</body>
</html>
""")
    def redirect(self, path):
        self.send_response(301)
        self.send_header("Location", path)
        self.end_headers()

def main():
    print 'srcdswatch'
    print 'Copyright (c) sk89q <http://www.sk89q.com>'
    print
    
    parser = OptionParser("config_path")

    (options, args) = parser.parse_args()
    
    if len(args) < 1:
        parser.error("Configuration file not specified")
    elif len(args) > 1:
        parser.error("Too many arguments")
    
    config_file = args[0]
    
    try:
        config = ConfigParser.RawConfigParser({
            "steam_update_cmd": "",
            "http_enable": "off",
            "http_port": "27015",
            "http_addr": "0.0.0.0",
            "http_port": "8081",
            "http_username": "admin",
            "http_password": "changeme",
        })
        
        config.read(config_file)
        addr = config.get("server", "addr").strip()
        port = config.getint("server", "port")
        cmd = config.get("server", "cmd")
        check_key = config.get("server", "check_key")
        check_value = config.get("server", "check_value")
        http_enable = config.getboolean("server", "http_enable")
        http_addr = config.get("server", "http_addr")
        http_port = config.getint("server", "http_port")
        http_username = config.get("server", "http_username")
        http_password = config.get("server", "http_password")
        steam_update_cmd = config.get("server", "steam_update_cmd")
    except ConfigParser.NoOptionError, e:
        print "error: Misconfiguration: {0!s}".format(e)
        sys.exit(1)
    
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)s] %(message)s')
        
    monitor = SRCDSMonitorThread(addr, port, check_key=check_key,
                                 check_value=check_value)
    
    srcds = SRCDSThread(cmd, monitor)
    srcds.enable()
    
    if steam_update_cmd.strip() != "":
        updater = SteamUpdateThread(steam_update_cmd)
    else:
        updater = False
    
    if http_enable:
        WebServerThread(http_addr, http_port, http_username,
                        http_password, srcds, updater) \
            .start()

if __name__ == '__main__':
    main()