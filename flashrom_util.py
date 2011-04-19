#!/usr/bin/env python
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# THIS FILE IS COPIED FROM AUTOTEST LIBRARY AND FOLLOWING PEP8 CODING STYLE RULE
# FOR BACKWARD COMPATIBLE, WE'RE NOT CHANGING ITS INDENTATION AND FUNCTION NAMES

"""
This module provides convenience routines to access Flash ROM (EEPROM).
 - flashrom_util is a low level wrapper of flashrom(8) program.
 - FlashromUtility is a high level object which provides more advanced
   features like journaling-alike (log-based) changing.

Original tool syntax:
    (common) -p internal:bus=BUS (BUS: BIOS=spi, EC=lpc)
    (read ) flashrom -r <file>
    (write) flashrom -l <layout_fn> [-i <image_name> ...] -w <file>

The layout_fn is in format of
    address_begin:address_end image_name
    which defines a region between (address_begin, address_end) and can
    be accessed by the name image_name.

Currently the tool supports multiple partial write but not partial read.

For more information, see help(flashrom_util.flashrom_util) and
help(flashrom_util.FlashromUtility).
"""

import os
import re
import subprocess
import sys
import tempfile
import types

import fmap

# Constant Values -----------------------------------------------------------

# The location of flashrom(8)' tool binary
DEFAULT_FLASHROM_TOOL_PATH = '/usr/sbin/flashrom'

# The default target names for BIOS and Embedded Controller (EC)
DEFAULT_TARGET_NAME_BIOS = 'bios'
DEFAULT_TARGET_NAME_EC = 'ec'

# The default description of ChromeOS firmware layout
# Check help(compile_layout) for the syntax.
# NOTE: Since the memory layout of BIOS may change very often,
#       the default layout is removed to prevent confusion.
#       Any BIOS image without FMAP is considered as corrupted.
DEFAULT_CHROMEOS_FIRMWARE_LAYOUT_DESCRIPTIONS = {
    "bios": "",  # retrieve from fmap, no defaults.
    "ec": """
            EC_RO
            |
            EC_RW
          """,
}

# The default conversion table for fmap_decode for legacy firmware (ex, CR48)
DEFAULT_CHROMEOS_FMAP_CONVERSION = {
    "Boot Stub": "BOOT_STUB",
    "GBB Area": "GBB",
    "Recovery Firmware": "RECOVERY",
    "RO VPD": "RO_VPD",
    "Firmware A Key": "VBLOCK_A",
    "Firmware A Data": "FW_MAIN_A",
    "Firmware B Key": "VBLOCK_B",
    "Firmware B Data": "FW_MAIN_B",
    "RW VPD": "RW_VPD",
}

# Default "skip" sections when verifying section data.
# This is required because some flashrom chip may create timestamps (or checksum
# values) when (or immediately after) we change flashrom content.
# The syntax is a comma-separated list of string tuples (separated by ':'):
# PARTNAME:OFFSET:SIZE
# If there's no need to skip anything, provide an empty list [].
DEFAULT_CHROMEOS_FIRMWARE_SKIP_VERIFY_LIST = {
    "bios": [],
    "ec": "EC_RO:0x48:4",
}

# Default target selection commands, by machine architecture
# Syntax: { 'arch_regex': exec_script, ... }
DEFAULT_ARCH_TARGET_MAP = {
    '^x86|^i\d86': {
        # The magic numbers here are register indexes and values that apply
        # to all current known x86 based ChromeOS devices.
        # Detail information is defined in section #"10.1.50 GCS-General
        # Control and Status Register" of document "Intel NM10 Express
        # Chipsets".
        "bios": '-p internal:bus=spi',
        "ec":   '-p internal:bus=lpc',
    },
}


