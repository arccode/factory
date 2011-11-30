# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This module provides convenience routines to access Flash ROM (EEPROM).
 - flashrom_util is a low level wrapper of flashrom(8) program.
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
"""

# TODO(hungte): Use Chromium Python style.  Update external references
# to changed function names, and deprecate/remove unused functions.


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
    '^armv7': {
        "bios": '',
        "ec": '',  # There's no programmable EC on ARM ChromeOS devices.
    }
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

        cmd = '%s %s%s --fast-verify -w "%s"' % (
            self.cmd_current, cmd_layout, cmd_list, tmpfn)

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
# Simple access to a FMAP based firmware images
class FirmwareImage(object):
  """Provides access to firmware image via FMAP sections."""
  def __init__(self, image_source):
    self._image = image_source;
    self._fmap = fmap.fmap_decode(self._image)
    self._areas = dict(
        (entry['name'], [entry['offset'], entry['size']])
        for entry in self._fmap['areas'])

  def has_section(self, section_name):
    """Returns if specified section is available in image."""
    return section_name in self._areas

  def get_section(self, section_name):
    """Returns the content of specified section."""
    if not self.has_section(section_name):
      raise Exception('get_section: invalid section "%s".' % section_name)
    area = self._areas[section_name]
    return self._image[area[0]:(area[0] + area[1])]

  def put_section(self, section_name, value):
    """Updates content of specified section in image."""
    if not self.has_section(section_name):
      raise Exception("Section does not exist: %s" % section_name)
    area = self._areas[section_name]
    if len(value) != area[1]:
      raise ValueError("Value size (%d) does not fit into section (%s, %d)" %
                       (len(value), section_name, area[1]))
    self._image = (self._image[0:area[0]] +
                   value +
                   self._image[(area[0] + area[1]):])
    return True

  def get_fmap_blob(self):
    """Returns the re-encoded fmap blob from firmware image."""
    return fmap.fmap_encode(self._fmap)


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


# ---------------------------------------------------------------------------
# TODO(tammo): Unify these functions with the ones above.


import logging
from tempfile import NamedTemporaryFile
from common import CompactStr, Obj, RunShellCmd


# Global dict of firmware details {bus_name: (chip_id, file handle)}.
_g_firmware_details = {}


def LoadFirmware(bus_name):
  """Return Obj containing chip_id and path to a file containing firmware data.

  Run flashrom twice.  First probe for the chip_id.  Then, if a chip
  is found, dump the contents of flash into a file.

  Args:
    bus_name: Which bus to scan.  For example 'spi' or 'lpc'.
  """
  if bus_name in _g_firmware_details:
    chip_id, fw_file = _g_firmware_details[bus_name]
    return Obj(chip_id=chip_id, path=fw_file.name)
  fw_file = NamedTemporaryFile(prefix='fw_%s_' % bus_name, delete=True)
  cmd_data = RunShellCmd('flashrom -p internal:bus=%s --flash-name' %  bus_name)
  match_list = re.findall('vendor="([^"]*)".*name="([^"]*)"', cmd_data.stdout)
  chip_id = ' ; '.join('%s %s' % (v, n) for v, n in match_list)
  chip_id = chip_id if chip_id else None
  if chip_id is not None:
    if not RunShellCmd('flashrom -p internal:bus=%s -r %s' %
                       (bus_name, fw_file.name)).success:
      raise Error, 'Failed to read %r firmware.' % bus_name
  _g_firmware_details[bus_name] = (chip_id, fw_file)
  return Obj(chip_id=chip_id, path=fw_file.name)


def LoadEcFirmware():
  """Return flashrom data for the internal lpc bus containing the EC."""
  return LoadFirmware('lpc')


def LoadMainFirmware():
  """Return flashrom data for the internal spi bus containing the main fw."""
  return LoadFirmware('spi')
