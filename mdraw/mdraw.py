#!/usr/bin/env python
#
# MouseDraw
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

# NOTE: This was a quick experiment. Quality and functionality of the code is
# not guaranteed!

import os
import sys
import ctypes
from ctypes import wintypes
import win32api, win32con
import Image
from threading import Thread
from xml.dom.minidom import parse
from pprint import pprint
import time
import math
import re

byref = ctypes.byref
user32 = ctypes.windll.user32

def resize_ratio(old_w, old_h, width, height):
    ratio = old_w/old_h

    if width/height > ratio:
       return height/old_h
    else:
       return width/old_w

class Vector(list):
    def __init__(self, *args, **kwargs):
        try:
            list.__init__(self, *args, **kwargs)
        except TypeError:
            list.__init__(self, args, **kwargs)

    def __add__(self, other):
        return Vector(map(lambda x, y: x + y, self, other))

    def __neg__(self):
        return Vector(map(lambda x: -x, self))
    
    def __sub__(self, other):
        return Vector(map(lambda x, y: x - y, self, other))

    def __mul__(self, other):
        try:
            return Vector(map(lambda x,y: x*y, self,other))
        except:
            return Vector(map(lambda x: x*other, self))

    def __rmul__(self, other):
        return self.__mul__(other)

    def __div__(self, other):
        try:
            return Vector(map(lambda x, y: x / y, self, other))
        except:
            return Vector(map(lambda x: x / other, self))

    def __rdiv__(self, other):
        return self.__div__(other)

class InputWait(Thread):
    def __init__(self, vk, mod):
        Thread.__init__(self)
        self.vk = vk
        self.mod = mod
        self.running = True
    
    def stop(self):
        print("stop")
        self.running = False
    
    def run(self):
        if not user32.RegisterHotKey(None, 1, self.mod, self.vk):
            raise Exception("Failed to register hotkey")
            
        try:
            msg = wintypes.MSG()
            while user32.GetMessageA(byref(msg), None, 0, 0) != 0 and self.running:
                if msg.message == win32con.WM_HOTKEY:
                    raise Exception("Hotkey pressed")

            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageA(byref(msg))
        except:
            pass
        finally:
            user32.UnregisterHotKey(None, 1)
        
        self.running = False