# ---------------------------------------------------------------------------
# simple layout description language compiler
def compile_layout(desc, size):
    """ compile_layout(desc, size) -> layout

    Compiles a flashrom layout by simple description language.
    Returns the result as a map. Empty map for any error.

    syntax:       <desc> ::= <partitions>
            <partitions> ::= <partition>
                           | <partitions> '|' <partition>
             <partition> ::= <spare_section>
                           | <partition> ',' <section>
                           | <section> ',' <partition>
               <section> ::= <name> '=' <size>
         <spare_section> ::= '*'
                           | <name>
                           | <name> '=' '*'

     * Example: 'ro|rw', 'ro=0x1000,*|*,rw=0x1000'
     * Each partition share same space from total size of flashrom.
     * Sections are fix sized, or "spare" which consumes all remaining
       space from a partition.
     * You can use any non-zero decimal or heximal (0xXXXX) in <size>.
       (size as zero is reserved now)
     * You can use '*' as <name> for "unamed" items which will be ignored in
       final layout output.
     * You can use "<name>=*" or simply "<name>" (including '*', the
       'unamed section') to define spare section.
     * There must be always one (no more, no less) spare section in
       each partition.
    """
    # create an empty layout first
    layout = {}
    err_ret = {}

    # prepare: remove all spaces (literal from string.whitespace)
    desc = ''.join([c for c in desc if c not in '\t\n\x0b\x0c\r '])
    # find equally-sized partitions
    parts = desc.split('|')
    block_size = size / len(parts)
    offset = 0

    for part in parts:
        sections = part.split(',')
        sizes = []
        names = []
        spares = 0

        for section in sections:
            # skip empty section to allow final ','
            if section == '':
                continue
            # format name=v or name ?
            if section.find('=') >= 0:
                k, value = section.split('=')
                if value == '*':
                    value = 0            # spare section
                else:
                    value = int(value, 0)
                    if value == 0:
                        raise ValueError('Using size as 0 is prohibited now.')
            else:
                k, value = (section, 0)  # spare, should appear for only one.
            if value == 0:
                spares = spares + 1
            names.append(k)
            sizes.append(value)

        if spares != 1:
            # each partition should have exactly one spare field
            return err_ret

        spare_size = block_size - sum(sizes)
        sizes[sizes.index(0)] = spare_size
        # fill sections
        for i in range(len(names)):
            # ignore unamed sections
            if names[i] != '*':
                layout[names[i]] = (offset, offset + sizes[i] - 1)
            offset = offset + sizes[i]

    return layout


def _convert_fmap_layout(conversion_map, fmap_areas):
    """
    (internal utility) Converts a FMAP areas structure to flashrom layout format
                       by conversion_map.
    Args:
        conversion_map: dictionary of names to convert.
        fmap_areas: a list of {name, offset, size} dictionary.

    Returns: layout structure for flashrom_util, or empty for failure.
    """
    layout = {}
    for entry in fmap_areas:
        name = entry['name']
        offset = entry['offset']
        size = entry['size']
        if name in conversion_map:
            name = conversion_map[name]
        name = name.replace(' ', '%20')
        layout[name] = (offset, offset + size - 1)
    return layout


def decode_fmap_layout(conversion_map, image_blob):
    """
    (Utility) Uses fmap_decode to retrieve embedded layout of a prepared
              firmware image.
    Args:
        conversion_map: dictionary for FMAP area name conversion
        image_blob: binary data of firmware image containing FMAP

    Returns: layout structure for flashrom_util, or empty for failure.
    """
    try:
        fmap_object = fmap.fmap_decode(image_blob)['areas']
    except:
        # print 'decode_fmap_layout: failed to decode from image blob'
        fmap_object = []
    return _convert_fmap_layout(conversion_map, fmap_object)


def csv_to_list(csv, delimiter=','):
    """
    (Utility) Converts a comma-separated-value (or list) to a list.

    To use symbols other that comma, customize with delimiter.
    """
    if isinstance(csv, types.StringTypes):
        return [i.strip() for i in csv.split(delimiter)]
    return csv


def _dummy(*_, **__):
    """ Dummy function. """
    pass

def _default_system_output(command, ignore_status):
    """ Stub for default system_output function. """
    return utils.system_output(command, ignore_status=ignore_status)

def _default_system(command, ignore_status):
    """ Stub for default system function. """
    return utils.system(command, ignore_status=ignore_status)

