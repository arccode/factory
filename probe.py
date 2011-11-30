# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Probing routines for hardware and firmware identification.

There are three types of probe functions: hardware components, hash
values, and initial_config.

Probe functions must return the target identification string if the
probe was successful or None if no appropriate data was available.
Probe functions may also raise the Error exception to indicate that a
survivable error occurred, in which case the error will be reported
and a None probe result assumed.
"""


import hashlib
import logging
import os
import re
import sys

from array import array
from glob import glob
from inspect import getargspec
from tempfile import NamedTemporaryFile

import edid
import flashrom_util
import vblock

sys.path.append('/usr/local/lib/flimflam/test')
import flimflam

from common import CompactStr, Error, Obj, RunShellCmd


# TODO(tammo): Some tests look for multiple components, some tests
# throw away all but the first, and some just look for one.  All tests
# should return a list of results, with the empty list indicating no
# components were found.

# TODO(tammo): Get rid of trial-and-error detection.  If there are
# multiple different ways to perform detection, we should run them all
# and collate the results.  Different code paths on different systems
# leads to bitrot and fragility.


# Load-time decorator-populated { class : probe function } tables.
_COMPONENT_PROBE_MAP = {}
_HASH_PROBE_MAP = {}
_INITIAL_CONFIG_PROBE_MAP = {}

# Load-time decorator-populated { key : function } table.
_COMMON_DATA_PROVIDER_MAP = {
  'arch': None,               # Always calculated by Probe().
  'component_registry': None  # Provided as arg to Probe() itself.
  }

# Load-time decorator-populated { function : required common data } table.
_SHARED_DATA_REQS_MAP = {}


def _LoadKernelModule(name):
  """Ensure kernel module is loaded.  If not already loaded, do the load."""
  # TODO(tammo): Maybe lift into shared data for performance reasons.
  loaded = RunShellCmd('lsmod | grep -q %s' % name).success
  if not loaded:
    loaded = RunShellCmd('modprobe %s' % name).success
    if not loaded:
      raise Error('Cannot load kernel module: %s' % name)


def _ReadSysfsFields(base_path, field_list, optional_field_list=[]):
  """Return dict of {field_name: field_value} corresponding to SYSFS contents.

  Args:
    base_path: SYSFS directory which each field should be a file within.
    field_list: Required fields ; function returns None if fields are missing.
    optional_field_list: Fields that are included if the corresponding
      files exist.

  Returns:
    Dict of field names and values, or None if required fields are not
    all present.
  """
  all_fields_list  = field_list + optional_field_list
  path_list = [os.path.join(base_path, field) for field in all_fields_list]
  data = dict((field, open(path).read().strip())
              for field, path in zip(all_fields_list, path_list)
              if os.path.exists(path))
  result = [data[field] for field in all_fields_list if field in data]
  return result if set(data) >= set(field_list) else None


def _ReadSysfsPciFields(path):
  """Returns string containing PCI 'vendor:device' tuple."""
  # TODO(hungte): Maybe add PCI 'rev' field.
  field_data = _ReadSysfsFields(path, ['vendor', 'device'])
  if field_data is None:
    return None
  vendor, device = field_data
  return '%s:%s' % (vendor.replace('0x', ''), device.replace('0x', ''))


def _ReadSysfsUsbFields(path):
  """Returns string containing at least the USB 'idVendor:idProduct' tuple.

  Args:
    path: Path used to search for USB SYSFS data.  First all symlinks
      are resolved, to the the 'real' path.  Then path terms are
      iteratively removed from the right hand side until the remaining
      path looks to contain the relevent data fields.

  Returns:
    A string with the above tuple if a sutable directory with
    containing the field data can be found.  This string will also
    contain space-separated optional field data if those are
    available.  If no directory with the required fields are found,
    returns None.
  """
  path = os.path.realpath(path)
  while path.find('/usb') > 0:
    if os.path.exists(os.path.join(path, 'idProduct')):
      break
    path = os.path.split(path)[0]
  field_data = _ReadSysfsFields(path, ['idVendor', 'idProduct'],
                                ['manufacturer', 'product', 'bcdDevice'])
  if field_data is None:
    return None
  result = '%s:%s' % (field_data[0].replace('0x', ''),
                      field_data[1].replace('0x', ''))
  result += (' ' + ' '.join(field_data[2:])) if field_data[2:] else ''
  return result


def _ReadSysfsDeviceId(path):
  """Returns SYSFS PCI or USB device identification string."""
  return (_ReadSysfsPciFields(path) or
          _ReadSysfsUsbFields(path) or
          None)


def _ReadSysfsNodeId(path):
  """Returns SYSFS node identification string.

  A more generic wrapper around _ReadSysfsDeviceId which supports
  cases where only a 'name' file exists.  Basically it tries to read
  the DeviceID data if present, but otherwise falls back to just
  reading the name file data.
  """
  name_path = os.path.join(path, 'name')
  return (_ReadSysfsDeviceId(os.path.join(path, 'device')) or
          (os.path.exists(name_path) and
           open(name_path).read().strip()) or
          None)


class _FlimflamDevices(object):
  """Wrapper around flimflam (connection manager) information.

  This object is a wrapper around the data from the flimflam module,
  providing dbus format post processing.

  Wrapped data is a list of Objs corresponding to devices detected by
  flimflam.  Each has devtype (flimflam type classification) and path
  (location of related data in sysfs) fields.  For cellular devices,
  there is also an attributes field which contains a dict of
  attribute:value items.
  """

  def __init__(self):
    def ProcessDevice(device):
      properties = device.GetProperties()
      get_prop = lambda p: flimflam.convert_dbus_value(properties[p])
      result = Obj(
        devtype=get_prop('Type'),
        path='/sys/class/net/%s/device' % get_prop('Interface'))
      if result.devtype == 'cellular':
        result.attributes = dict(
          (key, get_prop('Cellular.%s' % key))
          for key in ['Carrier', 'FirmwareRevision', 'HardwareRevision',
                      'ModelID', 'Manufacturer']
          if ('Cellular.%s' % key) in properties)
      return result
    self.dev_list = [ProcessDevice(device) for device in
                     flimflam.FlimFlam().GetObjectList('Device')]

  def GetDevices(self, devtype):
    """Return device Obj list for devices with the specified type."""
    return [dev for dev in self.dev_list if dev.devtype == devtype]

  def ReadSysfsDeviceIds(self, devtype):
    """Return _ReadSysfsDeviceId result for each device of specified type."""
    ids = [_ReadSysfsDeviceId(dev.path) for dev in self.GetDevices(devtype)]
    return ' ; '.join(ids) if ids else None


def _RegisterSharedDataRequirements(fun):
  args = getargspec(fun)[0]
  for arg in args:
    assert arg in _COMMON_DATA_PROVIDER_MAP, \
        'No provider for required common data %s' % repr(arg)
  _SHARED_DATA_REQS_MAP[fun] = args


def _ProvidesSharedData(data_name):
  def Decorate(f):
    assert data_name not in _COMMON_DATA_PROVIDER_MAP, \
        'Multiple functions providing %s common data.' % repr(data_name)
    _COMMON_DATA_PROVIDER_MAP[data_name] = f
    _RegisterSharedDataRequirements(f)
    return f
  return Decorate


@_ProvidesSharedData('ec_fw')
def _LoadEcFirmware():
  return flashrom_util.LoadEcFirmware()


@_ProvidesSharedData('main_fw')
def _LoadMainFirmware():
  return flashrom_util.LoadMainFirmware()


@_ProvidesSharedData('touchpad')
def _LoadTouchpadData():
  """Return Obj with hw_ident and fw_ident string fields."""
  def Synaptics():
    detect_program = '/opt/Synaptics/bin/syndetect'
    if not os.path.exists(detect_program):
      return None
    lock_check = RunShellCmd('lsof /dev/serio_raw0 | grep -q "^X"')
    if lock_check.success and not os.getenv('DISPLAY'):
      logging.error('Synaptics touchpad detection with X in the '
                    'foreground requires DISPLAY and XAUTHORITY '
                    'to be set properly.')
      return None
    result = RunShellCmd(detect_program)
    if not result.success:
      return None
    properties = dict(map(str.strip, line.split('=', 1))
                      for line in result.stdout.splitlines() if '=' in line)
    model = properties.get('Model String', 'Unknown Synaptics')
    # Delete the " on xxx Port" substring, as we do not care about the port.
    model = re.sub(' on [^ ]* [Pp]ort$', '', model)
    firmware = properties.get('Firmware ID', None)
    return Obj(hw_ident=model, fw_ident=firmware)
  def Cypress():
    for node in glob('/sys/class/input/mouse[0-9]*/device/device'):
      model_path_list = [os.path.join(node, field) for field in
                         ['product_id', 'hardware_version', 'protocol_version']]
      firmware_path = os.path.join(node, 'firmware_version')
      if not all(os.path.exists(path) for path in
                 model_path_list + [firmware_path]):
        continue
      return Obj(
        hw_ident=CompactStr([open(path).read().strip()
                             for path in model_path_list]),
        fw_ident=CompactStr(open(firmware_path).read().strip()))
    return None
  def Generic():
    # TODO(hungte) add more information from id/*
    # format: N: Name="???_trackpad"
    input_file = '/proc/bus/input/devices'
    cmd = 'grep -iE "^N.*(touch *pad|track *pad)" %s' % input_file
    info = RunShellCmd(cmd).stdout.splitlines()
    info = [re.sub('^[^"]*"(.*)"$', r'\1', device) for device in info]
    return Obj(hw_ident=(', '.join(info) if info else None), fw_ident=None)
  result_gen = (vendor_fun() for vendor_fun in [Cypress, Synaptics, Generic])
  return next((x for x in result_gen if x is not None),
              Obj(hw_ident=None, fw_ident=None))


@_ProvidesSharedData('flimflam')
def _LoadFlimflam():
  """Function wrapper to allow decoration of the class contructor."""
  return _FlimflamDevices()


def _ComponentProbe(comp_class, *arch_targets):
  """Decorator that populates _COMPONENT_PROBE_MAP.

  There can only be one probe function for each arch for each
  comp_class.  If no arch_targets are specified, the probe is assumed
  to be general and apply for all arch values.

  Args:
    comp_class: Target component class for which the generator
      produces results.
    arch_targets: List of arch strings for which the probe is relevant.
  """
  def Decorate(f):
    if not arch_targets:
      assert comp_class not in _COMPONENT_PROBE_MAP, \
          'Multiple generic component probe functions for %s' % repr(comp_class)
      _COMPONENT_PROBE_MAP[comp_class] = f
    else:
      arch_map = _COMPONENT_PROBE_MAP.setdefault(comp_class, {})
      assert set(arch_targets).isdisjoint(set(arch_map)), \
          'Overlapping target architectures for %s probe function' % comp_class
      for arch in arch_targets:
        arch_map[arch] = f
    _RegisterSharedDataRequirements(f)
    return f
  return Decorate


@_ComponentProbe('audio_codec')
def _ProbeAudioCodec():
  """Looks for codec strings in /proc/asound then at PCM details."""
  grep_result = RunShellCmd('grep -R "Codec:" /proc/asound/*')
  match_list = [re.findall(r'.*Codec:(.*)', line)
                for line in grep_result.stdout.splitlines()]
  result_set = set(CompactStr(match) for match in match_list if match)
  if result_set:
    return ' ; '.join(result_set)
  # Formatted '00-00: WM??? PCM wm???-hifi-0: ...'
  pcm_data = open('/proc/asound/pcm').read().strip().split(' ')
  if len(pcm_data) > 2:
    return CompactStr(pcm_data[1])
  return None


@_ComponentProbe('battery')
def _ProbeBattery():
  """Compose data from SYSFS."""
  node_path_list = glob('/sys/class/power_supply/*')
  type_data_list = [_ReadSysfsFields(node_path, ['type'])[0]
                    for node_path in node_path_list]
  battery_field_list = ['manufacturer', 'model_name', 'technology',
                        'charge_full_design']
  battery_data_list = [_ReadSysfsFields(node_path, battery_field_list)
                       for node_path, type_data
                       in zip(node_path_list, type_data_list)
                       if type_data == 'Battery']
  results = [CompactStr(x) for x in battery_data_list]
  return ' ; '.join(results) if results else None


@_ComponentProbe('bluetooth')
def _ProbeBluetooth():
  return _ReadSysfsDeviceId('/sys/class/bluetooth/hci0/device')


@_ComponentProbe('camera')
def _ProbeCamera():
  # TODO(tammo): What is happening here?  Arch-specific stuff?  Doc string...
  # TODO(tammo/sheckylin): Try to replace the code below with OpenCV calls.
  info = []
  camera_node = '/sys/class/video4linux/video0'
  camera_data = _ReadSysfsNodeId(camera_node)
  if camera_data:
    info.append(camera_data)
  # For SOC cameras
  camera_data = _ReadSysfsFields(camera_node, ['device/control/name'])
  if camera_data:
    info.append(camera_data)
  # Try video4linux2 (v4l2) interface.
  # See /usr/include/linux/videodev2.h for definition of these consts.
  # 'ident' values are defined in include/media/v4l2-chip-ident.h
  VIDIOC_DBG_G_CHIP_IDENT = 0xc02c5651
  V4L2_DBG_CHIP_IDENT_SIZE = 11
  V4L2_INDEX_REVISION = V4L2_DBG_CHIP_IDENT_SIZE - 1
  V4L2_INDEX_IDENT = V4L2_INDEX_REVISION - 1
  V4L2_VALID_IDENT = 3  # V4L2_IDENT_UNKNOWN + 1
  try:
    with open('/dev/video0', 'r+') as f:
      buf = array('i', [0] * V4L2_DBG_CHIP_IDENT_SIZE)
      ioctl(f.fileno(), VIDIOC_DBG_G_CHIP_IDENT, buf, 1)
      v4l2_ident = buf[V4L2_INDEX_IDENT]
      if v4l2_ident >= V4L2_VALID_IDENT:
        info.append('V4L2:%04x %04x' % (v4l2_ident, buf[V4L2_INDEX_REVISION]))
  except:
    pass
  return CompactStr(info) if info else None


@_ComponentProbe('cellular')
def _ProbeCellular(flimflam):
  return flimflam.ReadSysfsDeviceIds('cellular')


@_ComponentProbe('display_converter')
def _ProbeDisplayConverter():
  """Try brand-specific probes, return the first viable result."""
  def ProbeChrontel():
    """Search style borrowed from the /etc/init/chrontel.conf behavior."""
    _LoadKernelModule('i2c-dev')
    _LoadKernelModule('i2c-i801')
    dev_chrontel = '/dev/i2c-chrontel'
    if not os.path.exists(dev_chrontel):
      for dev_path in glob('/sys/class/i2c-adapter/*'):
        adapter_name = open(os.path.join(dev_path, 'name')).read().strip()
        if adapter_name.startswith('SMBus I801 adapter'):
          dev_chrontel = os.path.basename(dev_path)
          break
    cmd = 'ch7036_monitor -d %s -p' % dev_chrontel
    if os.path.exists(dev_chrontel) and RunShellCmd(cmd).success:
      return 'ch7036'
    return None
  part_id_gen = (probe_fun() for probe_fun in [ProbeChrontel])
  return next((x for x in part_id_gen if x is not None), None)


# TODO(tammo): Either remove this probe or make it work better.
# @_ComponentProbe('cardreader')
def _ProbeCardreader(component_registry):
  """Look for white listed card readers in system logs.

  A cardreader is generally powered off until cards are inserted.
  Therefore, instead of directly checking, we compare log data against
  a white list of known devices.

  This avoids needing to insert a card just for probing purposes, but
  does still require that a card was inserted at some point prior to
  probing.  NOTE: The overhead of scanning the logs can be
  significant, and is naturally undesirable.
  """
  pattern = r'New USB device found, idVendor=.*, idProduct=.*'
  grep_result = RunShellCmd('grep -s %s /var/log/messages*' % repr(pattern))
  cardreader_whitelist = component_registry['cardreader'].values()
  match_list = [re.findall(r'idVendor=(.*), idProduct=(.*)', line)
                for line in grep_result.stdout.splitlines()]
  device_str_list = ['%s:%s' % match[0] for match in match_list if match]
  found_cardreader_set = set(device for device in device_str_list
                             if device in cardreader_whitelist)
  return (' '.join(found_cardreader_set) if found_cardreader_set
          else None)


@_ComponentProbe('chipset', 'x86')
def _ProbeChipsetX86():
  """On x86, host bridge is always the first PCI device."""
  return _ReadSysfsDeviceId('/sys/bus/pci/devices/0000:00:00.0')


@_ComponentProbe('chipset', 'arm')
def _ProbeChipsetArm():
  """On ARM SOC-based systems, use first compatible list in device-tree."""
  # Format: manufacturer,model [NUL] compat-manufacturer,model [NUL] ...
  fdt_compatible_file = '/proc/device-tree/compatible'
  if not os.path.exists(fdt_compatible_file):
    return None
  compatible_list = open(fdt_compatible_file).read().strip()
  return CompactStr(compatible_list.strip(chr(0)).split(chr(0)))


@_ComponentProbe('cpu', 'x86')
def _ProbeCpuX86():
  """Reformat /proc/cpuinfo data."""
  # For platforms like x86, it provides names for each core.
  # Sample output for dual-core:
  #   model name : Intel(R) Atom(TM) CPU ???
  #   model name : Intel(R) Atom(TM) CPU ???
  cmd = r'sed -nr "s/^model name\s*: (.*)/\1/p" /proc/cpuinfo'
  stdout = RunShellCmd(cmd).stdout.splitlines()
  return CompactStr(stdout[0] + ' [%d cores]' % len(stdout))


@_ComponentProbe('cpu', 'arm')
def _ProbeCpuArm():
  """Reformat /proc/cpuinfo data."""
  # For platforms like arm, it gives the name only in 'Processor'
  # and then a numeric ID for each cores 'processor', so delta is 1.
  # Sample output for dual-core:
  #   Processor : ARM???
  #   processor : 0
  #   processor : 1
  cmd = r'sed -nr "s/^[Pp]rocessor\s*: (.*)/\1/p" /proc/cpuinfo'
  stdout = RunShellCmd(cmd).stdout.splitlines()
  return CompactStr(stdout[0] + ' [%d cores]' % len(stdout) - 1)


@_ComponentProbe('display_panel')
def _ProbeDisplayPanel():
  """Combine all available edid data, from sysfs and directly from the i2c."""
  edid_set = set(edid.Parse(open(path).read())
                 for path in glob('/sys/class/drm/*LVDS*/edid'))
  _LoadKernelModule('i2c_dev')
  edid_set |= set(edid.LoadFromI2c(path)
                  for path in sorted(glob('/dev/i2c-?')))
  edid_set -= set([None])
  return ' ; '.join(sorted(edid_set)) if edid_set else None


@_ComponentProbe('dram', 'x86')
def _ProbeDramX86():
  """Combine mosys memory timing and geometry information."""
  # TODO(tammo): Document why mosys cannot load i2c_dev itself.
  _LoadKernelModule('i2c_dev')
  time_data = RunShellCmd('mosys -k memory spd print timings').stdout
  size_data = RunShellCmd('mosys -k memory spd print geometry').stdout
  times = dict(re.findall('dimm="([^"]*)".*speeds="([^"]*)"', time_data))
  sizes = dict(re.findall('dimm="([^"]*)".*size_mb="([^"]*)"', size_data))
  return CompactStr(['%s|%s|%s' % (i, sizes[i], times[i].replace(' ', ''))
                     for i in sorted(times)])


@_ComponentProbe('dram', 'arm')
def _ProbeDramArm():
  """Memory is not directly probable, so use kernel cmdline info."""
  # TODO(tammo): Request that mosys provide this info (by any means).
  cmdline = open('/proc/cmdline').read().strip()
  # Format: *mem=384M@0M (size@address)
  return CompactStr(re.findall(r'\s\w*mem=(\d+M@\d+M)', cmdline))


@_ComponentProbe('ec_flash_chip')
def _ProbeEcFlashChip(ec_fw):
  return ec_fw.chip_id


@_ComponentProbe('embedded_controller')
def _ProbeEmbeddedController():
  """Reformat superiotool output."""
  cmd_stdout = RunShellCmd('superiotool').stdout
  # Example cmd output:
  # 'superiotool r\nFound Nuvoton WPCE775x (id=0x05, rev=0x02) at 0x2e'
  match = re.findall(r'Found (.*) at', cmd_stdout)
  return CompactStr(match.pop()) if match else None


@_ComponentProbe('ethernet')
def _ProbeEthernet(flimflam):
  return flimflam.ReadSysfsDeviceIds('ethernet')


@_ComponentProbe('flash_chip')
def _ProbeMainFlashChip(main_fw):
  return main_fw.chip_id


@_ComponentProbe('storage')
def _ProbeStorage():
  """Compile SFSFS data for all block storage devices."""
  def ProcessNode(node_path):
    size_path = os.path.join(os.path.dirname(node_path), 'size')
    size = ('#' + open(size_path).read().strip()
            if os.path.exists(size_path) else '')
    ata_fields = ['vendor', 'model']
    emmc_fields = ['type', 'name', 'fwrev', 'hwrev', 'oemid', 'manfid']
    data = (_ReadSysfsFields(node_path, ata_fields) or
            _ReadSysfsFields(node_path, emmc_fields) or
            None)
    return CompactStr(data + [size]) if data is not None else None
  node_path_list = [node_path for node_path in glob('/sys/class/block/*/device')
                    if os.path.exists(node_path)]
  ident_list = [ident for ident in map(ProcessNode, node_path_list)
                if ident is not None]
  return ' ; '.join(ident_list) if ident_list else None


@_ComponentProbe('touchpad')
def _ProbeTouchpad(touchpad):
  return touchpad.hw_ident if touchpad is not None else None


@_ComponentProbe('tpm')
def _ProbeTpm():
  """Return Manufacturer_info : Chip_Version string from tpm_version output."""
  tpm_data = [line.partition(':') for line in
              RunShellCmd('tpm_version').stdout.splitlines()]
  tpm_dict = dict((key.strip(), value.strip()) for
                  key, _, value in tpm_data)
  mfg = tpm_dict.get('Manufacturer Info', None)
  version = tpm_dict.get('Chip Version', None)
  if mfg is not None and version is not None:
    return mfg + ':' + version
  return None


@_ComponentProbe('usb_hosts')
def _ProbeUsbHosts(arch):
  """Compile USB data from SYSFS."""
  # On x86, USB hosts are PCI devices, located in parent of root USB.
  # On ARM and others, use the root device itself.
  relpath = '.' if arch == 'arm' else '..'
  usb_bus_list = glob('/sys/bus/usb/devices/usb*')
  usb_host_list = [os.path.join(os.path.realpath(path), relpath)
                   for path in usb_bus_list]
  # Usually there are several USB hosts, so only list the primary information.
  device_id_list = [_ReadSysfsDeviceId(usb_host) for usb_host in usb_host_list]
  valid_device_id_list = [x for x in device_id_list if x is not None]
  return ' '.join(valid_device_id_list) if valid_device_id_list else None


@_ComponentProbe('vga')
def _ProbeVga():
  return _ReadSysfsNodeId('/sys/class/graphics/fb0')


@_ComponentProbe('wireless')
def _ProbeWireless(flimflam):
  return flimflam.ReadSysfsDeviceIds('wifi')


def _HashProbe(hash_class):
  """Decorator that populates _HASH_PROBE_MAP.

  There can be only one probe function for each hash_class.
  """
  def Decorate(f):
    assert hash_class not in _HASH_PROBE_MAP, \
        'Multiple hash probe functions for %s' % repr(hash_class)
    _HASH_PROBE_MAP[hash_class] = f
    _RegisterSharedDataRequirements(f)
    return f
  return Decorate


@_HashProbe('ro_main_firmware')
def _GetMainFirmwareReadOnlyHash(main_fw):
  """Returns hash of main firmware (BIOS) read only parts.

  Allows verification that we have proper keys / boot code / recovery
  image installed.

  Algorithm: sha256(fmap, RO_SECTION[-GBB]).
  """
  raw_image = open(main_fw.path, 'rb').read()
  image = flashrom_util.FirmwareImage(raw_image)
  hash_src = image.get_fmap_blob()
  gbb = image.get_section('GBB')
  zero_gbb = chr(0) * len(gbb)
  image.put_section('GBB', zero_gbb)
  hash_src += image.get_section('RO_SECTION')
  return hashlib.sha256(hash_src).hexdigest()


@_HashProbe('hash_gbb')
def _GetMainFirmwareGbbHash(main_fw):
  """Returns hash of main firmware (BIOS) GBB section.

  Allows verification that we have proper keys / images / HWID.

  Algorithm: sha256(GBB[-HWID]).
  """
  raw_image = open(main_fw.path, 'rb').read()
  image = flashrom_util.FirmwareImage(raw_image)
  # Clobber HWID in a copy of the GBB, to get a HWID-independent hash.
  with NamedTemporaryFile('wb', delete=True) as f:
    f.write(image.get_section('GBB'))
    RunShellCmd('gbb_utility -s --hwid="ChromeOS" "%s"' % f.name)
    hash_src = f.read()
  return hashlib.sha256(hash_src).hexdigest()


@_HashProbe('ro_ec_firmware')
def _GetEcFirmwareReadOnlyHash(ec_fw):
  """Returns hash of Embedded Controller firmware read only parts.

  Allows verification that we have proper updated version of EC firmware.

  Algorithm: sha256(fmap, EC_RO).
  """
  if ec_fw.chip_id is None:
    return None
  raw_image = open(ec_fw.path, 'rb').read()
  image = flashrom_util.FirmwareImage(raw_image)
  hash_src = image.get_fmap_blob()
  hash_src += image.get_section('EC_RO')
  return hashlib.sha256(hash_src).hexdigest()


def _CalculateMainFwKeyHash(main_fw_file, key_name):
  """Returns hash of the specified key from the main firmware.

  Extracts specified GBB key element from the main firmware, using the
  gbb_utility command and a temporary file.

  Algorithm: sha256(key%%[00|FF])).
  """
  with NamedTemporaryFile(prefix='gbb_%s_' % key_name, delete=True) as f:
    if not RunShellCmd('gbb_utility -g --%s=%s %s' %
                       (key_name, f.name, main_fw_file)).success:
      raise Error('cannot get %s from GBB' % key_name)
    hash_src = f.read()
  # Keys may be padded with 0x00 or 0xFF.
  return hashlib.sha256(hash_src.strip('\x00\xff')).hexdigest()


@_HashProbe('key_recovery')
def _CalculateRecoveryKeyHash(main_fw):
  return _CalculateMainFwKeyHash(main_fw.path, 'recoverykey')


@_HashProbe('key_root')
def _CalculateRootKeyHash(main_fw):
  return _CalculateMainFwKeyHash(main_fw.path, 'rootkey')


def _InitialConfigProbe(initial_config_class):
  """Decorator that populates _INITIAL_CONFIG_PROBE_MAP.

  There can be only one probe function for each initial_config_class.
  """
  def Decorate(f):
    assert initial_config_class not in _INITIAL_CONFIG_PROBE_MAP, \
        'Multiple initial config probe functions for %s' % \
        repr(initial_config_class)
    _INITIAL_CONFIG_PROBE_MAP[initial_config_class] = f
    _RegisterSharedDataRequirements(f)
    return f
  return Decorate


@_InitialConfigProbe('cellular_fw_version')
def _ProbeCellularFirmwareVersion(flimflam):
  """Return firmware detail strings for all cellular devices."""
  def GetVersionString(dev_attrs):
    """Use flimflam or modem status data to generate a version string.

    The fields present in the flimflam data may differ for
    partners/components.
    """
    # TODO(tammo): Document breakdown of known combinations for each
    # supported part, correspondingly document when the 'modem status'
    # fallback is necessary.
    version_formats = [
        ['Carrier', 'FirmwareRevision'],
        ['FirmwareRevision'],
        ['HardwareRevision']]
    for version_format in version_formats:
      if not set(version_format).issubset(set(dev_attrs)):
        continue
      # Compact all fields into single line with limited space.
      return CompactStr([dev_attrs[key] for key in version_format])
    # If nothing available, try 'modem status'.
    cmd = 'modem status | grep firmware_revision'
    modem_status = RunShellCmd(cmd).stdout.stip()
    info = re.findall('^\s*firmware_revision:\s*(.*)', modem_status)
    if info and info[0]:
      return info[0]
    return None
  results = [GetVersionString(dev.attributes) for dev in
             flimflam.GetDevices('cellular')]
  results = [x for x in results if x is not None]
  return ' ; '.join(results) if results else None


@_InitialConfigProbe('rw_fw_version')
def _ProbeRwFirmwareVersion(main_fw):
  """Returns RW (writable) firmware version from VBLOCK sections.

  If A/B has different version, that means this system needs a reboot +
  firmwar update so return value is a "error report" in the form "A=x, B=y".
  """
  versions = [None, None]
  with open(main_fw.path, 'rb') as f:
    image = flashrom_util.FirmwareImage(f.read())
  for (index, name) in enumerate(['VBLOCK_A', 'VBLOCK_B']):
    data = image.get_section(name)
    block = vblock.unpack_verification_block(data)
    versions[index] = block['VbFirmwarePreambleHeader']['firmware_version']
  if len(versions) != 2:
    raise Error('Bad RW FW version data.')
  if versions[0] != versions[1]:
    return 'A=%d, B=%d' % versions
  return '%d' % versions[0]


@_InitialConfigProbe('touchpad_fw_version')
def _ProbeTouchpadFirmwareVersion(touchpad):
  return touchpad.fw_ident if touchpad is not None else None


# TODO(tammo): Consider getting rid of the component_registry
# argument.  Without it, probeing can be done independently of any
# component database, which is conceptually much cleaner.  Currently
# the only code that needs this is the card_reader probe to whitelist
# device identifiers, but this probe also has other ugliness -- it
# does not actually probe, but instead just crawls logs. which will
# introduce flakiness if the reader was never used.  One possible
# approach here is to add an option to the functional test for the
# card reader, so that it checks that the card readers it finds are
# the ones that we want.  The benefit here is that the functional test
# will always have all the information it needs, because the reader is
# active.  For example, it could use the hwid_tool to query the reader
# associated with the system (and maybe just give a warning if there
# is no hwid set yet).
def Probe(component_registry, probe_volatile=True, probe_initial_config=True):
  """Return device component, hash, and initial_config data.

  Run all of the available probing routines that make sense for the
  target architecture, for example if the machine being probed is x86
  then somewhat different probes would be run than for an ARM machine.

  All probe results are returned directly, without analysis.  Matching
  these results against the component database or against HWID data
  can be done afterwards.

  Args:
    component_registry: Dict of {component name: probe result} data,
      which can be used by probe routines (for example as a whitelist
      of known components of certain component classes, eg
      cardreader).
    probe_volatile: On False, do not probe for volatile data and
      return None for the corresponding field.
    probe_initial_config: On False, do not probe for initial_config
      data and return None for the corresponding field.
  Returns:
    Obj with components, volatile, and initial_config fields, each
    containing the corresponding dict of probe results.
  """
  arch = RunShellCmd('crossystem arch').stdout.strip()
  shared_data = { 'arch': arch, 'component_registry': component_registry }
  def PopulateSharedData(data_name):
    if data_name in shared_data:
      return
    fun = _COMMON_DATA_PROVIDER_MAP[data_name]
    shared_data[data_name] = RunFunWithSharedData(fun)
  def RunFunWithSharedData(fun):
    required_data_name_list = _SHARED_DATA_REQS_MAP[fun]
    map(PopulateSharedData, required_data_name_list)
    fun_args = dict((x, shared_data[x]) for x in shared_data
                    if x in required_data_name_list)
    return fun(**fun_args)
  def RunProbe(fun):
    try:
      return RunFunWithSharedData(fun)
    except Error, e:
      logging.exception(e)
      logging.error('Probe failed, returning None.')
      return None
  component_result_map = {}
  hash_result_map = {}
  initial_config_result_map = {}
  for component_class, fun_data in sorted(_COMPONENT_PROBE_MAP.items()):
    fun = fun_data[arch] if isinstance(fun_data, dict) else fun_data
    component_result_map[component_class] = RunProbe(fun)
  if probe_volatile:
    # TODO(tammo): Lift out the hash generation, to allow convenient
    # generation of hashes directly for firmware images (as opposed to
    # just DUT machines).  Ideally provide a command (maybe in
    # hwid_tool) which will take an arbitrary firmware image/blob,
    # determine the firmware type (main, ec, etc) and then generate
    # all of the corresponding hashes.  This command, similar to
    # probing for new BOM components, should help with appending new
    # hash values to the database.
    for hash_class, fun in sorted(_HASH_PROBE_MAP.items()):
      hash_result_map[hash_class] = RunProbe(fun)
  else:
    hash_result_map = None
  if probe_initial_config:
    for initial_config_class, fun in sorted(_INITIAL_CONFIG_PROBE_MAP.items()):
      initial_config_result_map[initial_config_class] = RunProbe(fun)
  else:
    initial_config_result_map = None
  return Obj(components=component_result_map,
             volatiles=hash_result_map,
             initial_configs=initial_config_result_map)
