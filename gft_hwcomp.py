#!/usr/bin/python
#
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import array
import fcntl
import glob
import imp
import os
import pprint
import re
import sys
import threading
import time
import types

import edid
import flashrom_util
import gft_common
import gft_fwhash
import vblock

from gft_common import DebugMsg, VerboseMsg, WarningMsg, ErrorMsg, ErrorDie


class HardwareComponents(object):
  """ Hardware Components Scanner """

  # Function names in this class are used for reflection, so please don't change
  # the function names even if they are not compliant to coding style guide.

  version = 7

  # We divide all component IDs (cids) into 5 categories:
  #  - enumerable: able to get the results by running specific commands;
  #  - probable: returns existed or not by given some pre-defined choices;
  #  - pure data: data for some special purpose, can't be tested;

  _enumerable_cids = [
    'data_display_geometry',
    'hash_key_recovery',
    'hash_key_root',
    'hash_gbb',
    'hash_ro_ec_firmware',
    'hash_ro_main_firmware',
    'part_id_audio_codec',
    'part_id_bluetooth',
    'part_id_camera',
    'part_id_cellular',
    'part_id_chipset',
    'part_id_cpu',
    'part_id_display_converter',
    'part_id_display_panel',
    'part_id_dram',
    'part_id_ec_flash_chip',
    'part_id_embedded_controller',
    'part_id_ethernet',
    'part_id_flash_chip',
    'part_id_hwqual',
    'part_id_keyboard',
    'part_id_storage',
    'part_id_touchpad',
    'part_id_tpm',
    'part_id_usb_hosts',
    'part_id_vga',
    'part_id_wireless',
    'version_cellular_firmware',
    'version_rw_firmware',
    'version_touchpad_firmware',
    # Deprecated fields:
    # 'part_id_gps',
    # - GPS is currently not supported by OS and no way to probe it.
    #   We should enable it only when OS supports it.
    ]
  _probable_cids = [
    'part_id_cardreader',
    ]
  _pure_data_cids = [
    'data_bitmap_fv',
    'data_recovery_url',
    ]

  # list of cids that should not be fetched asynchronously.
  _non_async_cids = [
    # Reading EC will become very slow and cause inaccurate results if we try to
    # probe components that also fires EC command at the same time.
    'part_id_ec_flash_chip',
    ]

  # _not_test_cids and _to_be_tested_cids will be re-created for each match.
  _not_test_cids = []
  _to_be_tested_cids = []

  # TODO(hungte) unify the 'not available' style messages
  _not_present = ''
  _no_match = 'No match'
  _failure_list = [_not_present, _no_match, '']

  # Type id for connection management (compatible to flimflam)
  _type_cellular = 'cellular'
  _type_ethernet = 'ethernet'
  _type_wireless = 'wifi'

  # Type id for touchpad information
  _type_id = 'id'
  _type_firmware = 'firmware'

  _flimflam_dir = '/usr/local/lib/flimflam/test'

  def __init__(self, verbose=False):
    self._initialized = False
    self._verbose = verbose
    self._pp = pprint.PrettyPrinter()

    # cache for firmware images
    self._flashrom = flashrom_util.flashrom_util(
        verbose_msg=VerboseMsg,
        exception_type=gft_common.GFTError,
        system_output=gft_common.SystemOutput,
        system=gft_common.System)
    self._temp_files = []

    # variables for matching
    self._enumerable_system = None
    self._file_base = None
    self._system = None
    self._failures = None

  def __del__(self):
    for temp_file in self._temp_files:
      try:
        # DebugMsg('gft_hwcomp: delete temp file %s' % temp_file)
        os.remove(temp_file)
      except:
        pass

  # --------------------------------------------------------------------
  # System Probing Utilities

  def Memorize(f):
    """ Decorator for thread-safe memorization """
    return gft_common.ThreadSafe(gft_common.Memorize(f))

  def EcProperty(f):
    """ Decorator for properties that requires programmable EC """
    def wrapper(*args, **kargs):
      self = args[0]
      if not self.has_ec():
        return self._not_present
      return f(*args, **kargs)
    return wrapper

  @Memorize
  def load_module(self, name):
    grep_cmd = ('lsmod 2>/dev/null | grep -q %s' % name)
    loaded = (os.system(grep_cmd) == 0)
    if not loaded:
      if os.system('modprobe %s >/dev/null 2>&1' % name) != 0:
        ErrorMsg("Cannot load module: %s" % name)
    return loaded

  @Memorize
  def is_legacy_device_record(self, record):
    """ Returns if a matching record looks like a legacy device. """
    # Current format: [0-9a-f]{4}:[0-9a-f]{4}
    return True if re.match('[0-9a-f]{4}:[0-9a-f]{4}', record) else False

  @Memorize
  def _get_legacy_device_list(self):
    # pci: cat /proc/bus/pci/devices | cut -f 2 # 0.004s < lspci=0.012s
    device_list = []
    pci_device_file = '/proc/bus/pci/devices'
    if os.path.exists(pci_device_file):
      with open(pci_device_file) as handle:
        pci_list = [data.split('\t', 2)[1]
                    for data in handle.readlines()]
        device_list += ['%s:%s' % (entry[:4], entry[4:])
                        for entry in pci_list]
    else:
      DebugMsg('Failed to read %s. Execute lspci.' % pci_device_file)
      pci_list = [entry.split()[2:4]
                  for entry in
                  gft_common.SystemOutput('lspci -n -mm').splitlines()]
      device_list += ['%s:%s' % (vendor.strip('"'), product.strip('"'))
                      for (vendor, product) in pci_list]
    # usb: realpath(/sys/bus/usb/devices/*:*)/../id* # 0.05s < lspci=0.078s
    usb_devs = glob.glob('/sys/bus/usb/devices/*:*')
    for dev in usb_devs:
      path = os.path.join(os.path.realpath(dev), '..')
      device_list += ['%s:%s' %
                      (gft_common.ReadOneLine(os.path.join(path, 'idVendor')),
                       gft_common.ReadOneLine(os.path.join(path, 'idProduct')))]
    DebugMsg('Legacy device list: ' + ', '.join(device_list))
    return device_list

  @Memorize
  def import_flimflam_module(self):
    """ Tries to load flimflam module from current system """
    if not os.path.exists(self._flimflam_dir):
      DebugMsg('no flimflam installed in %s' % self._flimflam_dir)
      return None
    try:
      return imp.load_module('flimflam',
                             *imp.find_module('flimflam', [self._flimflam_dir]))
    except ImportError:
      ErrorMsg('Failed to import flimflam.')
    except:
      ErrorMsg('Failed to load flimflam.')
    return None

  @Memorize
  def load_flimflam(self):
    """Gets information provided by flimflam (connection manager)

    Returns
    (None, None) if failed to load module, otherwise
    (connection_path, connection_info) where
     connection_path is a dict in {type: device_path},
     connection_info is a dict of {type: {attribute: value}}.
    """
    flimflam = self.import_flimflam_module()
    if not flimflam:
      return (None, None)
    path = {}
    info = {}
    info_attribute_names = {
        self._type_cellular: ['Carrier', 'FirmwareRevision', 'HardwareRevision',
                              'ModelID', 'Manufacturer'],
    }
    devices = flimflam.FlimFlam().GetObjectList('Device')
    unpack = flimflam.convert_dbus_value
    # TODO(hungte) support multiple devices existence in future
    for device in devices:
      # populate the 'path' collection
      prop = device.GetProperties()
      prop_type = unpack(prop['Type'])
      prop_path = unpack(prop['Interface'])
      if prop_type in path:
        WarningMsg('Multiple network devices with same type (%s) were found.'
                   'Target path changed from %s to %s.' %
                   (prop_type, path[prop_type], prop_path))
      path[prop_type] = '/sys/class/net/%s/device' % prop_path
      if prop_type not in info_attribute_names:
        continue
      # populate the 'info' collection
      info[prop_type] = dict((
          (key, unpack(prop['Cellular.%s' % key]))
          for key in info_attribute_names[prop_type]
          if ('Cellular.%s' % key) in prop))
    return (path, info)

  @Memorize
  def _get_all_connection_info(self):
    """ Probes available connectivity and device information """
    connection_info = {
        self._type_wireless: '/sys/class/net/wlan0/device',
        self._type_ethernet: '/sys/class/net/eth0/device',
        # cellular may also be /sys/class/net/usb0
        self._type_cellular: '/sys/class/tty/ttyUSB0/device',
    }
    (path, _) = self.load_flimflam()
    if path is not None:
      # trust flimflam instead.
      for k in connection_info:
        connection_info[k] = (path[k] if k in path else '')
    return connection_info

  @Memorize
  def i2cdump(self, bus, address, size):
    """ Reads binary dump from i2c bus. """
    # TODO(hungte) Use /usr/sbin/i2cdump if possible
    self.load_module('i2c_dev')
    if type(bus) is types.IntType:
      bus = '/dev/i2c-%d' % bus
    fd = -1
    I2C_SLAVE = 0x0703
    blob = None
    try:
      fd = os.open(bus, os.O_RDWR)
      if fcntl.ioctl(fd, I2C_SLAVE, address) != 0:
        return blob
      time.sleep(0.05)  # Wait i2c to get ready
      if os.write(fd, chr(0)) == 1:
        blob = os.read(fd, size)
    except:
      pass
    finally:
      if fd >= 0:
        os.close(fd)
    return blob

  @Memorize
  def load_lvds_edid(self):
    """ Probes LVDS data by using EDID method. """
    lvds_files = glob.glob('/sys/class/drm/*LVDS*/edid')
    if lvds_files:
      try:
        return edid.parse_edid_file(lvds_files[0])
      except ValueError, e:
        ErrorMsg('EDID Parsing Error: %s' % e)

    # Try i2c
    self.load_module('i2c_dev')
    i2c_files = glob.glob('/dev/i2c-?')
    i2c_files.sort()
    # LVDS are usually on address 0x50.
    I2C_LVDS_ADDERSS = 0x50
    for i2c_file in i2c_files:
      edid_blob = self.i2cdump(i2c_file, I2C_LVDS_ADDERSS,
                               edid.EDID_MINIMAL_SIZE)
      if edid_blob:
        try:
          return edid.parse_edid(edid_blob)
        except ValueError, e:
          WarningMsg('EDID Parsing Error: %s' % e)

    # TODO(hungte) we can also try xrandr
    return None

  def _get_sysfs_device_info(self, path, primary, optional=[]):
    """Gets the device information of a sysfs node.

    Args
      path: the sysfs device path.
      primary: mandatory list of elements to read.
      optional: optional list of elements to read.

    Returns
      [primary_values_dict, optional_values_dict]
    """

    primary_values = {}
    optional_values = {}
    for element in primary:
      element_path = os.path.join(path, element)
      if not os.path.exists(element_path):
        return [None, None]
      primary_values[element] = gft_common.ReadOneLine(element_path)
    for element in optional:
      element_path = os.path.join(path, element)
      if os.path.exists(element_path):
        optional_values[element] = gft_common.ReadOneLine(element_path)
    return [primary_values, optional_values]

  def _get_pci_device_info(self, path):
    """ Returns a PCI 'vendor:device' component information. """
    # TODO(hungte) PCI has a 'rev' info which may be better added into info.
    (info, _) = self._get_sysfs_device_info(path, ['vendor', 'device'])
    return '%s:%s' % (info['vendor'].replace('0x', ''),
                      info['device'].replace('0x', '')) if info else None

  def _get_usb_device_info(self, path):
    """ Returns an USB 'idVendor:idProduct manufacturer product' info. """

    # USB in sysfs is hierarchy, and usually uses the 'interface' layer.
    # If we are in 'interface' layer, the product info is in real parent folder.
    path = os.path.realpath(path)
    while path.find('/usb') > 0:
      if os.path.exists(os.path.join(path, 'idProduct')):
        break
      path = os.path.split(path)[0]
    optional_fields = ['manufacturer', 'product', 'bcdDevice']
    (info, optional) = self._get_sysfs_device_info(
        path, ['idVendor', 'idProduct'], optional_fields)
    if not info:
      return None
    info_string = '%s:%s' % (info['idVendor'].replace('0x', ''),
                             info['idProduct'].replace('0x', ''))
    for field in optional_fields:
      if field in optional:
        info_string += ' ' + optional[field]
    return info_string

  def get_sysfs_device_id(self, path):
    """Gets a sysfs device identifier. (Currently supporting USB/PCI)
    Args
      path: a path to sysfs device (ex, /sys/class/net/wlan0/device)

    Returns
      An identifier string, or self._not_present if not available.
    """
    if not path:
      return self._not_present
    path = os.path.realpath(path)
    if not os.path.isdir(path):
      return self._not_present

    info = (self._get_pci_device_info(path) or
            self._get_usb_device_info(path))
    return info or self._not_present

  def get_sysfs_node_id(self, path):
    """Gets a sysfs node identifier (for devices that may exist on SOC or bus)
    Args
      path: a path to sysfs node (ex, /sys/class/video4linux/video0) which
            contains a 'device' or 'name' property.

    Returns
      An identifier string, or self._not_present if not available.
    """
    if not path:
      return self._not_present
    device_id = self.get_sysfs_device_id(os.path.join(path, 'device'))
    if device_id:
      return device_id
    name_path = os.path.join(path, 'name')
    if os.path.exists(name_path):
      return gft_common.ReadOneLine(name_path)
    return self._not_present

  def compact_id(self, id_info):
    """Returns a identifier with white space characters compressed
    Args
      id_info: a string or list/tuple of identifiers

    Returns
      A string with all identifiers described by id_info with minimal space
    """
    if type(id_info) == list or type(id_info) == tuple:
      id_info = ' '.join(id_info)
    return re.sub('\s+', ' ', id_info).strip()

  @Memorize
  def get_arch(self):
    """ Gets current system architecture. """
    return gft_common.GetSystemArch()

  @Memorize
  def get_ssd_name(self, partition_number=None):
    """Gets a proper SSD device name by platform (arch) detection.
    Args
      partition_number: numeric index for partition. None for whole disk.

    Returns
      A device name for SSD, base on self.get_arch() result.
    """
    arch = self.get_arch()
    partno = '' if partition_number is None else ('%d' % partition_number)
    if arch in ('x86', 'amd64'):
      return 'sda' + partno
    elif arch in ('arm'):
      if partno:
        partno = 'p' + partno
      return 'mmcblk0' + partno
    else:
      assert False, ('get_ssd_name: unknown arch: %s' % arch)
      return 'sda' + partno

  @Memorize
  def has_ec(self):
    """ Returns if current system has programmable EC chips. """
    arch = self.get_arch()
    if arch in ('x86', 'amd64'):
      return True
    elif arch in ('arm'):
      return False
    else:
      assert False, 'unknown platform for EC information.'
    return False

  # --------------------------------------------------------------------
  # Firmware Processing Utilities

  @Memorize
  def _load_firmware(self, target_name):
    filename = gft_common.GetTemporaryFileName('fw_cache')
    self._temp_files.append(filename)

    option_map = {
        'main': '-p internal:bus=spi',
        'ec': '-p internal:bus=lpc',
    }
    assert target_name in option_map

    # example output:
    #  Found chip "Winbond W25x16" (2048 KB, FWH) at physical address 0xfe
    # TODO(hungte) maybe we don't need the -V in future -- if that can make
    # the command faster.
    command = 'flashrom -V %s -r %s' % (option_map[target_name], filename)
    parts = []
    lines = gft_common.SystemOutput(
        command,
        progress_message='Reading %s firmware: ' % target_name,
        show_progress=self._verbose).splitlines()
    for line in lines:
      match = re.search(r'Found chip "(.*)" .* at physical address ', line)
      if match:
        parts.append(match.group(1))
    part_id = ', '.join(parts)
    # restore flashrom target bus
    if target_name != 'main':
      os.system('flashrom %s >/dev/null 2>&1' % option_map['main'])
    return (part_id, filename)

  def load_main_firmware(self):
    """ Loads and cache main (BIOS) firmware image.

    Returns
        A file name of cached image.
    """
    (_, image_file) = self._load_firmware('main')
    return image_file

  @EcProperty
  def load_ec_firmware(self):
    """ Loads and cache EC firmware image.

    Returns
        A file name of cached image.
    """
    (_, image_file) = self._load_firmware('ec')
    return image_file

  @Memorize
  def _read_gbb_component(self, name):
    image_file = self.load_main_firmware()
    if not image_file:
      ErrorDie('cannot load main firmware')
    filename = gft_common.GetTemporaryFileName('gbb%s' % name)
    if os.system('gbb_utility -g --%s=%s %s >/dev/null 2>&1' %
                 (name, filename, image_file)) != 0:
      ErrorDie('cannot get %s from GBB' % name)
    value = gft_common.ReadBinaryFile(filename)
    os.remove(filename)
    return value

  # --------------------------------------------------------------------
  # Product-Specific Probing

  @Memorize
  def probe_touchpad(self):
    """ Probes touchpad information.

    Returns:
      A dict of { _type_id: 'TOUCHPAD_HWINFO',
                  _type_firmware: 'TOUCHPAD_FWINFO' }
    """

    def synaptics():
      detect_program = '/opt/Synaptics/bin/syndetect'
      model_string_str = 'Model String'
      firmware_id_str = 'Firmware ID'

      if not os.path.exists(detect_program):
        return None
      command_list = [detect_program]
      # Determine if X is capturing touchpad
      locked = os.system('lsof /dev/serio_raw0 2>/dev/null | grep -q "^X"')

      if (locked == 0) and (not os.getenv('DISPLAY')):
        ErrorMsg('Warning: You are trying to detect touchpad with X in '
                 'foreground but not configuring DISPLAY properly.\n'
                 'Test may fail with incorrect detection results.')
        # Make a trial with default configuration (see cros/cros_ui.py and
        # suite_Factory/startx.sh)
        command_list.insert(0, 'DISPLAY=":0"')
        xauthority_locations = ('/var/run/factory_ui.auth',
                                '/home/chronos/.Xauthority')
        valid_xauth = [xauth for xauth in xauthority_locations
                       if os.path.exists(xauth)]
        if valid_xauth:
          command_list.insert(0, 'XAUTHORITY="%s"' % valid_xauth[0])

      (exit_code, data, _) = gft_common.ShellExecution(
          ' '.join(command_list),
          ignore_status=True,
          progress_message='Synaptics Touchpad: ',
          show_progress=self._verbose)
      if exit_code != 0:
        return None
      properties = dict(map(str.strip, line.split('=', 1))
                        for line in data.splitlines() if '=' in line)
      model = properties.get(model_string_str, 'Unknown Synaptics')
      # The pattern " on xxx Port" may vary by the detection approach,
      # so we need to strip it.
      model = re.sub(' on [^ ]* [Pp]ort$', '', model)
      firmware_id = properties.get(firmware_id_str, self._not_present)
      return (model, firmware_id)

    def cypress():
      nodes = glob.glob('/sys/class/input/mouse[0-9]*/device/device')
      for node in nodes:
        id_files = ['product_id', 'hardware_version', 'protocol_version']
        if not all([os.path.exists(os.path.join(node, field))
                    for field in id_files]):
          continue
        firmware_files = ['firmware_version']
        model = self.compact_id(
            [gft_common.ReadOneLine(os.path.join(node, field))
             for field in id_files])
        firmware_id = self.compact_id(
            [gft_common.ReadOneLine(os.path.join(node, field))
             for field in firmware_files
             if os.path.exists(os.path.join(node, field))])
        return (model, firmware_id)
      return None

    def generic():
      # TODO(hungte) add more information from id/*
      # format: N: Name="XXX_trackpad"
      input_file = '/proc/bus/input/devices'
      cmd_grep = 'grep -iE "^N.*(touch *pad|track *pad)" %s' % input_file
      info = gft_common.SystemOutput(cmd_grep, ignore_status=True).splitlines()
      info = [re.sub('^[^"]*"(.*)"$', r'\1', device)
              for device in info]
      return (', '.join(info) or self._not_present, self._not_present)

    method_list = [cypress, synaptics, generic]
    data = { self._type_id: self._not_present,
             self._type_firmware: self._not_present }
    for method in method_list:
      result = method()
      DebugMsg('probe_touchpad: %s: %s' % (method,result or '<failed>'))
      if result:
        data[self._type_id] = result[0]
        data[self._type_firmware] = result[1]
        return data
    return data

  # --------------------------------------------------------------------
  # Enumerable Properties

  def get_data_display_geometry(self):
    # Get edid from driver.
    # TODO(nsanders): this is driver specific.
    # Try EDID
    lvds_edid = self.load_lvds_edid()
    if lvds_edid:
      return '%dx%d' % (lvds_edid[edid.EDID_WIDTH],
                        lvds_edid[edid.EDID_HEIGHT])

    # Try frame buffer
    fb_modes_file = '/sys/class/graphics/fb0/modes'
    if os.path.exists(fb_modes_file):
      # format: U:1366x768p-0
      fb_mode = gft_common.ReadOneLine(fb_modes_file)
      geometry = re.search(r'\d+x\d+', fb_mode)
      if geometry:
        return geometry.group(0)

    return self._not_present

  def get_hash_gbb(self):
    image_file = self.load_main_firmware()
    return gft_fwhash.GetMainFirmwareGbbHash(file_source=image_file)

  def get_hash_key_recovery(self):
    current_key = self._read_gbb_component('recoverykey')
    return gft_fwhash.GetKeyHash(current_key)

  def get_hash_key_root(self):
    current_key = self._read_gbb_component('rootkey')
    return gft_fwhash.GetKeyHash(current_key)

  @EcProperty
  def get_hash_ro_ec_firmware(self):
    """
    Returns a hash of Embedded Controller firmware read only parts,
    to confirm we have proper updated version of EC firmware.
    """

    image_file = self.load_ec_firmware()
    if not image_file:
      ErrorDie('get_hash_ro_ec_firmware: cannot read firmware')
    return gft_fwhash.GetEcFirmwareReadOnlyHash(file_source=image_file)

  def get_hash_ro_main_firmware(self):
    """
    Returns a hash of main firmware (BIOS) read only parts,
    to confirm we have proper keys / boot code / recovery image installed.
    """

    image_file = self.load_main_firmware()
    if not image_file:
      ErrorDie('get_hash_ro_main_firmware: cannot read firmware')
    return gft_fwhash.GetMainFirmwareReadOnlyHash(file_source=image_file)

  def get_part_id_cellular(self):
    device_path = self._get_all_connection_info()[self._type_cellular]
    return self.get_sysfs_device_id(device_path) or self._not_present

  def get_part_id_audio_codec(self):
    cmd = 'grep -R Codec: /proc/asound/* | head -n 1 | sed s/.\*Codec://'
    part_id = gft_common.SystemOutput(
        cmd, progress_message='Searching Audio Codecs: ',
        show_progress=self._verbose).strip()
    # If no codec installed, try PCM.
    if not part_id:
      # format: 00-00: WMXXXX PCM wmxxxx-hifi-0: ...
      pcm_data = gft_common.ReadOneLine('/proc/asound/pcm').split(' ')
      if len(pcm_data) > 2:
        part_id = pcm_data[1]
    return part_id

  def get_part_id_bluetooth(self):
    return self.get_sysfs_device_id('/sys/class/bluetooth/hci0/device')

  def get_part_id_camera(self):
    info = []
    camera_node = '/sys/class/video4linux/video0'
    info.append(self.get_sysfs_node_id(camera_node))
    # For soc-camera, "control/name" is a helpful driver name.
    control_name = os.path.join(camera_node, 'device/control/name')
    if os.path.exists(control_name):
      info.append(gft_common.ReadOneLine(control_name))
    # Try video4linux2 (v4l2) interface
    camera_dev = '/dev/video0'
    if os.path.exists(camera_dev):
      fd = -1
      try:
        fd = os.open(camera_dev, os.O_RDWR)
        # See /usr/include/linux/videodev2.h for definition
        VIDIOC_DBG_G_CHIP_IDENT = 0xc02c5651
        V4L2_DBG_CHIP_IDENT_SIZE = 11
        V4L2_INDEX_REVISION = V4L2_DBG_CHIP_IDENT_SIZE - 1
        V4L2_INDEX_IDENT = V4L2_INDEX_REVISION - 1
        V4L2_VALID_IDENT = 3  # V4L2_IDENT_UNKNOWN + 1
        v4l2_dbg_chip_ident = array.array('i', [0] * V4L2_DBG_CHIP_IDENT_SIZE)
        fcntl.ioctl(fd, VIDIOC_DBG_G_CHIP_IDENT, v4l2_dbg_chip_ident, 1)
        # 'ident' values are defined in include/media/v4l2-chip-ident.h
        v4l2_ident = v4l2_dbg_chip_ident[V4L2_INDEX_IDENT]
        if v4l2_ident >= V4L2_VALID_IDENT:
          info.append('V4L2:%04x %04x' %
                      (v4l2_ident, v4l2_dbg_chip_ident[V4L2_INDEX_REVISION]))
      except:
        pass
      finally:
        if fd >= 0:
          os.close(fd)
    return self.compact_id(info)

  def get_part_id_display_converter(self):
    """ Gets display converter by dedicated probing """
    def probe_ch7036():
      self.load_module('i2c_dev')
      probe_cmd = 'ch7036_monitor -p >/dev/null 2>&1'
      return 'ch7036' if os.system(probe_cmd) == 0 else ''

    method_list = [probe_ch7036]
    part_id = self._not_present
    for method in method_list:
      part_id = method()
      DebugMsg('get_part_id_display_converter: %s: %s' %
               (method.__name__, part_id or '<failed>'))
      if part_id:
        break
    return part_id

  def get_part_id_chipset(self):
    # On x86, host bridge is always the first PCI device.
    # For SOC-based system, trust the first compatible list in device-tree
    # (fdt).
    part_id = self.get_sysfs_device_id('/sys/bus/pci/devices/0000:00:00.0')
    fdt_compatible_file = '/proc/device-tree/compatible'
    if (not part_id) and os.path.exists(fdt_compatible_file):
      compatible_list = gft_common.ReadOneLine(fdt_compatible_file)
      # format: manufacturer,model [NUL] compat-manufacturer,model [NUL] ...
      info = compatible_list.strip(chr(0)).split(chr(0))
      part_id = self.compact_id(info)
    return part_id

  def get_part_id_cpu(self):
    part_id = 'Unknown'
    cpu_info_map = {
        # arch: (command, core_delta)
        # The core_delta computation is caused by different report format.
        # For platforms like x86, it provides names for each core.
        #  Sample output for dual-core:
        #   model name : Intel(R) Atom(TM) CPU XXXX
        #   model name : Intel(R) Atom(TM) CPU XXXX
        'amd64': (r'sed -nr "s/^model name\t*: (.*)/\1/p" /proc/cpuinfo', 0),
        'x86': (r'sed -nr "s/^model name\s*: (.*)/\1/p" /proc/cpuinfo', 0),
        # For platforms like arm, it gives the name only in 'Processor'
        #  and then a numeric ID for each cores 'processor', so delta is 1.
        #  Sample output for dual-core:
        #   Processor : ARMXXXX
        #   processor : 0
        #   processor : 1
        'arm': (r'sed -nr "s/^[Pp]rocessor\s*: (.*)/\1/p" /proc/cpuinfo', 1),
    }
    arch = self.get_arch()
    if arch not in cpu_info_map:
      return part_id
    info = gft_common.SystemOutput(cpu_info_map[arch][0]).splitlines()
    if not info:
      return part_id
    cores = len(info) - cpu_info_map[arch][1]
    info = info[0:1]
    # TODO(hungte) For backward compatbility, core number reporting on x86 is
    # disabled. We need to fix HWID component lists in future.
    if cores > 1 and arch != 'x86':
      info.append('*%d' % cores)
    return self.compact_id(info)

  def get_part_id_display_panel(self):
    # Try EDID
    lvds_edid = self.load_lvds_edid()
    if lvds_edid:
      return '%s:%04x' % (lvds_edid[edid.EDID_MANUFACTURER_ID],
                          lvds_edid[edid.EDID_PRODUCT_ID])
    # Try frame buffer
    fb_filename = '/sys/class/graphics/fb0/name'
    if os.path.exists(fb_filename):
      return gft_common.ReadOneLine(fb_filename)

    return self._not_present

  def get_part_id_dram(self):
    arch = self.get_arch()
    if arch in ('x86', 'amd64'):
      # TODO(hungte) if we only want DRAM size, maybe no need to use mosys
      self.load_module('i2c_dev')
      cmd = ('mosys -l memory spd print geometry | '
             'grep size_mb | cut -f2 -d"|"')
      part_id = gft_common.SystemOutput(cmd).strip()
    elif arch in ('arm'):
      # Even kernel cannot probe the memory. We can only trust the memory
      # information passed to kernel.
      param = gft_common.ReadOneLine('/proc/cmdline')
      # Format: *mem=384M@0M (type=size@address)
      part_id = '%d' % sum(
          [int(size) for size in re.findall(r'\s\w*mem=(\d+)M@\d+M', param)])
    return part_id if part_id else self._not_present

  @EcProperty
  def get_part_id_ec_flash_chip(self):
    (chip_id, _) = self._load_firmware('ec')
    return chip_id

  @EcProperty
  def get_part_id_embedded_controller(self):
    # example output:
    #  Found Nuvoton WPCE775x (id=0x05, rev=0x02) at 0x2e

    parts = []
    res = gft_common.SystemOutput(
        'superiotool',
        progress_message='Probing Embedded Controller: ',
        show_progress=self._verbose,
        ignore_status=True).splitlines()
    for line in res:
      match = re.search(r'Found (.*) at', line)
      if match:
        parts.append(match.group(1))
    part_id = ', '.join(parts)
    return part_id

  def get_part_id_ethernet(self):
    device_path = self._get_all_connection_info()[self._type_ethernet]
    return self.get_sysfs_device_id(device_path) or self._not_present

  def get_part_id_flash_chip(self):
    (chip_id, _) = self._load_firmware('main')
    return chip_id

  def get_part_id_hwqual(self):
    part_id = gft_common.SystemOutput('crossystem hwid').strip()
    # TODO(hungte) compare this with HWID in GBB.
    return (part_id if part_id else self._not_present)

  def get_part_id_storage(self):
    part_id = self._not_present
    node = '/sys/class/block/%s' % self.get_ssd_name()
    path = os.path.join(node, 'device')
    if not os.path.exists(path):
      return part_id
    size = ''
    size_path = os.path.join(node, 'size')
    if os.path.exists(size_path):
      size = '#' + gft_common.ReadOneLine(size_path)
    info_list = (
        ['vendor', 'model'],  # ATA
        ['type', 'name', 'fwrev', 'hwrev', 'oemid', 'manfid'],  # EMMC
    )
    for info in info_list:
      data = [gft_common.ReadOneLine(os.path.join(path, data_file))
              for data_file in info
              if os.path.exists(os.path.join(path, data_file))]
      if data:
        return self.compact_id(data + [size])
    return part_id

  def get_part_id_keyboard(self):
    # VPD value "keyboard_layout"="xkb:gb:extd:eng" should be listed.
    image_file = self.load_main_firmware()
    part_id = gft_common.SystemOutput(
        'vpd -i RO_VPD -l -f "%s" | grep keyboard_layout | cut -f4 -d\\"' %
        image_file).strip()
    return part_id or self._not_present

  def get_part_id_touchpad(self):
    data = self.probe_touchpad()
    return data[self._type_id]

  def get_part_id_tpm(self):
    """ Returns Manufacturer_info : Chip_Version """
    cmd = 'tpm_version'
    part_id = self._not_present
    tpm_output = gft_common.SystemOutput(cmd)
    tpm_lines = tpm_output.splitlines()
    tpm_dict = {}
    for tpm_line in tpm_lines:
      [key, colon, value] = tpm_line.partition(':')
      tpm_dict[key.strip()] = value.strip()
    (key1, key2) = ('Manufacturer Info', 'Chip Version')
    if key1 in tpm_dict and key2 in tpm_dict:
      part_id = tpm_dict[key1] + ':' + tpm_dict[key2]
    return part_id

  def get_part_id_usb_hosts(self):
    arch = self.get_arch()
    if arch in ('x86', 'amd64'):
      # on x86, USB hosts are PCI devices, located in parent of root USB.
      relpath = '..'
    else:
      # on ARM and others, use the root device itself.
      relpath = '.'

    usb_bus_list = glob.glob('/sys/bus/usb/devices/usb*')
    usb_host_list = [os.path.join(os.path.realpath(path), relpath)
                     for path in usb_bus_list]
    # usually there are several USB hosts, so only list the primary information.
    usb_host_info = [re.sub(' .*', '', self.get_sysfs_device_id(device))
                     for device in usb_host_list]
    usb_host_info.sort(reverse=True)
    return ' '.join(usb_host_info)

  def get_part_id_vga(self):
    return self.get_sysfs_node_id('/sys/class/graphics/fb0')

  def get_part_id_wireless(self):
    device_path = self._get_all_connection_info()[self._type_wireless]
    return self.get_sysfs_device_id(device_path) or self._not_present

  def get_version_cellular_firmware(self):
    (_, attributes) = self.load_flimflam()
    if attributes and (self._type_cellular in attributes):
      # A list of possible version info combination, since the supported fields
      # may differ for partners.
      version_formats = [
          ['Carrier', 'FirmwareRevision'],
          ['FirmwareRevision'],
          ['HardwareRevision']]
      info = attributes[self._type_cellular]
      for version_format in version_formats:
        if not set(version_format).issubset(set(info)):
          continue
        # compact all fields into single line with limited space
        return self.compact_id([info[key] for key in version_format])
      # If nothing available, try 'modem status'.
      modem_status = gft_common.SystemOutput(
          'modem status | grep firmware_revision', ignore_status=True).strip()
      info = re.findall('^\s*firmware_revision:\s*(.*)', modem_status)
      if info and info[0]:
        return info[0]
    return self._not_present

  def get_version_rw_firmware(self):
    """
    Returns the version of Read-Write (writable) firmware from VBLOCK sections.

    If A/B has different version, that means this system needs a reboot +
    firmwar update so return value is a "error report" in the form "A=x, B=y".
    """

    # TODO(hungte) Support new VBLOCK, or use vbutil_firmware
    versions = [None, None]
    section_names = ['VBLOCK_A', 'VBLOCK_B']
    image_file = self.load_main_firmware()
    if not image_file:
      ErrorDie('Cannot read system main firmware.')
    flashrom = self._flashrom
    base_img = open(image_file).read()
    flashrom_size = len(base_img)

    # we can trust base image for layout, since it's only RW.
    layout = flashrom.detect_chromeos_bios_layout(flashrom_size, base_img)
    if not layout:
      ErrorDie('Cannot detect ChromeOS flashrom layout')
    for (index, name) in enumerate(section_names):
      data = flashrom.get_section(base_img, layout, name)
      block = vblock.unpack_verification_block(data)
      ver = block['VbFirmwarePreambleHeader']['firmware_version']
      versions[index] = ver
    # we embed error reports in return value.
    assert len(versions) == 2
    if versions[0] != versions[1]:
      return 'A=%d, B=%d' % (versions[0], versions[1])
    return '%d' % versions[0]

  def get_version_touchpad_firmware(self):
    data = self.probe_touchpad()
    return data[self._type_firmware]

  # --------------------------------------------------------------------
  # Probable Properties

  def probe_part_id_cardreader(self, part_id):
    # A cardreader is always power off until a card inserted. So checking
    # it using log messages instead of lsusb can limit operator-attended.
    # But note that it does not guarantee the cardreader presented during
    # the time of the test.

    # TODO(hungte) Grep entire /var/log/message may be slow. Currently we cache
    # this result by verify_probable_component, but we should find some better
    # and reliable way to detect this.
    [vendor_id, product_id] = part_id.split(':')
    found_pattern = ('New USB device found, idVendor=%s, idProduct=%s' %
                     (vendor_id, product_id))
    cmd = 'grep -qs "%s" /var/log/messages*' % found_pattern
    return os.system(cmd) == 0

  # --------------------------------------------------------------------
  # Matching

  def force_get_property(self, property_name):
    """ Returns property value or empty string on error. """

    try:
      return getattr(self, property_name)()
    except gft_common.GFTError, e:
      ErrorMsg("Error in probing property %s: %s" % (property_name, e.value))
      return ''
    except:
      ErrorMsg('Exception in getting property %s' % property_name)
      return ''

  def update_ignored_cids(self, ignored_cids):
    for cid in ignored_cids:
      if cid in self._to_be_tested_cids:
        self._to_be_tested_cids.remove(cid)
        DebugMsg('Ignoring cid: %s' % cid)
      else:
        ErrorDie('The ignored cid %s is not defined' % cid)
      self._not_test_cids.append(cid)

  def read_approved_from_file(self, filename):
    approved = gft_common.LoadComponentsDatabaseFile(filename)
    for cid in self._to_be_tested_cids + self._not_test_cids:
      if cid not in approved:
        # If we don't have any listing for this type
        # of part in HWID, it's not required.
        WarningMsg('gft_hwcomp: Bypassing unlisted cid %s' % cid)
        approved[cid] = '*'
    return approved

  def get_all_enumerable_components(self, async):
    results = {}
    thread_pools = []

    def fetch_enumerable_component(cid):
      """ Fetch an enumerable component and update the results """
      if self._verbose:
        sys.stdout.flush()
        sys.stderr.write('<Fetching property %s>\n' % cid)
      components = self.force_get_property('get_' + cid)
      if not isinstance(components, list):
        components = [components]
      results[cid] = components

    class FetchThread(threading.Thread):
      """ Thread object for parallel enumerating """
      def __init__(self, cid):
        threading.Thread.__init__(self)
        self.cid = cid

      def run(self):
        fetch_enumerable_component(self.cid)

    for cid in self._enumerable_cids:
      if async and cid not in self._non_async_cids:
        thread_pools.append(FetchThread(cid))
      else:
        fetch_enumerable_component(cid)

    # Complete the threads
    for thread in thread_pools:
      thread.start()
    for thread in thread_pools:
      thread.join()
    return results

  def format_failure(self, exact_values, approved_values):
    message_not_present = 'Not Present'
    actual = [(message_not_present
               if value in self._failure_list else value)
              for value in exact_values]
    expected = [(message_not_present
                 if value in self._failure_list else value)
                for value in approved_values]
    return ['Actual: %s' % ', '.join(set(actual)),
            'Expected: %s' % ' | '.join(set(expected))]

  def check_enumerable_component(self, cid, exact_values, approved_values):
    if '*' in approved_values:
      return

    unmatched = [value for value in exact_values
                 if value not in approved_values]
    if not unmatched:
      return

    # there's some error, let's try to match them in legacy list
    match_goal = [value for value in approved_values
                  if value not in self._failure_list]
    legacy_approved = filter(self.is_legacy_device_record, match_goal)
    if match_goal and (set(legacy_approved) == set(match_goal)):
      DebugMsg('Start legacy search for cid: ' + cid)
      # TODO(hungte) prefetch this list in async batch process.
      legacy_list = self._get_legacy_device_list()
      matched = list(set(legacy_list).intersection(set(match_goal)))
      if matched:
        DebugMsg('Changed detected list: %s->%s' % (self._system[cid], matched))
        self._system[cid] = matched
        return
    # update with remaining error.
    self._failures[cid] = self.format_failure(exact_values, approved_values)

  @Memorize
  def verify_probable_component(self, cid, approved_values):
    if '*' in approved_values:
      return (True, ['*'])

    for value in approved_values:
      present = getattr(self, 'probe_' + cid)(value)
      if present:
        return (True, [value])
    return (False, [self._no_match])

  def check_probable_component(self, cid, approved_values):
    (probed, value) = self.verify_probable_component(cid, approved_values)
    if probed:
      self._system[cid] = value
    else:
      self._failures[cid] = self.format_failure(value, approved_values)

  def pformat(self, obj):
    return '\n' + self._pp.pformat(obj) + '\n'

  def initialize(self, force=False, async=False):
    if self._initialized and not force:
      return
    # probe current system components
    DebugMsg('Starting to detect system components...')
    self._enumerable_system = self.get_all_enumerable_components(async)
    self._initialized = True

  def match_current_system(self, filename, ignored_cids=[]):
    """ Matches a given component list to current system.
        Returns: (current, failures)
    """

    # assert self._initialized, 'Not initialized.'
    self._to_be_tested_cids = (self._enumerable_cids +
                               self._probable_cids)
    self._not_test_cids = self._pure_data_cids[:]

    self.update_ignored_cids(ignored_cids)
    self._failures = {}
    self._system = {}
    self._system.update(self._enumerable_system)
    self._file_base = gft_common.GetComponentsDatabaseBase(filename)

    approved = self.read_approved_from_file(filename)
    for cid in self._enumerable_cids:
      if cid not in self._to_be_tested_cids:
        VerboseMsg('gft_hwcomp: match: ignored: %s' % cid)
      else:
        self.check_enumerable_component(
            cid, self._enumerable_system[cid], approved[cid])
    for cid in self._probable_cids:
      if cid not in self._to_be_tested_cids:
        VerboseMsg('gft_hwcomp: match: ignored: %s' % cid)
      else:
        self.check_probable_component(cid, approved[cid])

    return (self._system, self._failures)


#############################################################################
# Console main entry
@gft_common.GFTConsole
def _main(self_path, args):
  do_async = True

  # preprocess args
  compdb_list = []
  for arg in args:
    if arg == '--sync':
      do_async = False
    elif arg == '--async':
      do_async = True
    elif not os.path.exists(arg):
      print 'ERROR: unknown parameter: ' + arg
      print 'Usage: %s [--sync|--async] [components_db_files...]\n' % self_path
      sys.exit(1)
    else:
      compdb_list.append(arg)

  components = HardwareComponents(verbose=True)
  print 'Starting to detect%s...' % (' asynchrounously' if do_async else '')
  components.initialize(async=do_async)

  if not compdb_list:
    print 'Enumerable properties:'
    print components.pformat(components._enumerable_system)
    sys.exit(0)

  print 'Starting to match system...'
  for arg in compdb_list:
    (matched, failures) = components.match_current_system(arg)
    print 'Probed (%s):' % arg
    print components.pformat(matched)
    print 'Failures (%s):' % arg
    print components.pformat(failures)

if __name__ == '__main__':
  _main(sys.argv[0], sys.argv[1:])