# ---------------------------------------------------------------------------
# flashrom utility wrapper
class flashrom_util(object):
    """ a wrapper for "flashrom" utility.

    You can read, write, or query flash ROM size with this utility.
    Although you can do "partial-write", the tools always takes a
    full ROM image as input parameter.

    NOTE before accessing flash ROM, you may need to first "select"
    your target - usually BIOS or EC. That part is not handled by
    this utility. Please find other external script to do it.

    To perform a read, you need to:
     1. Prepare a flashrom_util object
        ex: flashrom = flashrom_util.flashrom_util()
     2. Decide target (BIOS/EC)
        ex: flashrom.select_bios_flashrom()
     3. Perform read operation
        ex: image = flashrom.read_whole()

    To perform a (partial) write, you need to:
     1. Select target (BIOS/EC)
        ex: flashrom.select_ec_flashrom()
     2. Create or load a layout map (see explain of layout below)
        ex: layout_map = { 'all': (0, rom_size - 1) }
        ex: layout_map = { 'ro': (0, 0xFFF), 'rw': (0x1000, rom_size-1) }
        You can also use built-in layout like detect_chromeos_bios_layout(),
        detect_chromeos_layout(), or detect_layout() to build the layout maps.
     3. Prepare a full base image
        ex: image = flashrom.read_whole()
        ex: image = chr(0xFF) * rom_size
     4. (optional) Modify data in base image
        ex: new_image = flashrom.put_section(image, layout_map, 'all', mydata)
     5. Perform write operation
        ex: flashrom.write_partial(new_image, layout_map, ('all',))

     P.S: you can also create the new_image in your own way, for example:
        rom_size = flashrom_util.get_size()
        erase_image = chr(0xFF) * rom_size
        flashrom.write_partial(erase_image, layout_map, ('all',))

    The layout is a dictionary of { 'name': (address_begin, addres_end) }.
    Note that address_end IS included in the range.
    See help(detect_layout) for easier way to generate layout maps.

    Attributes:
        tool_path: file path to the tool 'flashrom'
        cmd_prefix: prefix of every shell cmd, ex: "PATH=.:$PATH;export PATH;"
        cmd_current: combined by tool_path, cmd_prefix and selected target
        tmp_root: a folder name for mkstemp (for temp of layout and images)
        keep_temp_files: boolean flag to control cleaning of temporary files
        target_map: map of what commands should be invoked to switch targets.
                    if you don't need any commands, use empty dict {}.
                    if you want default detection, use None (default param).
        exception_type: the type of exception to raise for errors.
        verbose_msg: a function to be called with debugging/helpful messages.
        system_output: a function to receive shell command output.
        system: a function to execute shell command and return results
    """

    TARGET_BIOS = DEFAULT_TARGET_NAME_BIOS
    TARGET_EC = DEFAULT_TARGET_NAME_EC

    def __init__(self,
                 tool_path=DEFAULT_FLASHROM_TOOL_PATH,
                 cmd_prefix='',
                 tmp_root=None,
                 keep_temp_files=False,
                 target_map=None,
                 exception_type=Exception,
                 verbose_msg=_dummy,
                 system_output=_default_system_output,
                 system=_default_system,
                 ):
        """ constructor of flashrom_util. help(flashrom_util) for more info """
        self.exception_type = exception_type
        self.tool_path = tool_path
        self.cmd_prefix = cmd_prefix
        self.tmp_root = tmp_root
        self.keep_temp_files = keep_temp_files
        self.target_map = target_map
        self.is_debug = False
        self.verbose_msg = verbose_msg
        self.system_output = system_output
        self.system_exit_code = system
        # detect bbs map if target_map is None.
        # NOTE when target_map == {}, that means "do not execute commands",
        # different to default value.
        if isinstance(target_map, types.NoneType):
            # generate default target map
            self.target_map = self.detect_target_map()
        # command for current target
        self.cmd_current = '%s"%s"' % (self.cmd_prefix, self.tool_path)

    def _error_die(self, message):
        ''' (internal) raises a critical exception on un-recoverable errors. '''
        raise self.exception_type('%s: %s' % (self.__class__.__name__,
                                              str(message)))

    def _get_temp_filename(self, prefix):
        ''' (internal) Returns name of a temporary file in self.tmp_root '''
        (handle, name) = tempfile.mkstemp(prefix=prefix, dir=self.tmp_root)
        os.close(handle)
        return name

    def _remove_temp_file(self, filename):
        """ (internal) Removes a temp file if self.keep_temp_files is false. """
        if self.keep_temp_files:
            return
        if os.path.exists(filename):
            os.remove(filename)

    def _create_layout_file(self, layout_map):
        '''
        (internal) Creates a layout file based on layout_map.
        Returns the file name containing layout information.
        '''
        layout_text = ['0x%08lX:0x%08lX %s' % (v[0], v[1], k)
            for k, v in layout_map.items()]
        layout_text.sort()  # unstable if range exceeds 2^32
        tmpfn = self._get_temp_filename('lay')
        open(tmpfn, 'wb').write('\n'.join(layout_text) + '\n')
        return tmpfn

    def system(self, cmd):
          ''' (internal) Returns if cmd is successfully executed. '''
          return self.system_exit_code(cmd, ignore_status=True) == 0

    def get_section(self, base_image, layout_map, section_name):
        '''
        Retrieves a section of data based on section_name in layout_map.
        Raises error if unknown section or invalid layout_map.
        '''
        assert section_name in layout_map, "Invalid section: " + section_name
        pos = layout_map[section_name]
        if pos[0] >= pos[1] or pos[1] >= len(base_image):
            self._error_die('INTERNAL ERROR: invalid layout map: %s.' %
                            section_name)
        return base_image[pos[0] : pos[1] + 1]

    def put_section(self, base_image, layout_map, section_name, data):
        '''
        Updates a section of data based on section_name in layout_map.
        Raises error if unknown section or invalid layout_map.
        Returns the full updated image data.
        '''
        assert section_name in layout_map, "Invalid section: " + section_name
        pos = layout_map[section_name]
        if pos[0] >= pos[1] or pos[1] >= len(base_image):
            self._error_die('INTERNAL ERROR: invalid layout map.')
        if len(data) != pos[1] - pos[0] + 1:
            self._error_die('INTERNAL ERROR: unmatched data size.')
        return base_image[0 : pos[0]] + data + base_image[pos[1] + 1 :]

    def get_size(self):
        """ Gets size of current flash ROM """
        cmd = '%s --get-size | grep "^[0-9]"' % (self.cmd_current)
        self.verbose_msg('flashrom_util.get_size(): ' + cmd)
        output = self.system_output(cmd, ignore_status=True)
        last_line = output.strip()
        try:
            size = long(last_line)
        except ValueError:
            self._error_die('INTERNAL ERROR: unable to get the flash size.')
        self.verbose_msg('flashrom_util.get_size(): got %d' % size)
        return size

    def detect_target_map(self):
        """
        Detects the target selection map.
        Use machine architecture in current implementation.
        """
        arch = utils.get_arch()
        for regex, target_map in DEFAULT_ARCH_TARGET_MAP.items():
            if re.match(regex, arch):
                return target_map
        self._error_die('INTERNAL ERROR: unknown architecture, need target_map')

    def detect_layout(self, layout_desciption, size, image):
        """
        Detects and builds layout according to current flash ROM size
        (or image) and a simple layout description language.

        NOTE: if you don't trust any available FMAP layout information in
              flashrom image, pass image = None.

        Args:
            layout_description: Pre-defined layout description. See
                help(flashrom_util.compile_layout) for syntax detail.
            size: Size of flashrom. If size is None, self.get_size()
                will be called.
            image: (optional) Flash ROM image that contains FMAP layout info.
                If image is None, layout will be calculated by size only.

        Returns the layout map (empty if any error).
        """
        ret = None
        if image:
            if self.is_debug:
                print " * detect_layout: try FMAP"
            ret = decode_fmap_layout(DEFAULT_CHROMEOS_FMAP_CONVERSION, image)
        if not ret:
            if not size:
                size = self.get_size()
            ret = compile_layout(layout_desciption, size)
            if self.is_debug:
                print " * detect_layout: using pre-defined memory layout"
        elif self.is_debug:
            print " * detect_layout: using FMAP layout in firmware image."
        return ret

    def detect_chromeos_layout(self, target, size, image):
        """
        Detects and builds ChromeOS firmware layout according to current flash
        ROM size.  Currently supported targets are: 'bios' or 'ec'.

        See help(flashrom_util.flashrom_util.detect_layout) for detail
        information of argument size and image.

        Returns the layout map (empty if any error).
        """
        assert target in DEFAULT_CHROMEOS_FIRMWARE_LAYOUT_DESCRIPTIONS, \
                'unknown layout target: ' + target
        chromeos_target = DEFAULT_CHROMEOS_FIRMWARE_LAYOUT_DESCRIPTIONS[target]
        return self.detect_layout(chromeos_target, size, image)

    def detect_chromeos_bios_layout(self, size, image):
        """ Detects standard ChromeOS BIOS layout.
            A short cut to detect_chromeos_layout(TARGET_BIOS, size, image). """
        return self.detect_chromeos_layout(self.TARGET_BIOS, size, image)

    def detect_chromeos_ec_layout(self, size, image):
        """ Detects standard ChromeOS Embedded Controller layout.
            A short cut to detect_chromeos_layout(TARGET_EC, size, image). """
        return self.detect_chromeos_layout(self.TARGET_EC, size, image)

    def read_whole_to_file(self, output_file):
        '''
        Reads whole flash ROM data to a file.
        Returns True on success, otherwise False.
        '''
        cmd = '%s -r "%s"' % (self.cmd_current, output_file)
        self.verbose_msg('flashrom_util.read_whole_to_file(): ' + cmd)
        return self.system(cmd)

    def read_whole(self):
        '''
        Reads whole flash ROM data.
        Returns the data read from flash ROM, or empty string for other error.
        '''
        result = ''
        tmpfn = self._get_temp_filename('rd_')
        if self.read_whole_to_file(tmpfn):
            try:
                result = open(tmpfn, 'rb').read()
            except IOError:
                result = ''

        # clean temporary resources
        self._remove_temp_file(tmpfn)
        return result

    def _write_flashrom(self, base_image, layout_map, write_list):
        '''
        (internal) Writes data in sections of write_list to flash ROM.
        If layout_map and write_list are both empty, write whole image.
        Returns True on success, otherwise False.
        '''
        cmd_layout = ''
        cmd_list = ''
        layout_fn = ''

        if write_list:
            assert layout_map, "Partial writing to flash requires layout"
            assert set(write_list).issubset(layout_map.keys())
            layout_fn = self._create_layout_file(layout_map)
            cmd_layout = '-l "%s" ' % (layout_fn)
            cmd_list = '-i %s ' % ' -i '.join(write_list)
        else:
            assert not layout_map, "Writing whole flash does not allow layout"

        tmpfn = self._get_temp_filename('wr_')
        open(tmpfn, 'wb').write(base_image)

        cmd = '%s %s%s -w "%s"' % (self.cmd_current,
                                   cmd_layout,
                                   cmd_list,
                                   tmpfn)

        self.verbose_msg('flashrom._write_flashrom(): ' + cmd)
        result = self.system(cmd)

        # clean temporary resources
        self._remove_temp_file(tmpfn)
        if layout_fn:
            self._remove_temp_file(layout_fn)
        return result

    def write_whole(self, base_image):
        '''
        Writes whole image to flashrom.
        Returns True on success, otherwise False.
        '''
        assert base_image, "You must provide full image."
        return self._write_flashrom(base_image, [], [])

    def write_partial(self, base_image, layout_map, write_list):
        '''
        Writes data in sections of write_list to flash ROM.
        Returns True on success, otherwise False.
        '''
        assert write_list, "You need to provide something to write."
        return self._write_flashrom(base_image, layout_map, write_list)

    def enable_write_protect(self, layout_map, section):
        '''
        Enables the "write protection" for specified section on flashrom.

        WARNING: YOU CANNOT CHANGE FLASHROM CONTENT AFTER THIS CALL.
        '''
        if section not in layout_map:
            self._error_die('INTERNAL ERROR: unknown section.')
        # syntax: flashrom --wp-range offset size
        #         flashrom --wp-enable
        # NOTE: wp-* won't return error value even if they failed to change
        # the value/status due to WP already enabled, so we can't rely on the
        # return value; the real status must be verified by --wp-status.
        addr = layout_map[section]
        cmd = ('%s --wp-disable && '
               '%s --wp-range 0x%06X 0x%06X && '
               '%s --wp-enable' % (
                       self.cmd_current,
                       self.cmd_current, addr[0], addr[1] - addr[0] + 1,
                       self.cmd_current))
        self.verbose_msg('flashrom.enable_write_protect(): ' + cmd)
        return self.system(cmd)

    def disable_write_protect(self):
        '''
        Disables whole "write protection" range and status.
        '''
        # syntax: flashrom --wp-range offset size
        #         flashrom --wp-disable
        cmd = '%s --wp-disable && %s --wp-range 0 0' % (
                self.cmd_current, self.cmd_current)
        self.verbose_msg('flashrom.disable_write_protect(): ' + cmd)
        return self.system(cmd)

    def verify_write_protect(self, layout_map, section):
        '''
        Verifies if write protection is configured correctly.
        '''
        if section not in layout_map:
            self._error_die('INTERNAL ERROR: unknown section.')
        # syntax: flashrom --wp-status
        addr = layout_map[section]
        cmd = '%s --wp-status | grep "^WP: "' % (self.cmd_current)
        self.verbose_msg('flashrom.verify_write_protect(): ' + cmd)
        results = self.system_output(cmd, ignore_status=True).splitlines()
        # output: WP: status: 0x80
        #         WP: status.srp0: 1
        #         WP: write protect is %s. (disabled/enabled)
        #         WP: write protect range: start=0x%8x, len=0x%08x
        wp_enabled = None
        wp_range_start = -1
        wp_range_len = -1
        for result in results:
            result = result.strip()
            if result.startswith('WP: write protect is '):
                result = result.rpartition(' ')[-1].strip('.')
                if result == 'enabled':
                    wp_enabled = True
                elif result == 'disabled':
                    wp_enabled = False
                else:
                    self.verbose_msg('flashrom.verify_write_protect: '
                                     'unknown status: ' + result)
                continue
            if result.startswith('WP: write protect range: '):
                value_start = re.findall('start=[0-9xXa-fA-F]+', result)
                value_len = re.findall('len=[0-9xXa-fA-F]+', result)
                if value_start and value_len:
                    wp_range_start = int(value_start[0].rpartition('=')[-1], 0)
                    wp_range_len = int(value_len[0].rpartition('=')[-1], 0)
                continue
        self.verbose_msg(' wp_enabled: %s' % wp_enabled)
        self.verbose_msg(' wp_range_start: %s' % wp_range_start)
        self.verbose_msg(' wp_range_len: %s' % wp_range_len)
        if (wp_enabled == None) or ((wp_range_start < 0) or (wp_range_len < 0)):
            self.verbose_msg('flashrom.verify_write_protect(): invalid output: '
                             + '\n'.join(results))
            return False

        # expected: enabled, and correct range
        addr = layout_map[section]
        addr_start = addr[0]
        addr_len = addr[1] - addr[0] + 1
        if (wp_range_start != addr_start) or (wp_range_len != addr_len):
            self.verbose_msg(
                'flashrom.verify_write_protect(): unmatched range: '
                'current (%08lx, %08lx), expected (%08lx,%08lx)' %
                (wp_range_start, wp_range_len, addr_start, addr_len))
            return False
        if not wp_enabled:
            self.verbose_msg('flashrom.verify_write_protect(): '
                             'write protect is not enabled.')
            return False

        # everything is correct.
        return True

    def select_target(self, target):
        '''
        Selects (usually by setting BBS register) a target defined in target_map
        and then directs all further firmware access to certain region.
        '''
        assert target in self.target_map, "Unknown target: " + target
        if not self.target_map[target]:
            return True
        self.verbose_msg('flashrom.select_target("%s"): %s' %
                         (target, self.target_map[target]))
        # command for current target
        self.cmd_current = '%s"%s" %s ' % (self.cmd_prefix,
                                           self.tool_path,
                                           self.target_map[target])
        return True

    def select_bios_flashrom(self):
        ''' Directs all further accesses to BIOS flash ROM. '''
        return self.select_target(self.TARGET_BIOS)

    def select_ec_flashrom(self):
        ''' Directs all further accesses to Embedded Controller flash ROM. '''
        return self.select_target(self.TARGET_EC)