class DrawerHost(Thread):
    def __init__(self, drawer, offset, dim, pos_delay=0.005, evnt_delay=0.005):
        Thread.__init__(self)
        self.drawer = drawer
        self.offset = offset
        self.dim = dim
        self.pos_delay = pos_delay
        self.evnt_delay = evnt_delay
        self.running = True
    
    def stop(self):
        self.running = False
    
    def pos(self, pos):
        win32api.SetCursorPos(pos)
        time.sleep(self.pos_delay)
    
    def ldown(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(self.evnt_delay)
    
    def lup(self):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(self.evnt_delay)
    
    def run(self):
        for i in self.drawer.draw(self, self.offset, self.dim):
            if not self.running:
                break
        
        self.pos(self.offset)
        self.running = False

class ImageDrawer:
    def __init__(self, im, vert_optimize=False):
        self.im = im
        self.vert_optimize = vert_optimize
    
    def draw(self, host, offset, dim):
        pix = self.im.load()
        
        for x in range(0, self.im.size[0]):
            for y in range(0, self.im.size[1]):
                if pix[x, y] == (0, 0, 0):
                    rx = (x + offset[0]) * dim
                    ry = (y + offset[1]) * dim
                    
                    host.pos((rx, ry))
                    host.ldown()
                    
                    if self.vert_optimize:
                        for i in range(1, self.im.size[1] - y):
                            if pix[x, y + i] != (0, 0, 0):
                                y = y + i - 1
                                break
                    
                    ry = (y + offset[1]) * dim
                    host.lup()
                
                yield

class SVGTransformContext:
    """Keeps track of the current coordinate system and its transformations.
    """
    matrix_re = re.compile(r"^[ \t\r\n]*matrix[ \t\r\n]*\([ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*" +
        r",[ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*,[ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*," +
        r"[ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*,[ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*," +
        r"[ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*\)")
    translate_re = re.compile(r"^[ \t\r\n]*translate[ \t\r\n]*\([ \t\r\n]*(-?[0-9\.eE]+)" +
        r"(?:[ \t\r\n]*,[ \t\r\n]*(-?[0-9\.eE]+))?[ \t\r\n]*\)")
    scale_re = re.compile(r"^[ \t\r\n]*scale[ \t\r\n]*\([ \t\r\n]*(-?[0-9\.eE]+)" + 
        r"(?:[ \t\r\n]*,[ \t\r\n]*(-?[0-9\.eE]+))?[ \t\r\n]*\)")
    rotate_re = re.compile(r"^[ \t\r\n]*rotate[ \t\r\n]*\([ \t\r\n]*(-?[0-9\.eE]+)" +
        r"(?:[ \t\r\n]*,[ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*,[ \t\r\n]*" +
        r"(-?[0-9\.eE]+))?[ \t\r\n]*\)")
    skew_x_re = re.compile(r"^[ \t\r\n]*skewX[ \t\r\n]*\([ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*\)")
    skew_y_re = re.compile(r"^[ \t\r\n]*skewY[ \t\r\n]*\([ \t\r\n]*(-?[0-9\.eE]+)[ \t\r\n]*\)")
    
    @staticmethod
    def parse(data):
        """Parses the transform string.
        """
        data = data.strip()
        ctx = SVGTransformContext()
        
        try:
            # Simple regexp parser
            while len(data) > 0:
                # matrix(a, b, c, d, e, f)
                m = SVGTransformContext.matrix_re.search(data)
                if m:
                    ctx.add_matrix(float(m.group(1)), float(m.group(2)),
                                   float(m.group(3)), float(m.group(4)),
                                   float(m.group(5)), float(m.group(6)))
                    data = data[len(m.group(0)):]
                    continue
                # translate(tx[, ty])
                m = SVGTransformContext.translate_re.search(data)
                if m:
                    if m.group(2) != None:
                        ctx.translate(float(m.group(1)), float(m.group(2)))
                    else:
                        ctx.translate(float(m.group(1)))
                    data = data[len(m.group(0)):]
                    continue
                # scale(sx[, sy])
                m = SVGTransformContext.scale_re.search(data)
                if m:
                    if m.group(2) != None:
                        ctx.scale(float(m.group(1)), float(m.group(2)))
                    else:
                        ctx.scale(float(m.group(1)))
                    data = data[len(m.group(0)):]
                    continue
                # rotate(angle[, cx, cy])
                m = SVGTransformContext.rotate_re.search(data)
                if m:
                    if m.group(3) != None:
                        ctx.rotation(float(m.group(1)), float(m.group(2)),
                                         float(m.group(3)))
                    else:
                        ctx.rotation(float(m.group(1)))
                    data = data[len(m.group(0)):]
                    continue
                # skewX(angle)
                m = SVGTransformContext.skew_x_re.search(data)
                if m:
                    ctx.skew_x(float(m.group(1)))
                    data = data[len(m.group(0)):]
                    continue
                # skewY(angle)
                m = SVGTransformContext.skew_y_re.search(data)
                if m:
                    ctx.skew_y(float(m.group(1)))
                    data = data[len(m.group(0)):]
                    continue
                raise Exception("Could not parse rest of transformations: %s" % data)
        except Exception, e:
            print "warning: %s" % e
            
        return ctx
    
    def __init__(self):
        """Create a context.
        """
        self._ctm = (1, 0, 0, 1, 0, 0) # Identity
    
    def transform(self, v):
        """Transforms a point using this context.
        """
        return Vector(self._ctm[0] * v[0] + self._ctm[2] * v[1] + self._ctm[4],
                      self._ctm[1] * v[0] + self._ctm[3] * v[1] + self._ctm[5])
    
    def matrix(self, a, b, c, d, e, f):
        """Adds a transformation matrix, whose values are specified by
        a, b, c, d, e, and f.
        """
        self._ctm = self._mul(self._ctm, (a, b, c, d, e, f))
    
    def translate(self, tx, ty=None):
        """Adds a translation.
        """
        ty = ty if ty != None else 0
        self._ctm = self._mul(self._ctm, (1, 0, 0, 1, tx, ty))
    
    def scale(self, sx, sy=None):
        """Adds a scaling.
        """
        sy = sy if sy != None else sx
        self._ctm = self._mul(self._ctm, (sx, 0, 0, sy, 0, 0))
    
    def rotation(self, a, cx=None, cy=None):
        """Adds a rotation.
        """
        a = a * 180 / math.pi
        cx = cx if cx != None else 0
        cy = cy if cy != None else 0
        self.translate(cx, cy)
        self._ctm = self._mul(self._ctm, (math.cos(a), math.sin(a),
                                          -math.sin(a), math.cos(a), 0, 0))
        self.translate(-cx, -cy)
    
    def skew_x(self, skew_x):
        """Adds a skew on the X axis.
        """
        skew_x = skew_x * 180 / math.pi
        self._ctm = self._mul(self._ctm, (1, 0, math.tan(skew_x), 1, 0, 0))
    
    def skew_y(self, skew_y):
        """Adds a skew on the Y axis.
        """
        skew_y = skew_y * 180 / math.pi
        self._ctm = self._mul(self._ctm, (1, math.tan(skew_y), 0, 1, 0, 0))
        
    def _mul(self, a, b, *m):
        """Internal method to do matrix multiplication.
        """
        result = (a[0] * b[0] + a[2] * b[1],
                  a[1] * b[0] + a[3] * b[1],
                  a[0] * b[2] + a[2] * b[3],
                  a[1] * b[2] + a[3] * b[3],
                  a[0] * b[4] + a[2] * b[5] + a[4],
                  a[1] * b[4] + a[3] * b[5] + a[5])
        if len(m) > 0:
            return self._mul(result, *m)
        else:
            return result
    
    def __add__(self, other):
        """Add two SVGTransformContext instances together.
        """
        ctx = SVGTransformContext()
        ctx._ctm = self._mul(self._ctm, other._ctm)
        return ctx
    
class SVGLineParser:
    """Used to parse the SVG file and convert it into a list of lines.
    """
    instruct_re = re.compile("^([A-Za-z])")
    number_re = re.compile("^(\\-?[0-9]+(?:\\.[0-9]*)?)")
    space_re = re.compile("([ ,\\-])")
    
    def __init__(self, lines, elm, transform=SVGTransformContext()):
        """Create an instance of SVGLineParser using a list of lines and
        the root element to start parsing form.
        """
        self.lines = lines
        self.transform = transform
        
        for node in elm.childNodes:
            if node.nodeType != 1: continue
            
            try:
                if node.localName == "path":
                    self.handle_path(node)
                elif node.localName == "polyline":
                    self.handle_polyline(node)
                elif node.localName == "polygon":
                    self.handle_polygon(node)
                elif node.localName == "line":
                    self.handle_line(node)
                elif node.localName == "rect":
                    self.handle_rect(node)
                elif node.localName == "circle":
                    self.handle_circle(node)
                elif node.localName == "ellipse":
                    self.handle_ellipse(node)
                elif node.localName == "g":
                    self.handle_group(node)
                elif node.localName == "marker": # We don't really 'use' this entity
                    self.handle_group(node)
                elif node.localName == "pattern": # We don't really 'use' this entity
                    self.handle_group(node)
                else:
                    print "warning: Unprocessed node: %s" % node.localName
            except Exception, e:
                print "warning: Error while processing '%s' node: %s" %\
                    (node.localName, e)
    
    def parse_point(self, t):
        """Parses a comma-separated list of two coordinates.
        """
        a, b = t.split(",")
        return Vector(float(a), float(b))
    
    def parse_transforms(self, node):
        """Parse the transform attribute out of a node and return an
        instance of SVGTransformContext.
        """
        if node.hasAttribute('transform'):
            return SVGTransformContext.parse(node.getAttribute('transform'))
        else:
            return SVGTransformContext()
    
    def tokenize_path(self, data):
        """Tokenize an SVG path data attribute value.
        """
        tokens = []
        
        while len(data) > 0:
            m = SVGLineParser.instruct_re.search(data)
            if m:
                tokens.append(m.group(1))
                data = data[len(m.group(0)):]
                continue
            m = SVGLineParser.number_re.search(data)
            if m:
                tokens.append(m.group(1))
                data = data[len(m.group(0)):]
                continue
            m = SVGLineParser.space_re.search(data)
            if m:
                data = data[len(m.group(0)):]
                continue
            print "warning: Unknown element in rest of path: %s" % data
            break
        
        return tokens
    
    def safe_float(self, v, default=0):
        try:
            return float(v)
        except:
            return default
    
    def handle_group(self, node):
        """Handle an SVG group node.
        """
        transform = self.parse_transforms(node)
        
        SVGLineParser(self.lines, node, self.transform + transform)
    
    def handle_polyline(self, node, close=False):
        """Handle a polyline node.
        """
        transform = self.parse_transforms(node)
        
        points = re.split(" +", node.getAttribute('points').strip())
        last = self.parse_point(points[0])
        first = last
        for i in range(1, len(points)):
            pt = self.parse_point(points[i])
            if points[i].strip() != "":
                self.line(last, pt, transform)
                last = pt
        if close:
            self.line(last, first, transform)
    
    def handle_polygon(self, node):
        """Handle a polygon node.
        """
        self.handle_polyline(node, True)
    
    def handle_line(self, node):
        """Handle a line node.
        """
        transform = self.parse_transforms(node)
        
        x1 = self.safe_float(node.getAttribute('x1'))
        y1 = self.safe_float(node.getAttribute('y1'))
        x2 = self.safe_float(node.getAttribute('x2'))
        y2 = self.safe_float(node.getAttribute('y2'))
        self.line(Vector(x1, y1), Vector(x2, y2), transform)
    
    def handle_rect(self, node):
        """Handle a rect node.
        """
        transform = self.parse_transforms(node)
        
        x = self.safe_float(node.getAttribute('x'))
        y = self.safe_float(node.getAttribute('y'))
        w = float(node.getAttribute('width'))
        h = float(node.getAttribute('height'))
        self.rectangle(x, y, w, h, transform=transform)
    
    def handle_circle(self, node):
        """Handle a circle node.
        """
        transform = self.parse_transforms(node)
        
        cx = self.safe_float(node.getAttribute('cx'))
        cy = self.safe_float(node.getAttribute('cy'))
        r = float(node.getAttribute('r'))
        self.circle(cx, cy, r, transform)
    
    def handle_ellipse(self, node):
        """Handle an ellipse node.
        """
        transform = self.parse_transforms(node)
        
        cx = self.safe_float(node.getAttribute('cx'))
        cy = self.safe_float(node.getAttribute('cy'))
        rx = float(node.getAttribute('rx'))
        ry = float(node.getAttribute('ry'))
        self.ellipse(cx, cy, rx, ry, transform)
        
    def handle_path(self, node):
        """Handle a path node.
        """
        data = node.getAttribute('d')
        
        tokens = self.tokenize_path(data)
        transform = self.parse_transforms(node)
        pos = Vector(0, 0)
        start_pos = Vector(0, 0)
        last_cubic_cp = None
        last_quad_cp = None
        last_instruct = ""
        
        while len(tokens) > 0:
            part = tokens.pop(0)
            if len(part) > 1:
                try:
                    float(part)
                    tokens.insert(0, part)
                    part = last_instruct
                except ValueError, e: pass
            
            last_instruct = part
            
            # Move to
            if part == "M":
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                start_pos = pos
            elif part == "m":
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                start_pos = pos
            
            # End path
            elif part == "Z" or part == "z":
                self.lines.append((pos, start_pos))
            
            # Line to
            elif part == "L":
                old_pos = pos
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                self.line(old_pos, pos, transform)
            elif part == "l":
                old_pos = pos
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                self.line(old_pos, pos, transform)
            
            # Horizontal
            elif part == "H":
                old_pos = pos
                pos = Vector(float(tokens.pop(0)), pos[1])
                self.line(old_pos, pos, transform)
            elif part == "h":
                old_pos = pos
                pos = Vector(pos[0] + float(tokens.pop(0)), pos[1])
                self.line(old_pos, pos, transform)
            
            # Vertical
            elif part == "V":
                old_pos = pos
                pos = Vector(pos[0], float(tokens.pop(0)))
                self.line(old_pos, pos, transform)
            elif part == "v":
                old_pos = pos
                pos = Vector(pos[0], pos[1] + float(tokens.pop(0)))
                self.line(old_pos, pos,** self.parse_transforms(node))
            
            # Cubic curve to
            elif part == "C":
                old_pos = pos
                cp1 = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                cp2 = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                last_cubic_cp = cp2
                self.cubic_bezier(old_pos, cp1, cp2, pos, transform=transform)
            elif part == "c":
                old_pos = pos
                cp1 = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                cp2 = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                last_cubic_cp = cp2
                self.cubic_bezier(old_pos, cp1, cp2, pos, transform=transform)
            
            # shorthand cubic curve to
            elif part == "S":
                old_pos = pos
                cp1 = -(last_cubic_cp - pos) + pos
                cp2 = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                last_cubic_cp = cp2
                self.cubic_bezier(old_pos, cp1, cp2, pos, transform=transform)
            elif part == "s":
                old_pos = pos
                cp1 = -(last_cubic_cp - pos) + pos
                cp2 = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                last_cubic_cp = cp2
                self.cubic_bezier(old_pos, cp1, cp2, pos, transform=transform)
            
            # Quadratic cubic curve to
            elif part == "Q":
                old_pos = pos
                cp1 = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                last_quad_cp = cp1
                self.quad_bezier(old_pos, cp1, pos, transform)
            elif part == "Q":
                old_pos = pos
                cp1 = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                last_quad_cp = cp1
                self.quad_bezier(old_pos, cp1, po, transform)
            
             # Shorthand quadratic cubic curve to
            elif part == "T":
                old_pos = pos
                cp1 = -(last_quad_cp - pos) + pos
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0)))
                last_quad_cp = cp1
                self.quad_bezier(old_pos, cp1, pos, transform)
            elif part == "t":
                old_pos = pos
                cp1 = -(last_quad_cp - pos) + pos
                pos = Vector(float(tokens.pop(0)), float(tokens.pop(0))) + pos
                last_quad_cp = cp1
                self.quad_bezier(old_pos, cp1, pos, transform)
            
            else:
                print "warning: Unknown path instruction: %s" % part
                break
    
    def add_points(self, points, transform=SVGTransformContext()):
        """Given a set of points, draw lines in between them.
        """
        if len(points) == 0: return
        
        last_pt = points[0]
        for i in range(1, len(points)):
            self.line(last_pt, points[i], transform)
            last_pt = points[i]
    
    def line(self, f, t, transform=SVGTransformContext()):
        """Draw a line.
        """
        transform = self.transform + transform
        self.lines.append((transform.transform(f), transform.transform(t)))
    
    def rectangle(self, x, y, w, h, rx=0, ry=0, steps=10,
                  transform=SVGTransformContext()):
        """Draw a rectangle.
        """
        self.line(Vector(x, y), Vector(x + w, y))
        self.line(Vector(x + w, y), Vector(x + w, y + h))
        self.line(Vector(x + w, y + h), Vector(x, y + h))
        self.line(Vector(x, y + h), Vector(x, y))
    
    def circle(self, cx, cy, r, steps=10, transform=SVGTransformContext()):
        """Draw a circle.
        """
        self.ellipse(cx, cy, r, r, steps, transform)
    
    def ellipse(self, cx, cy, rx, ry, steps=10,
                    transform=SVGTransformContext()):
        """Draw an ellipse.
        """
        if rx < 0 or ry < 0: return
        
        points = []
        for t in range(steps + 1):
            t = t / float(steps)
            x = rx * math.cos(t * 2*math.pi) + cx
            y = ry * math.sin(t * 2*math.pi) + cy
            points.append(Vector(x, y))
        self.add_points(points, transform)

    def quad_bezier(self, start_pos, cp1, end_pos, steps=10,
                        transform=SVGTransformContext()):
        """Draw a quadratic bezier.
        """
        points = []
        for t in range(steps + 1):
            t = t / float(steps)
            x = (1 - t)**2 * start_pos[0] + 2 * t * (1 - t) * cp1[0] + t**2 * end_pos[0]
            y = (1 - t)**2 * start_pos[1] + 2 * t * (1 - t) * cp1[1] + t**2 * end_pos[1]
            points.append(Vector(x, y))
        self.add_points(points, transform)

    def cubic_bezier(self, start_pt, cp1, cp2, end_pt, steps=3,
                         transform=SVGTransformContext()):
        """Draw a cubic bezier.
        """
        # from http://www.pygame.org/wiki/BezierCurve
        p = (start_pt, cp1, cp2, end_pt)
        
        t = 1.0 / steps
        temp = t*t
        
        f = p[0]
        fd = 3 * (p[1] - p[0]) * t
        fdd_per_2 = 3 * (p[0] - 2 * p[1] + p[2]) * temp
        fddd_per_2 = 3 * (3 * (p[1] - p[2]) + p[3] - p[0]) * temp * t
        
        fddd = fddd_per_2 + fddd_per_2
        fdd = fdd_per_2 + fdd_per_2
        fddd_per_6 = fddd_per_2 * (1.0 / 3)
        
        points = []
        for x in range(steps):
            points.append(f)
            f = f + fd + fdd_per_2 + fddd_per_6
            fd = fd + fdd + fddd_per_2
            fdd = fdd + fddd
            fdd_per_2 = fdd_per_2 + fddd_per_2
        points.append(f)
        
        self.add_points(points, transform)

