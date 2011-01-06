#!/usr/bin/env python2.7
#
# checkworld.py - Minecraft Alpha/Beta world checker
# Copyright (c) 2010, 2011 sk89q <http://www.sk89q.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# $Id#

import sys
import os.path
import os
from glob import glob
import re
import io
import gzip
from struct import Struct
import argparse

tag_types = None

class CheckerException(Exception): pass
class FormatParseException(CheckerException): pass
class UnknownTagTypeError(FormatParseException): pass
class DuplicateNamedTagError(FormatParseException): pass
class UnexpectedTagError(FormatParseException): pass
class ValidationError(CheckerException): pass
class BadItemTypeError(ValidationError): pass

class BaseTag(object):
    unnamed = False
    def __init__(self, data, parent):
        self.data = data
        self.parent = parent
        self.name = "?"
    def __repr__(self):
        return repr(self.data)
    @classmethod
    def read(cls, reader, parent):
        return cls(cls.fmt.unpack(reader.read(cls.fmt.size))[0], parent)

class EndTag(BaseTag):
    unnamed = True
    def __init__(self):
        self.data = None

class ByteTag(BaseTag): fmt = Struct(">b")
class ShortTag(BaseTag): fmt = Struct(">h")
class IntTag(BaseTag): fmt = Struct(">i")
class LongTag(BaseTag): fmt = Struct(">q")
class FloatTag(BaseTag): fmt = Struct(">f")
class DoubleTag(BaseTag): fmt = Struct(">d")

class ByteArrayTag(BaseTag):
    def __repr__(self):
        return "<{0} bytes>".format(len(self.data))
    @classmethod
    def read(cls, reader, parent):
        size = IntTag.read(reader, None).data
        return ByteArrayTag(reader.read(size), parent)

class StringTag(BaseTag):
    @classmethod
    def read(cls, reader, parent):
        size = ShortTag.read(reader, None).data
        return StringTag(reader.read(size).decode("utf8"), parent)

class ListTag(BaseTag):
    def __len__(self):
        return len(self.data)
    def __getitem__(self, index):
        return self.data[index]
    def __repr__(self):
        return ",".join([repr(i) for i in self.data])
    @classmethod
    def read(cls, reader, parent):
        list_tag = ListTag([], parent)
        tag_id = ByteTag.read(reader, None).data
        tag_cls = tag_types[tag_id]
        count = IntTag.read(reader, None).data
        for tag in read_tags(reader, tag_id, count, list_tag):
            list_tag.data.append(tag)
        return list_tag

class CompoundTag(BaseTag):
    def __contains__(self, key):
        return key in self.data
    def __getitem__(self, key):
        return self.data[key]
    def __repr__(self):
        return "{" + ", ".join(["%s=%s" % (k, repr(self.data[k])) for k in self.data]) + "}"
    @classmethod
    def read(cls, reader, parent):
        compound_tag = CompoundTag({}, parent)
        for name, tag in read_named_tags(reader, compound_tag):
            if not tag.unnamed: # Ignore end tags
                if name in compound_tag.data:
                    raise DuplicateNamedTagError(name)
                compound_tag.data[name] = tag
        return compound_tag

tag_types = [
    EndTag, ByteTag, ShortTag, IntTag, LongTag, FloatTag, DoubleTag,
    ByteArrayTag, StringTag, ListTag, CompoundTag
]

def read_tags(reader, type_id, count, parent):
    try: 
        cls = tag_types[type_id]
    except IndexError:
        raise UnknownTagTypeError(type_id)
    for i in xrange(count):
        tag = cls.read(reader, parent)
        tag.name = str(i)
        yield tag

def read_named_tags(reader, parent, check_eof=False):
    fmt = read_named_tags.fmt
    while True:
        data = reader.read(fmt.size)
        if check_eof and len(data) == 0: break
        type_id = fmt.unpack(data)[0]
        if type_id == 0: # Special case: end tags
            yield None, EndTag()
            break
        else:
            name = StringTag.read(reader, None).data
            try:
                cls = tag_types[type_id]
            except IndexError:
                raise UnknownTagTypeError(type_id)
            tag = cls.read(reader, parent)
            tag.name = name
            yield name, tag
read_named_tags.fmt = Struct("b")