# ---------------------------------------------------------------------------
# Advanced flashrom utiliity
class FlashromUtility(object):
    """
    A high level (easier to use and more advanced) utility class to access
    flashrom. FlashromUtility supports general read and journaling-alike (log
    based) style write functionality.

    To use it, first initialize, read/update section data, and finally commit.
    Example:
        flashrom = FlashromUtility()
        flashrom.initialize(flashrom.TARGET_BIOS)

        # quick access to section data
        data = flashrom.read_section('FW_MAIN_A')
        flashrom.write_section('FW_MAIN_A', data)

        # compare section data
        if flashrom.verify_sections('A,B', 'C,D', image1, image2):
            print "same contents!"

        # copy between sections
        flashrom.image_copy(list_A, list_B, image);  # copy A in image to B

        # check if really need to perform writing to flashrom
        if flashrom.need_commit():
            print "need to rewrite the flash..."

        # perform real write operation
        flashrom.commit()

    Attributes
        flashrom:       instance of flashrom_util
        current_image:  cached image data of current flashrom
        layout:         the Chrome OS firmware layout for flashrom to use
        whole_flash_layout: a special layout to contain whole flashrom space
        skip_verify:    a description of what data must be skipped when
                        doing compare / verification
        change_history: a list of every change we should apply when committing.
                        each item is (changed_list, image_data).

        verbose_msg:    function to report verbose messages.
    """

    TARGET_BIOS = DEFAULT_TARGET_NAME_BIOS
    TARGET_EC = DEFAULT_TARGET_NAME_EC

    def __init__(self,
                 flashrom_util_instance=None,
                 exception_type=Exception,
                 verbose_msg=_dummy,
                 system_output=_default_system_output,
                 ):
        """
        Initializes internal variables and states.

        Arguments:
            flashrom_util_instance: An instance of existing flashrom_util.  If
                                    not provided, FlashromUtility will create
                                    one with all default values.
        """
        self.exception_type = exception_type
        self.flashrom = flashrom_util_instance
        if not self.flashrom:
            self.flashrom = flashrom_util(verbose_msg=verbose_msg,
                                          exception_type=exception_type,
                                          system_output=system_output)
        self.current_image = None
        self.target_file = None
        self.layout = None
        self.whole_flash_layout = None
        self.skip_verify = None
        self.change_history = []
        self.verbose_msg = verbose_msg
        self.is_debug = False

    def _error_die(self, message):
        ''' (internal) raises a critical exception on un-recoverable errors. '''
        raise self.exception_type('%s: %s' % (self.__class__.__name__,
                                              str(message)))

    def initialize(self, target, layout_image=None, layout_desc=None,
                   use_fmap_layout=True, skip_verify=None, target_file=None):
        """
        Starts flashrom initialization with given target.

        Args:
            target: Name of the target you are dealing with (check TARGET_*)
            layout_desc: (optional) Description of pre-defined layout
            layout_image: (optional) A image blob containing FMAP for building
                layout. None if you want to use current system flash content
            use_fmap_layout: Use True (default) if you trust the FMAP in
                layout_image.
            skip_verify: (optional) Description of what data must be skipped
                when doing comparison / verification.
            target_file: (optional) An firmware image file for processing
                instead of system flashrom.
        """
        flashrom = self.flashrom
        if not target_file and not flashrom.select_target(target):
            self._error_die("Cannot Select Target. Abort.")
        else:
            self.target_file = target_file

        self.verbose_msg(" - reading current content")
        self.current_image = self._perform_read_flash()

        if not self.current_image:
            self._error_die("Cannot read flashrom image. Abort.")
        flashrom_size = len(self.current_image)

        if not use_fmap_layout:
            layout_image = None
        elif not layout_image:
            layout_image = self.current_image

        if layout_desc:
            layout = flashrom.detect_layout(
                    layout_desc, flashrom_size, layout_image)
        else:
            layout = flashrom.detect_chromeos_layout(
                    target, flashrom_size, layout_image)
        self.layout = layout
        self.whole_flash_layout = flashrom.detect_layout('all', flashrom_size,
                                                         None)
        if not skip_verify:
            skip_verify = DEFAULT_CHROMEOS_FIRMWARE_SKIP_VERIFY_LIST[target]
        self.skip_verify = skip_verify
        self.change_history = []  # reset list

    def get_current_image(self):
        """ Returns current flashrom image (physically, not changed) """
        return self.current_image

    def get_latest_changed_image(self):
        """ Returns the latest changed result image (not written yet) """
        if not self.change_history:
            return self.get_current_image()
        # the [1] refers to the latter element of (changed_list, image_data)
        return self.change_history[-1][1]

    def need_commit(self):
        """ Returns if we have uncommitted changes """
        if self.change_history:
            return True
        return False

    def image_copy(self, from_list, to_list, from_image=None):
        """
        Copies sections (in from_list) of data from from_image to the sections
        (in to_list) in latest changed image.

        If from_image is not assigned, use latest changed image as source.

        from_list and to_list can be real list or comma-separated-value.
        """
        # simplify arguments and local variables
        if not from_image:
            from_image = self.get_latest_changed_image()
        to_image = self.get_latest_changed_image()
        from_list = csv_to_list(from_list)
        to_list = csv_to_list(to_list)
        changed_list = []
        changed_image = to_image
        flashrom = self.flashrom
        layout = self.layout

        for f, t in zip(from_list, to_list):
            if self.verify_sections(f, t, from_image, to_image):
                continue
            from_data = flashrom.get_section(from_image, layout, f)
            to_data = flashrom.get_section(to_image, layout, t)
            assert len(from_data) == len(to_data)
            changed_image = flashrom.put_section(changed_image, layout, t,
                                                from_data)
            assert changed_image != to_image
            changed_list.append(t)

        # add to history if anything has been changed.
        if changed_list:
            self.change_history.append((changed_list, changed_image))
            assert changed_image != to_image

    def read_section(self, section, from_image=None):
        """ Returns data of the section in image.

        If from_image is omitted, read from get_latest_changed_image();
        otherwise read directly from from_image.
        """
        if not from_image:
            from_image = self.get_latest_changed_image()
        return self.flashrom.get_section(from_image, self.layout, section)

    def write_section(self, section, data):
        """ Change the section data of latest changed image. """
        new_image = self.get_latest_changed_image()
        new_image = self.flashrom.put_section(new_image, self.layout, section, \
                                              data)
        return self.image_copy(section, section, new_image)

    def get_verification_image(self, from_image, pad_value=chr(0)):
        """
        Returns an image derived from from_image with "skip verification"
        regions padded by pad_value.
        """
        layout = self.layout

        # decode skip_verify with layout, and then modify images
        for verify_tuple in csv_to_list(self.skip_verify):
            (name, offset, size) = verify_tuple.split(':')
            name = name.strip()
            offset = int(offset.strip(), 0)
            size = int(size.strip(), 0)
            assert name in layout, "(make_verify) Unknown section name: " + name
            if self.is_debug:
                print " ** skipping range: %s +%d [%d]" % (name, offset, size)
            # we use the layout's internal structure here...
            offset = layout[name][0] + offset
            from_image = from_image[:offset] + (pad_value * size) + \
                         from_image[(offset + size):]
        return from_image

    def verify_sections(self, from_list, to_list, from_image, to_image):
        """
        Compares if sections in from_list and to_list are the same, skipping
        by self.skip_verify description.

        If from_list and to_list are both empty list ([]), compare whole image
        """
        # simplify arguments and local variables
        from_list = csv_to_list(from_list)
        to_list = csv_to_list(to_list)
        flashrom = self.flashrom
        layout = self.layout

        # prepare verification image
        if self.skip_verify:
            from_image = self.get_verification_image(from_image)
            to_image = self.get_verification_image(to_image)

        # compare sections in image
        if not (from_list or to_list):
            return from_image == to_image
        for (f, t) in zip(from_list, to_list):
            data_f = flashrom.get_section(from_image, layout, f)
            data_t = flashrom.get_section(to_image, layout, t)
            if data_f != data_t:
                return False
        return True

    def verify_whole_image(self, image1, image2):
        """ Compares if image1 and image2 are the same, except the
        skip_verify region.
        """
        return self.verify_sections([], [], image1, image2)

    def _perform_read_flash(self):
        """ (INTERNAL) Performs a real read to flashrom. """
        flashrom = self.flashrom

        if self.target_file:
            return open(self.target_file, 'rb').read()
        else:
            return flashrom.read_whole()

    def _perform_write_flash(self, changed_list, layout, new_image):
        """ (INTERNAL) Performs a real write to flashrom. """
        flashrom = self.flashrom
        self.verbose_msg(" - writing firmware sections: %s" %
                         ','.join(changed_list))

        if self.target_file:
            # TODO(hungte) implementt real partial write here?
            open(self.target_file, 'wb').write(new_image)
        elif not flashrom.write_partial(new_image, layout, changed_list):
            self._error_die("Cannot re-write firmware. Abort.")

        self.verbose_msg(" - verifying firmware data")
        verify_image = self._perform_read_flash()
        self.current_image = verify_image
        if not self.verify_whole_image(verify_image, new_image):
            self._error_die("Tool return success but actual data is incorrect.")

    def commit(self):
        """ Commits all change data into real flashrom """
        # TODO(hungte) if _perform_write_flash failed, we should try to revert
        # system back to initial status.
        # revert_image =self.get_current_image()
        for change_list, change_image in self.change_history:
            self._perform_write_flash(change_list, self.layout, change_image)
        # all committed, clear log history
        self.change_history = []

    def commit_whole_flashrom_image(self, image):
        """ Updates (and commits directly) whole new flashrom image """
        whole_layout = self.whole_flash_layout
        assert len(whole_layout) == 1
        self._perform_write_flash(whole_layout.keys(), whole_layout, image)

    def revert(self):
        """ Revert all changed data which were not committed yet. """
        self.change_history = []