class SVGDrawer:
    def __init__(self, dom):
        self.lines = []
        SVGLineParser(self.lines, dom.documentElement)
    
    def fit(self, lines, dim):        
        lines = []
        
        smallest_x, smallest_y = 0, 0
        largest_x, largest_y = 0, 0
        
        for line in self.lines:
            for point in line:
                x, y = point
                if x < smallest_x: smallest_x = x
                if x > largest_x: largest_x = x
                if y < smallest_y: smallest_y = y
                if y > largest_y: largest_y = y
        
        width = largest_x - smallest_x
        height = largest_y - smallest_y
        ratio = resize_ratio(width, height, dim[0], dim[1])
        shift = map(int, Vector(-smallest_x, -smallest_y) * ratio +
                         Vector(dim[0] - width * ratio, dim[1] - height * ratio) / 2.0)
        
        return ratio, shift

    def draw(self, host, offset, dim):
        ratio, shift = self.fit(self.lines, dim)
        
        for line in self.lines:
            sx = offset[0] + int(line[0][0] * ratio) + shift[0]
            sy = offset[1] + int(line[0][1] * ratio) + shift[1]
            ex = offset[0] + int(line[1][0] * ratio) + shift[0]
            ey = offset[1] + int(line[1][1] * ratio) + shift[1]
            
            host.pos((sx, sy))
            host.ldown()
            host.pos((ex, ey))
            host.lup()
            
            yield

print "Loading source material..."

pos_delay = 0.005
evnt_delay = 0.005
# SVG
dim = (1000, 500)
dom = parse("avatar.svg")
drawer = SVGDrawer(dom)
# Image
# dim = 1 # Scale
# im = Image.open("img.png")
# drawer = ImageDrawer(im, vert_optimize=True)

print "Loaded!"

while True:    
    print("Press F4 to start drawing...")
    wait = InputWait(win32con.VK_F4, 0)
    wait.start()
    while wait.running:
        time.sleep(0.1)
        
    print("Press F4 to stop drawing...")
    wait = InputWait(win32con.VK_F4, 0)
    wait.start()

    offset = win32api.GetCursorPos()
    host = DrawerHost(drawer, offset, dim, pos_delay, evnt_delay)
    host.start()

    while True:
        if not wait.running:
            print("Drawing interrupted!")
            host.stop()
            break
        elif not host.running:
            print("Drawing COMPLETED!")
            print("Press F4 to end")
            while wait.running:
                time.sleep(0.1)
            break
        else:
            time.sleep(0.1)