def get_path(tag):
    path = []
    cur = tag
    while cur != None:
        path.insert(0, cur.name)
        cur = cur.parent
    return "root" + ".".join(path)

class ChunkValidator(object):
    byte_fmt = Struct(">b")
    filename_match = re.compile(r"c\.(\-?[a-z0-9]+)\.(\-?[a-z0-9]+)\.dat$")

    def __init__(self, path):
        self.path = path
        m = self.filename_match.search(path)
        if not m:
            raise ValidationError("Invalid filename: " + path)
        try:
            self.expected_x = int(m.group(1), 36)
            self.expected_z = int(m.group(2), 36)
        except ValueError:
            raise ValidationError("Invalid filename (invalid coordinate): " + path)
    
    def is_valid_mob_id(self, name):
        return name == 'Mob'\
            or name == 'Monster'\
            or name == 'Creeper'\
            or name == 'Skeleton'\
            or name == 'Spider'\
            or name == 'Giant'\
            or name == 'Zombie'\
            or name == 'Slime'\
            or name == 'PigZombie'\
            or name == 'Ghast'\
            or name == 'Pig'\
            or name == 'Sheep'\
            or name == 'Cow'\
            or name == 'Chicken'
    
    def expect(self, tag, cond, msg):
        if not cond:
            raise ValidationError("Expected '{0}' ".format(get_path(tag)) + msg)
    
    def expect_valid_chest_item_id(self, tag, id):
        if id < 0 or (id >= 21 and id <= 34)\
                or id == 36\
                or (id >= 92 and id <= 255)\
                or (id >= 351 and id <= 2255)\
                or id >= 2258:
            raise ValidationError("Invalid item/block chest ID: '{0}' ".format(id))
    
    def expect_tag_type(self, tag, cls):
        if not isinstance(tag, cls):
            raise ValidationError("Expected '{0}' to be a {1}".format(get_path(tag), cls))
    
    def expect_compound_children(self, tag, validators):
        self.expect_tag_type(tag, CompoundTag)
        for name in validators:
            if name not in tag:
                raise ValidationError("Missing tag '{0}' in '{1}'".format(name, get_path(tag)))
            validators[name](tag[name])
    
    def expect_child_value(self, tag, name, cls, validate_func=None):
        self.expect(tag, name in tag, "to contain an '{0}' child tag".format(name))
        self.expect_tag_type(tag[name], cls)
        if validate_func != None:
            validate_func(tag, tag[name].data)
    
    def expect_x_inside_chunk(self, tag, x):
        if x < self.expected_x * 16 or x > self.expected_x * 16 + 16:
            raise ValidationError("Entity X coordinate is outside chunk in '{0}'"
                    .format(get_path(tag)))
    
    def expect_y_inside_chunk(self, tag, y):
        if y < 0 or y > 127:
            raise ValidationError("Entity Y coordinate is invalid in '{0}'"
                    .format(get_path(tag)))
    
    def expect_z_inside_chunk(self, tag, z):
        if z < self.expected_z * 16 or z > self.expected_z * 16 + 16:
            raise ValidationError("Entity z coordinate is outside chunkin '{0}'"
                    .format(get_path(tag)))
    
    def expect_valid_sign_text(self, tag, text):
        if len(text) > 15:
            raise ValidationError("Sign line is longer than 15 chars. in '{0}'"
                    .format(get_path(tag)))
    
    def expect_valid_mob_name(self, tag, mob_name):
        if not self.is_valid_mob_id(mob_name):
            raise ValidationError("Invalid mob name: " + mob_name)
    
    def expect_valid_mob_spawner_delay(self, tag, delay):
        if delay < 0:
            raise ValidationError("Mob spawner delay < 0 in '{0}'"
                    .format(get_path(tag)))
    
    def expected_valid_chest_items(self, tag, items):
        for item in items:
            self.expect_tag_type(item, CompoundTag)
            self.expect_child_value(item, "id", ShortTag, self.expect_valid_chest_item_id)
            self.expect_child_value(item, "Damage", ShortTag)
            self.expect_child_value(item, "Count", ByteTag)
            self.expect_child_value(item, "Slot", ByteTag)
    
    def validate_entity(self, tag):
        self.expect_tag_type(tag, CompoundTag)
        self.expect(tag, 'id' in tag, "to contain an 'id' child tag")
        id = tag['id'].data
        if self.is_valid_mob_id(id):
            pass # TODO: Validation
        elif id == 'Item' or id == 'Arrow' or id == 'Snowball'\
                or id == 'Egg' or id == 'Painting':
            pass # TODO: Validation
        elif id == 'Minecart' or id == 'Boat':
            pass # TODO: Validation
        elif id == 'PrimedTnt' or id == 'FallingSand':
            pass # TODO: Validation
        else:
            raise ValidationError("Unknown entity type '{0}' in '{1}'"
                    .format(id, get_path(tag)))
    
    def validate_tile_entity(self, tag):
        self.expect_tag_type(tag, CompoundTag)
        self.expect(tag, 'id' in tag, "to contain an 'id' child tag")
        self.expect_child_value(tag, 'x', IntTag, self.expect_x_inside_chunk)
        self.expect_child_value(tag, 'y', IntTag, self.expect_y_inside_chunk)
        self.expect_child_value(tag, 'z', IntTag, self.expect_z_inside_chunk)
        id = tag['id'].data
        if id == 'Furnance':
            self.expect_child_value(tag, "BurnTime", ShortTag)
        elif id == 'Sign':
            self.expect_child_value(tag, "Text1", StringTag, self.expect_valid_sign_text)
            self.expect_child_value(tag, "Text2", StringTag, self.expect_valid_sign_text)
            self.expect_child_value(tag, "Text3", StringTag, self.expect_valid_sign_text)
            self.expect_child_value(tag, "Text4", StringTag, self.expect_valid_sign_text)
        elif id == 'MobSpawner':
            self.expect_child_value(tag, "EntityId", StringTag, self.expect_valid_mob_name)
            self.expect_child_value(tag, "Delay", ShortTag, self.expect_valid_mob_spawner_delay)
        elif id == 'Chest':
            self.expect_child_value(tag, "Items", ListTag, self.expected_valid_chest_items)
        else:
            raise ValidationError("Unknown title entity type '{0}' in '{1}'"
                    .format(id, get_path(tag)))
    
    def validate_blocks(self, tag):
        self.expect_tag_type(tag, ByteArrayTag)
        self.expect(tag, len(tag.data) == 32768, "to be 32768 bytes long")
        for i in xrange(0, len(tag.data)):
            block_id = self.byte_fmt.unpack(tag.data[i])[0]
            if block_id < 0 or (block_id >= 21 and block_id <= 34)\
                    or block_id == 36 or block_id >= 92:
                raise ValidationError("Invalid block ID: {0}".format(block_id))
    
    def validate_data(self, tag):
        self.expect_tag_type(tag, ByteArrayTag)
        self.expect(tag, len(tag.data) == 16384, "to be 16384 bytes long")
        # NOTE: Does not do deep checking
    
    def validate_sky_light(self, tag):
        self.expect_tag_type(tag, ByteArrayTag)
        self.expect(tag, len(tag.data) == 16384, "to be 16384 bytes long")
        # NOTE: Does not do deep checking (does it matter?)
    
    def validate_block_light(self, tag):
        self.expect_tag_type(tag, ByteArrayTag)
        self.expect(tag, len(tag.data) == 16384, "to be 16384 bytes long")
        # NOTE: Does not do deep checking (does it matter?)
    
    def validate_height_map(self, tag):
        self.expect_tag_type(tag, ByteArrayTag)
        self.expect(tag, len(tag.data) == 256, "to be 256 bytes long")
        # NOTE: Does not do deep checking (does it matter?)
    
    def validate_entities(self, tag):
        self.expect_tag_type(tag, ListTag)
        for child in tag:
            self.validate_entity(child)
    
    def validate_tile_entities(self, tag):
        self.expect_tag_type(tag, ListTag)
        for child in tag:
            self.validate_tile_entity(child)
    
    def validate_last_update(self, tag):
        self.expect_tag_type(tag, LongTag)
    
    def validate_terrain_populated(self, tag):
        self.expect_tag_type(tag, ByteTag)
        if tag.data != 0 and tag.data != 1:
            raise ValidationError("TerrainPopulated is neither '0' nor '1'")
    
    def validate_xpos(self, tag):
        self.expect_tag_type(tag, IntTag)
        if tag.data != self.expected_x:
            raise ValidationError("xPos in file does not match filename")
    
    def validate_zpos(self, tag):
        self.expect_tag_type(tag, IntTag)
        if tag.data != self.expected_z:
            raise ValidationError("zPos in file does not match filename")

    def validate_level_tag(self, tag):
        self.expect_compound_children(tag, {
            'Blocks': self.validate_blocks,
            'Data': self.validate_data,
            'SkyLight': self.validate_sky_light,
            'BlockLight': self.validate_block_light,
            'HeightMap': self.validate_height_map,
            'Entities': self.validate_entities,
            'TileEntities': self.validate_tile_entities,
            'LastUpdate': self.validate_last_update,
            'TerrainPopulated': self.validate_terrain_populated,
            'xPos': self.validate_xpos,
            'zPos': self.validate_zpos,
        })
        
    def validate_root_tag(self, tag):
        self.expect_compound_children(tag, {
            'Level': self.validate_level_tag,
        })

    def validate(self):
        f = gzip.open(self.path, 'rb')
        reader = io.BufferedReader(f)
        found = 0
        for name, tag in read_named_tags(reader, None, check_eof=True):
            if not isinstance(tag, CompoundTag):
                raise UnexpectedTagError("Root tag expected to be a compound tag")
            if found != 0:
                raise UnexpectedTagError("Only one root tag expected")
            self.validate_root_tag(tag)
            found = found + 1