# ---------------------------------------------------------------------------
# The flashrom_util supports both running inside and outside 'autotest'
# framework, so we need to provide some mocks and dynamically load
# autotest components here.


class mock_utils(object):
    """ a mock for autotest_li.client.bin.utils """
    def get_arch(self):
        """ gets system architecture. """
        arch = os.popen('uname -m').read().rstrip()
        arch = re.sub(r"i\d86", r"i386", arch, 1)
        return arch

    def run_command(self, cmd, ignore_status=False):
        """ executes a command and return its output and return code. """
        p = subprocess.Popen(cmd, shell=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (out_msg, err_msg) = p.communicate()
        if p.returncode:
            err_msg = p.stderr.read()
            sys.stderr.write("%s\n%s\n" % (out_msg, err_msg))
            if not ignore_status:
                raise Exception (
                    "failed to execute: %s\nError messages: %s" %
                    (cmd, err_msg))
        return (p.returncode, out_msg)

    def system(self, cmd, ignore_status=False):
        (returncode, _) = self.run_command(cmd, ignore_status)
        return returncode

    def system_output(self, cmd, ignore_status=False):
        (_, output) = self.run_command(cmd, ignore_status)
        return output


# import autotest or mock utilities
try:
    # print 'using autotest'
    from autotest_lib.client.bin import utils
except ImportError:
    # print 'using mocks'
    utils = mock_utils()


# main stub
if __name__ == "__main__":
    # TODO(hungte) provide unit tests or command line usage
    pass