def main():
    epilog = """
checkworld.py does a deep strict validation of the world files of a Minecraft
Alpha/Beta server. It is designed to be run on world files that have not
had additional entity types added (through mods). Currently the program does
not perform a deep check on entities, although it does check for acceptable
entity types. For all other cases, checkworld.py does a very strict and
deep check, down to acceptable item and block IDs. Only chunk files are checked."""

    parser = argparse.ArgumentParser(prog='checkworld.py',
                                     description='Checks a Minecraft Alpha/Beta world',
                                     epilog=epilog)
    parser.add_argument('--world', metavar='world', type=str, nargs='?',
                        default='world',
                        help='world directory')
    parser.add_argument('--write-bad-chunks', dest='write_bad', metavar='filename', type=str,
                        help='write bad chunks to a file, optionally specifying a filename')
    parser.add_argument('action', metavar='action', type=str,
                        choices=['validate'],
                        help='an action to perform')

    args = parser.parse_args()
    world = args.world
    action = args.action
    write_bad_chunks = args.write_bad
    
    print("checkworld.py - Minecraft Alpha/Beta world checker")
    print("Copyright (c) 2010, 2011 sk89q <http://www.sk89q.com>")
    print("")
    
    print("Looking for chunk files...")
    files = glob(os.path.join(world, "*/*/c.*.dat"))
    total = len(files)
    
    if total == 0:
        print("error: Failed to find chunk files")
        sys.exit(1)
    
    bad_chunk_f = None
    if write_bad_chunks != None:
        try:
            bad_chunk_f = open(write_bad_chunks, "wb")
        except IOError, e:
            print("error: Could not open bad chunks output file")
            sys.exit(2)
    
    print("Found {0} chunk files; now validating...".format(total))
    
    i = 0
    corrupt = 0
    for path in files:
        progress = i / float(total)
        rel_path = os.path.relpath(path, world)
        print("[{0}/{1} {2}% {3}] {4}".format(i + 1, total, int(progress * 100), corrupt, rel_path))
        try:
            ChunkValidator(path).validate()
        except Exception, e:
            corrupt = corrupt + 1
            print("BAD CHUNK: " + e.message)
            if bad_chunk_f != None:
                try:
                    bad_chunk_f.write(path + "\r\n")
                    bad_chunk_f.write("# " + e.message.replace("\r", "").replace("\n", "") + "\r\n")
                except IOError, e:
                    print("error: Failed to write bad chunk output file")
        i = i + 1
    
    if bad_chunk_f != None:
        try:
            bad_chunk_f.close()
        except IOError: pass
    
    print("Scanned with {0} corrupt chunk(s) detected.".format(corrupt))

if __name__ == "__main__":
    main()