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
from fcntl import ioctl
from tempfile import NamedTemporaryFile

import factory_common  # pylint: disable=W0611

from cros.factory import system
from cros.factory.common import CompactStr, Error, Obj, ParseKeyValueData, Shell
from cros.factory.gooftool import edid
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import vblock
# pylint: disable=E0611
from cros.factory.hwdb.hwid_tool import ProbeResults, COMPACT_PROBE_STR

try:
  sys.path.append('/usr/local/lib/flimflam/test')
  import flimflam  # pylint: disable=F0401
except: # pylint: disable=W0702
  pass

# TODO(tammo): Some tests look for multiple components, some tests
# throw away all but the first, and some just look for one.  All tests
# should return a list of results, with the empty list indicating no
# components were found.

# TODO(tammo): Get rid of trial-and-error detection.  If there are
# multiple different ways to perform detection, we should run them all
# and collate the results.  Different code paths on different systems
# leads to bitrot and fragility.


# Load-time decorator-populated dicts (arch of None implies generality):
# { arch : { class : probe function } }
_COMPONENT_PROBE_MAP = {}
_INITIAL_CONFIG_PROBE_MAP = {}

# Load-time decorator-populated set of probably component classes.
PROBEABLE_COMPONENT_CLASSES = set()

# If this file is present, we'll return its probe results rather than
# actually probing.
FAKE_PROBE_RESULTS_FILE = '/tmp/fake_probe_results.yaml'


def DictCompactProbeStr(content):
  return {COMPACT_PROBE_STR: CompactStr(content)}


def _LoadKernelModule(name, error_on_fail=True):
  """Ensure kernel module is loaded.  If not already loaded, do the load."""
  # TODO(tammo): Maybe lift into shared data for performance reasons.
  loaded = Shell('lsmod | grep -q %s' % name).success
  if not loaded:
    loaded = Shell('modprobe %s' % name).success
    if (not loaded) and error_on_fail:
      raise Error('Cannot load kernel module: %s' % name)
  return loaded


def _ReadSysfsFields(base_path, field_list, optional_field_list=None):
  """Return dict of {field_name: field_value} corresponding to sysfs contents.

  Args:
    base_path: sysfs directory which each field should be a file within.
    field_list: Required fields ; function returns None if fields are missing.
    optional_field_list: Fields that are included if the corresponding
      files exist.

  Returns:
    Dict of field names and values, or None if required fields are not
    all present.
  """
  all_fields_list  = field_list + (optional_field_list or [])
  path_list = [os.path.join(base_path, field) for field in all_fields_list]
  data = dict((field, open(path).read().strip())
              for field, path in zip(all_fields_list, path_list)
              if os.path.exists(path) and not os.path.isdir(path))
  if not set(data) >= set(field_list):
    return None
  data.update(DictCompactProbeStr(
      [data[field] for field in all_fields_list if field in data]))
  return data


def _ReadSysfsPciFields(path):
  """Returns string containing PCI 'vendor:device' tuple."""
  # TODO(hungte): Maybe add PCI 'rev' field.
  field_data = _ReadSysfsFields(path, ['vendor', 'device'])
  if field_data is None:
    return None
  field_data.update(DictCompactProbeStr([
      '%s:%s' % (field_data['vendor'].replace('0x', ''),
                 field_data['device'].replace('0x', ''))]))
  return field_data


def _ReadSysfsUsbFields(path):
  """Returns dict containing at least the values of USB 'idVendor' and
  'idProduct'.

  Args:
    path: Path used to search for USB sysfs data.  First all symlinks
      are resolved, to the the 'real' path.  Then path terms are
      iteratively removed from the right hand side until the remaining
      path looks to contain the relevent data fields.

  Returns:
    A dict with the USB 'idVendor' and 'idProduct' values if a sutable
    directory containing the field data can be found. This dict will also
    contain other optional field data if those are available. If no directory
    with the required fields are found, returns None.
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
  compact_str_list = ['%s:%s' % (field_data['idVendor'].replace('0x', ''),
                                 field_data['idProduct'].replace('0x', ''))]
  for key in ['manufacturer', 'product', 'bcdDevice']:
    if field_data.get(key):
      compact_str_list.append(field_data[key])
  field_data.update(DictCompactProbeStr(compact_str_list))
  return field_data


def _ReadSysfsDeviceId(path, ignore_usb=False):
  """Returns sysfs PCI or USB device identification string."""
  return (_ReadSysfsPciFields(path) or
          (_ReadSysfsUsbFields(path) if not ignore_usb else None) or
          None)


def _ReadSysfsNodeId(path):
  """Returns sysfs node identification string.

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


def _RecursiveProbe(path, read_method):
  """Recursively probes in path and all the subdirectory using read_method.

  Args:
    path: Root path of the recursive probing.
    read_method: The method used to probe device information.
      This method accepts an input path and returns a string.
      e.g. _ReadSysfsUsbFields, _ReadSysfsPciFields, or _ReadSysfsDeviceId.

  Returns:
    A list of strings which contains probed results under path and
    all the subdirectory of path. Duplicated data will be omitted.
  """
  def _InternalRecursiveProbe(path, visited_path, data_list, read_method):
    """Recursively probes in path and all the subdirectory using read_method.

    Args:
      path: Root path of the recursive probing.
      visited_path: A set containing visited paths. These paths will not
        be visited again.
      data_list: A list of string which contains probed results.
        This list will be appended through the recursive probing.
      read_method: The method used to probe device information.
        This method accepts an input path and returns a string.

    Returns:
      No return value. data_list in the input will be appended with probed
      information. Duplicated data will be omitted.
    """
    path = os.path.realpath(path)
    if path in visited_path:
      return

    if os.path.isdir(path):
      data = read_method(path)
      # Only append new data
      if data not in data_list:
        data_list.append(data)
      entries_list = os.listdir(path)
      visited_path.add(path)
    else:
      return

    for filename in entries_list:
      # Do not search directory upward
      if filename == 'subsystem':
        continue
      sub_path = os.path.join(path, filename)
      _InternalRecursiveProbe(sub_path, visited_path, data_list, read_method)
    return

  visited_path = set()
  data_list = []
  _InternalRecursiveProbe(path, visited_path, data_list, read_method)
  return data_list

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

  cached_dev_list = None

  @classmethod
  def GetDevices(cls, devtype):
    """Return device Obj list for devices with the specified type."""

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

    if cls.cached_dev_list is None:
      cls.cached_dev_list = [ProcessDevice(device) for device in
                             flimflam.FlimFlam().GetObjectList('Device')]
    return [dev for dev in cls.cached_dev_list if dev.devtype == devtype]

  @classmethod
  def ReadSysfsDeviceIds(cls, devtype, ignore_usb=False):
    """Return _ReadSysfsDeviceId result for each device of specified type."""
    ids = [_ReadSysfsDeviceId(dev.path, ignore_usb)
           for dev in cls.GetDevices(devtype)]
    # Filter out 'None' results
    return sorted(device for device in ids if device is not None)


class _TouchpadData():  # pylint: disable=W0232
  """Return Obj with hw_ident and fw_ident string fields."""

  @classmethod
  def Synaptics(cls):
    detect_program = '/opt/Synaptics/bin/syndetect'
    if not os.path.exists(detect_program):
      return None
    lock_check = Shell('lsof /dev/serio_raw0 | grep -q "^X"')
    if lock_check.success and not os.getenv('DISPLAY'):
      logging.error('Synaptics touchpad detection with X in the '
                    'foreground requires DISPLAY and XAUTHORITY '
                    'to be set properly.')
      return None
    result = Shell(detect_program)
    if not result.success:
      return None
    properties = dict(map(str.strip, line.split('=', 1))
                      for line in result.stdout.splitlines() if '=' in line)
    model = properties.get('Model String', 'Unknown Synaptics')
    # Delete the " on xxx Port" substring, as we do not care about the port.
    model = re.sub(' on [^ ]* [Pp]ort$', '', model)
    firmware = properties.get('Firmware ID', None)
    return Obj(ident_str=model, fw_version=firmware)

  @classmethod
  def Cypress(cls):
    for node in glob('/sys/class/input/mouse[0-9]*/device/device'):
      model_path_list = [os.path.join(node, field) for field in
                         ['product_id', 'hardware_version', 'protocol_version']]
      firmware_path = os.path.join(node, 'firmware_version')
      if not all(os.path.exists(path) for path in
                 model_path_list + [firmware_path]):
        continue
      return Obj(
        ident_str=CompactStr(
            [open(path).read().strip() for path in model_path_list]),
        fw_version=CompactStr(open(firmware_path).read().strip()))
    return None

  @classmethod
  def Atmel(cls):
    input_file = '/proc/bus/input/devices'
    re_device_name = re.compile(r'^N: Name="(Atmel.*Touchpad)"$', re.MULTILINE)
    re_sysfs = re.compile(r'^S: Sysfs=(.*)$', re.MULTILINE)
    with open(input_file, 'r') as f:
      buf = f.read()
    devices = buf.split('\n\n')
    for d in devices:
      match = re_device_name.findall(d)
      if not match:
        continue
      device_name = match[0]
      sysfs_path = os.path.join('/sys', re_sysfs.findall(d)[0].lstrip('/'))
      with open(os.path.join(sysfs_path, '..', '..', 'fw_version'), 'r') as f:
        fw_version = f.read().strip()
      with open(os.path.join(sysfs_path, '..', '..', 'config_csum'), 'r') as f:
        config_csum = f.read().strip()
      return Obj(ident_str=device_name, fw_version=fw_version,
                 config_csum=config_csum)

  @classmethod
  def Generic(cls):
    # TODO(hungte) add more information from id/*
    # format: N: Name="???_trackpad"
    input_file = '/proc/bus/input/devices'
    cmd = 'grep -iE "^N.*(touch *pad|track *pad)" %s' % input_file
    info = Shell(cmd).stdout.splitlines()
    info = [re.sub('^[^"]*"(.*)"$', r'\1', device) for device in info]
    return Obj(ident_str=(', '.join(info) if info else None), fw_version=None)

  cached_data = None

  @classmethod
  def Get(cls):
    if cls.cached_data is None:
      cls.cached_data = Obj(ident_str=None, fw_version=None)
      for vendor_fun in [cls.Cypress, cls.Synaptics, cls.Atmel, cls.Generic]:
        data = vendor_fun()
        if data is not None:
          cls.cached_data = data
          break
    return cls.cached_data


def _ProbeFun(probe_map, probe_class, *arch_targets):
  """Decorator that populates probe_map.

  There can only be one probe function for each arch for each
  probe_class.  If no arch_targets are specified, the probe is assumed
  to be general and apply for those arches whithout arch specific
  probes.

  Args:
    probe_map: Map to update.
    comp_class: Probe class for which the probe fun produces results.
    arch_targets: List of arches for which the probe is relevant.
  """
  def Decorate(f):
    arch_list = arch_targets if arch_targets else [None]
    for arch in arch_list:
      arch_probe_map = probe_map.setdefault(arch, {})
      assert probe_class not in arch_probe_map, (
          'Multiple component probe functions for %r %r',
          arch if arch else 'generic', probe_class)
      arch_probe_map[probe_class] = f
    return f
  return Decorate


def _ComponentProbe(probe_class, *arch_targets):
  PROBEABLE_COMPONENT_CLASSES.add(probe_class)
  return _ProbeFun(_COMPONENT_PROBE_MAP, probe_class, *arch_targets)


def _InitialConfigProbe(probe_class, *arch_targets):
  return _ProbeFun(_INITIAL_CONFIG_PROBE_MAP, probe_class, *arch_targets)


@_ComponentProbe('audio_codec')
def _ProbeAudioCodec():
  """Looks for codec strings in /proc/asound then at PCM details."""
  grep_result = Shell('grep -R "Codec:" /proc/asound/*')
  match_set = set()
  for line in grep_result.stdout.splitlines():
    match_set |= set(re.findall(r'.*Codec:(.*)', line))
  results = [DictCompactProbeStr(match) for match in sorted(match_set) if match]
  if results:
    return results
  # Formatted '00-00: WM??? PCM wm???-hifi-0: ...'
  pcm_data = open('/proc/asound/pcm').read().strip().split(' ')
  if len(pcm_data) > 2:
    return [DictCompactProbeStr(pcm_data[1])]
  return []


@_ComponentProbe('battery')
def _ProbeBattery():
  """Compose data from sysfs."""
  node_path_list = glob('/sys/class/power_supply/*')
  type_data_list = [_ReadSysfsFields(node_path, ['type'])['type']
                    for node_path in node_path_list]
  battery_field_list = ['manufacturer', 'model_name', 'technology']
  # probe energy_full_design or charge_full_design, battery can have either
  battery_full_field_candidate = ['charge_full_design',
                                  'energy_full_design']
  battery_full_field_candidate_found = False
  for candidate in battery_full_field_candidate:
    if any(os.path.exists(os.path.join(path, candidate))
           for path in node_path_list):
      battery_field_list.append(candidate)
      battery_full_field_candidate_found = True
      break
  if not battery_full_field_candidate_found:
    return []
  battery_data_list = [_ReadSysfsFields(node_path, battery_field_list)
                       for node_path, type_data
                       in zip(node_path_list, type_data_list)
                       if type_data == 'Battery']
  return sorted(x for x in battery_data_list if x)


@_ComponentProbe('bluetooth')
def _ProbeBluetooth():
  # Probe in primary path
  device_id = _ReadSysfsDeviceId('/sys/class/bluetooth/hci0/device')
  if device_id:
    return [device_id]
  # Use information in driver if probe failed in primary path
  device_id_list = _RecursiveProbe('/sys/module/bluetooth/holders',
                                   _ReadSysfsDeviceId)
  return sorted(x for x in device_id_list if x)


@_ComponentProbe('camera')
def _ProbeCamera():
  # TODO(tammo): What is happening here?  Arch-specific stuff?  Doc string...
  # TODO(tammo/sheckylin): Try to replace the code below with OpenCV calls.
  info = {}
  camera_node = '/sys/class/video4linux/video0'
  camera_data = _ReadSysfsNodeId(camera_node)
  if camera_data:
    info.update(camera_data)
  # For SOC cameras
  camera_data_soc = _ReadSysfsFields(camera_node, ['device/control/name'])
  if camera_data_soc:
    info.update(camera_data_soc)
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
        info['ident'] = 'V4L2:%04x %04x' % (v4l2_ident,
                                            buf[V4L2_INDEX_REVISION])
  except:  # pylint: disable=W0702
    pass
  return [info] if info else []


@_ComponentProbe('cellular')
def _ProbeCellular():
  data = _FlimflamDevices.ReadSysfsDeviceIds('cellular')
  if data:
    carrier = re.findall(
        r'^\s*carrier: (.*)$', Shell('modem status').stdout, re.M)
    if carrier:
      data[0]['carrier'] = carrier[0]
  return data


@_ComponentProbe('wimax')
def _ProbeWimax():
  return _FlimflamDevices.ReadSysfsDeviceIds('wimax')


@_ComponentProbe('display_converter')
def _ProbeDisplayConverter():
  """Try brand-specific probes, return the first viable result."""
  def ProbeChrontel():
    """Search style borrowed from the /etc/init/chrontel.conf behavior."""
    _LoadKernelModule('i2c-dev')
    # i2c-i801 is not available on some devices (ex, ARM).
    _LoadKernelModule('i2c-i801', error_on_fail=False)
    dev_chrontel = '/dev/i2c-chrontel'
    if not os.path.exists(dev_chrontel):
      for dev_path in glob('/sys/class/i2c-adapter/*'):
        adapter_name = open(os.path.join(dev_path, 'name')).read().strip()
        if adapter_name.startswith('SMBus I801 adapter'):
          dev_chrontel = os.path.basename(dev_path)
          break
    cmd = 'ch7036_monitor -d %s -p' % dev_chrontel
    if os.path.exists(dev_chrontel) and Shell(cmd).success:
      return 'ch7036'
    return None
  part_id_gen = (probe_fun() for probe_fun in [ProbeChrontel])
  return next(([x] for x in part_id_gen if x is not None), [])


@_ComponentProbe('chipset', 'x86')
def _ProbeChipsetX86():
  """On x86, host bridge is always the first PCI device."""
  device_id = _ReadSysfsDeviceId('/sys/bus/pci/devices/0000:00:00.0')
  return [device_id] if device_id is not None else []


@_ComponentProbe('chipset', 'arm')
def _ProbeChipsetArm():
  """On ARM SOC-based systems, use first compatible list in device-tree."""
  # Format: manufacturer,model [NUL] compat-manufacturer,model [NUL] ...
  fdt_compatible_file = '/proc/device-tree/compatible'
  if not os.path.exists(fdt_compatible_file):
    return []
  compatible_list = open(fdt_compatible_file).read().strip()
  return [DictCompactProbeStr(compatible_list.strip(chr(0)).split(chr(0)))]


@_ComponentProbe('cpu', 'x86')
def _ProbeCpuX86():
  """Reformat /proc/cpuinfo data."""
  # For platforms like x86, it provides names for each core.
  # Sample output for dual-core:
  #   model name : Intel(R) Atom(TM) CPU ???
  #   model name : Intel(R) Atom(TM) CPU ???
  cmd = r'sed -nr "s/^model name\s*: (.*)/\1/p" /proc/cpuinfo'
  stdout = Shell(cmd).stdout.splitlines()
  return [{'model': stdout[0], 'cores': str(len(stdout)),
           COMPACT_PROBE_STR: CompactStr(
               '%s [%d cores]' % (stdout[0], len(stdout)))}]


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
  stdout = Shell(cmd).stdout.splitlines()
  return [{'model': stdout[0], 'cores': str(len(stdout) - 1),
           COMPACT_PROBE_STR: CompactStr(
               stdout[0] + ' [%d cores]' % (len(stdout) - 1))}]


@_ComponentProbe('display_panel')
def _ProbeDisplayPanel():
  """Combine all available edid data, from sysfs and directly from the i2c."""
  edid_list = []
  for path in glob('/sys/class/drm/*LVDS*/edid'):
    with open(path) as f:
      parsed_edid = edid.Parse(f.read())
      if parsed_edid:
        edid_list.append(parsed_edid)
  _LoadKernelModule('i2c_dev')
  for path in sorted(glob('/dev/i2c-[0-9]*')):
    parsed_edid = edid.LoadFromI2c(path)
    if parsed_edid:
      edid_list.append(parsed_edid)
  return edid_list


@_ComponentProbe('dram')
def _ProbeDram():
  """Combine mosys memory timing and geometry information."""
  # TODO(tammo): Document why mosys cannot load i2c_dev itself.
  _LoadKernelModule('i2c_dev')
  part_data = Shell('mosys -k memory spd print id').stdout
  timing_data = Shell('mosys -k memory spd print timings').stdout
  size_data = Shell('mosys -k memory spd print geometry').stdout
  parts = dict(re.findall('dimm="([^"]*)".*part_number="([^"]*)"', part_data))
  timings = dict(re.findall('dimm="([^"]*)".*speeds="([^"]*)"', timing_data))
  sizes = dict(re.findall('dimm="([^"]*)".*size_mb="([^"]*)"', size_data))
  results = []
  for slot in sorted(parts):
    part = parts[slot]
    size = sizes[slot]
    timing = timings[slot].replace(' ', '')
    results.append({
        'slot': slot,
        'part': part,
        'size': size,
        'timing': timing,
        COMPACT_PROBE_STR: CompactStr(['|'.join([slot, part, size, timing])])})
  return results


@_ComponentProbe('ec_flash_chip')
def _ProbeEcFlashChip():
  chip_id = crosfw.LoadEcFirmware().GetChipId()
  return [{COMPACT_PROBE_STR: chip_id}] if chip_id is not None else []


@_ComponentProbe('embedded_controller')
def _ProbeEmbeddedController():
  """Reformat mosys output."""
  # Example mosys command output:
  # vendor="VENDOR" name="CHIPNAME" fw_version="ECFWVER"
  ecinfo = re.findall(r'\bvendor="([^"]*)".*\bname="([^"]*)"',
                      Shell('mosys -k ec info').stdout)
  if not ecinfo:
    return []
  return [{'vendor': ecinfo[0][0], 'name': ecinfo[0][1],
           COMPACT_PROBE_STR: CompactStr(*ecinfo)}]


@_ComponentProbe('ethernet')
def _ProbeEthernet():
  # Build-in ethernet devices should not be attached to USB. They are usually
  # either PCI or SOC.
  return _FlimflamDevices.ReadSysfsDeviceIds('ethernet', ignore_usb=True)


@_ComponentProbe('flash_chip')
def _ProbeMainFlashChip():
  chip_id = crosfw.LoadMainFirmware().GetChipId()
  return [{COMPACT_PROBE_STR: chip_id}] if chip_id else []


def _GetFixedDevices():
  """Returns paths to all fixed storage devices on the system."""
  ret = []

  for node in sorted(glob('/sys/class/block/*')):
    path = os.path.join(node, 'removable')
    if not os.path.exists(path) or open(path).read().strip() != '0':
      continue
    if re.match('^loop|^dm-', os.path.basename(node)):
      # Loopback or dm-verity device; skip
      continue

    ret.append(node)

  return ret


@_ComponentProbe('storage')
def _ProbeStorage():
  """Compile sysfs data for all non-removable block storage devices."""
  def ProcessNode(node_path):
    dev_path = os.path.join(node_path, 'device')
    size_path = os.path.join(os.path.dirname(dev_path), 'size')
    sectors = (open(size_path).read().strip()
               if os.path.exists(size_path) else '')
    ata_fields = ['vendor', 'model']
    emmc_fields = ['type', 'name', 'hwrev', 'oemid', 'manfid']
    data = (_ReadSysfsFields(dev_path, ata_fields) or
            _ReadSysfsFields(dev_path, emmc_fields) or
            None)
    if not data:
      return None
    data['sectors'] = sectors
    data[COMPACT_PROBE_STR] = ' '.join([data[COMPACT_PROBE_STR],
                                        '#' + data['sectors']])
    return data
  return [ident for ident in map(ProcessNode, _GetFixedDevices())
          if ident is not None]


@_ComponentProbe('touchpad')
def _ProbeTouchpad():
  data = _TouchpadData.Get()
  if data.ident_str is None:
    return []

  results = {'id': data.ident_str}
  results.update(DictCompactProbeStr(data.ident_str))
  for key in ('fw_version', 'config_csum'):
    value = getattr(data, key)
    if value:
      results[key] = value
  return [results]


@_ComponentProbe('tpm')
def _ProbeTpm():
  """Return Manufacturer_info : Chip_Version string from tpm_version output."""
  tpm_data = [line.partition(':') for line in
              Shell('tpm_version').stdout.splitlines()]
  tpm_dict = dict((key.strip(), value.strip()) for
                  key, _, value in tpm_data)
  mfg = tpm_dict.get('Manufacturer Info', None)
  version = tpm_dict.get('Chip Version', None)
  if mfg is not None and version is not None:
    return [{'manufacturer_info': mfg, 'version': version,
             COMPACT_PROBE_STR: CompactStr(mfg + ':' + version)}]
  return []


@_ComponentProbe('usb_hosts')
def _ProbeUsbHosts():
  """Compile USB data from sysfs."""
  # On x86, USB hosts are PCI devices, located in parent of root USB.
  # On ARM and others, use the root device itself.
  # TODO(tammo): Think of a better way to do this, without arch.
  arch = Shell('crossystem arch').stdout.strip()
  relpath = '.' if arch == 'arm' else '..'
  usb_bus_list = glob('/sys/bus/usb/devices/usb*')
  usb_host_list = [os.path.join(os.path.realpath(path), relpath)
                   for path in usb_bus_list]
  # Usually there are several USB hosts, so only list the primary information.
  device_id_list = [_ReadSysfsDeviceId(usb_host) for usb_host in usb_host_list]
  return [x for x in device_id_list if x is not None]


@_ComponentProbe('vga')
def _ProbeVga():
  node_id = _ReadSysfsNodeId('/sys/class/graphics/fb0')
  return [node_id] if node_id is not None else []


@_ComponentProbe('wireless')
def _ProbeWireless():
  return _FlimflamDevices.ReadSysfsDeviceIds('wifi')

@_ComponentProbe('pmic')
def _ProbePmic():
  pmics = glob('/sys/bus/platform/devices/*-pmic')
  return ([{COMPACT_PROBE_STR: os.path.basename(x)} for x in pmics]
          if pmics else [])

@_ComponentProbe('keyboard')
def _ProbeKeyboard():
  ro_vpd = ReadRoVpd(crosfw.LoadMainFirmware().GetFileName())
  try:
    return [{COMPACT_PROBE_STR: ro_vpd['keyboard_layout']}]
  except KeyError:
    return []


@_InitialConfigProbe('cellular_fw_version')
def _ProbeCellularFirmwareVersion():
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
    modem_status = Shell(cmd).stdout.strip()
    info = re.findall('^\s*firmware_revision:\s*(.*)', modem_status)
    if info and info[0]:
      return info[0]
    return None
  results = [GetVersionString(dev.attributes) for dev in
             _FlimflamDevices.GetDevices('cellular')]
  results = [x for x in results if x is not None]
  return ' ; '.join(results)


@_InitialConfigProbe('rw_fw_key_version')
def _ProbeRwFirmwareVersion():
  """Returns RW (writable) firmware version from VBLOCK sections."""
  def GetVersion(section_name):
    data = image.get_section(section_name)
    block = vblock.unpack_verification_block(data)
    return block['VbFirmwarePreambleHeader']['firmware_version']
  main_fw_file = crosfw.LoadMainFirmware().GetFileName()
  image = crosfw.FirmwareImage(open(main_fw_file, 'rb').read())
  versions = map(GetVersion, ['VBLOCK_A', 'VBLOCK_B'])
  if versions[0] != versions[1]:
    return 'A=%d, B=%d' % versions
  return '%d' % versions[0]


@_InitialConfigProbe('touchpad_fw_version')
def _ProbeTouchpadFirmwareVersion():
  return _TouchpadData.Get().fw_version


@_InitialConfigProbe('storage_fw_version')
def _ProbeStorageFirmwareVersion():
  """Returns firmware rev for all fixed devices."""
  ret = []
  for f in _GetFixedDevices():
    smartctl = Shell('smartctl --all %s' %
                      os.path.join('/dev', os.path.basename(f))).stdout
    matches = re.findall('(?m)^Firmware Version:\s+(.+)$', smartctl)
    if matches:
      if re.search(r'(?m)^Device Model:\s+SanDisk', smartctl):
        # Canonicalize SanDisk firmware versions by replacing 'CS' with '11'.
        matches = [re.sub('^CS', '11', x) for x in matches]
      ret.extend(matches)
    else:
      # Use fwrev file (e.g., for eMMC where smartctl is unsupported)
      fw_rev = _ReadSysfsFields(os.path.join(f, 'device'), ['fwrev'])
      if fw_rev:
        ret.extend(fw_rev.values())
  return CompactStr(ret)


def _AddFirmwareIdTag(image, id_name='RO_FRID'):
  """Returns firmware ID in '#NAME' format if available."""
  if not image.has_section(id_name):
    return ''
  id_stripped = image.get_section(id_name).strip(chr(0))
  if id_stripped:
    return '#%s' % id_stripped
  return ''


def _GbbHash(image):
  """Algorithm: sha256(GBB[-HWID]); GBB without HWID."""
  with NamedTemporaryFile('w+b') as f:
    data = image.get_section('GBB')
    f.write(data)
    f.flush()
    if not Shell('gbb_utility -s --hwid="ChromeOS" --flags=0 "%s"' %
                 f.name).success:
      logging.error("Failed calling gbb_utility to calcuate GBB hash.")
      return None
    # Rewind to re-read the data.
    f.seek(0)
    hash_src = f.read()
    assert len(hash_src) == len(data)
  # pylint: disable=E1101
  return {COMPACT_PROBE_STR: 'gv2#' + hashlib.sha256(hash_src).hexdigest()}


def _MainRoHash(image):
  """Algorithm: sha256(fmap, RO_SECTION[-GBB])."""
  hash_src = image.get_fmap_blob()
  gbb = image.get_section('GBB')
  zero_gbb = chr(0) * len(gbb)
  image.put_section('GBB', zero_gbb)
  hash_src += image.get_section('RO_SECTION')
  image.put_section('GBB', gbb)
  # pylint: disable=E1101
  return {
      'hash': hashlib.sha256(hash_src).hexdigest(),
      'version': _AddFirmwareIdTag(image).lstrip('#'),
      COMPACT_PROBE_STR: 'mv2#%s%s' % (hashlib.sha256(hash_src).hexdigest(),
                                           _AddFirmwareIdTag(image))}


def _EcRoHash(image):
  """Algorithm: sha256(fmap, EC_RO)."""
  hash_src = image.get_fmap_blob()
  hash_src += image.get_section('EC_RO')
  # pylint: disable=E1101
  return {
      'hash': hashlib.sha256(hash_src).hexdigest(),
      'version': _AddFirmwareIdTag(image).lstrip('#'),
      COMPACT_PROBE_STR: 'ev2#%s%s' % (hashlib.sha256(hash_src).hexdigest(),
                                           _AddFirmwareIdTag(image))}


def _FwKeyHash(main_fw_file, key_name):
  """Hash specified GBB key, extracted by vbutil_key."""
  known_hashes = {
      'b11d74edd286c144e1135b49e7f0bc20cf041f10': 'devkeys/rootkey',
      'c14bd720b70d97394257e3e826bd8f43de48d4ed': 'devkeys/recovery',
  }
  with NamedTemporaryFile(prefix='gbb_%s_' % key_name) as f:
    if not Shell('gbb_utility -g --%s=%s %s' %
                 (key_name, f.name, main_fw_file)).success:
      raise Error('cannot get %s from GBB' % key_name)
    key_info = Shell('vbutil_key --unpack %s' % f.name).stdout
    sha1sum = re.findall(r'Key sha1sum:[\s]+([\w]+)', key_info)
    if len(sha1sum) != 1:
      logging.error("Failed calling vbutil_key for firmware key hash.")
      return None
    sha1 = sha1sum[0]
    if sha1 in known_hashes:
      sha1 += '#' + known_hashes[sha1]
    return {COMPACT_PROBE_STR: 'kv3#' + sha1}


def CalculateFirmwareHashes(fw_file_path):
  """Calculate the volatile hashes corresponding to a firmware blob.

  Given a firmware blob, determine what kind of firmware it is based
  on what sections are present.  Then generate a dict containing the
  corresponding hash values.
  """
  raw_image = open(fw_file_path, 'rb').read()
  try:
    image = crosfw.FirmwareImage(raw_image)
  except:  # pylint: disable=W0702
    return None
  hashes = {}
  if image.has_section('EC_RO'):
    hashes['ro_ec_firmware'] = _EcRoHash(image)
  elif image.has_section('GBB') and image.has_section('RO_SECTION'):
    hashes['hash_gbb'] = _GbbHash(image)
    hashes['ro_main_firmware'] = _MainRoHash(image)
    hashes['key_recovery'] = _FwKeyHash(fw_file_path, 'recoverykey')
    hashes['key_root'] = _FwKeyHash(fw_file_path, 'rootkey')
  return hashes


def ReadVpd(fw_image_file, kind):
  raw_vpd_data = Shell('vpd -i %s -l -f %s' % (kind, fw_image_file)).stdout
  return ParseKeyValueData('"(.*)"="(.*)"$', raw_vpd_data)


def ReadRoVpd(fw_image_file):
  return ReadVpd(fw_image_file, 'RO_VPD')


def ReadRwVpd(fw_image_file):
  return ReadVpd(fw_image_file, 'RW_VPD')


def Probe(target_comp_classes=None,
          fast_fw_probe=False,
          probe_volatile=True,
          probe_initial_config=True,
          probe_vpd=False):
  """Return device component, hash, and initial_config data.

  Run all of the available probing routines that make sense for the
  target architecture, for example if the machine being probed is x86
  then somewhat different probes would be run than for an ARM machine.

  All probe results are returned directly, without analysis.  Matching
  these results against the component database or against HWID data
  can be done afterwards.

  Args:
    component_classes: Which component classes to probe for.  A None
      value implies all classes.
    fast_fw_probe: Do a fast probe for EC and main firmware version. Setting
      this to True implies probe_volatile = False and probe_initial_config =
      False.
    probe_volatile: On False, do not probe for volatile data and
      return None for the corresponding field.
    probe_initial_config: On False, do not probe for initial_config
      data and return None for the corresponding field.
    probe_vpd: On True, include vpd data in the volatiles (handy for use with
      'gooftool verify_hwid --probe_results=...').
  Returns:
    Obj with components, volatile, and initial_config fields, each
    containing the corresponding dict of probe results.
  """
  if os.path.exists(FAKE_PROBE_RESULTS_FILE):
    # Overriding with results from a file (for testing).
    with open(FAKE_PROBE_RESULTS_FILE) as f:
      logging.warning('Using fake probe results in %s',
                      FAKE_PROBE_RESULTS_FILE)
      return ProbeResults.Decode(f)

  def RunProbe(probe_fun):
    try:
      return probe_fun()
    except Exception:  # pylint: disable=W0703
      logging.exception('Probe %r FAILED (see traceback), returning None.',
                        probe_fun.__name__)
      return None
  def FilterProbes(ref_probe_map, arch, probe_class_white_list):
    generic_probes = ref_probe_map.get(None, {})
    arch_probes = ref_probe_map.get(arch, {})
    if probe_class_white_list is None:
      probe_class_white_list = set(generic_probes) | set(arch_probes)
    return dict((probe_class, (arch_probes[probe_class]
                               if probe_class in arch_probes
                               else generic_probes[probe_class]))
                for probe_class in sorted(probe_class_white_list)
                if probe_class not in (
                    'ro_ec_firmware', 'ro_main_firmware', 'hash_gbb',
                    'key_recovery', 'key_root'))
  arch = Shell('crossystem arch').stdout.strip()
  comp_probes = FilterProbes(_COMPONENT_PROBE_MAP, arch, target_comp_classes)

  initial_configs = {}
  volatiles = {}
  if fast_fw_probe:
    volatiles['ro_ec_firmware'] = {'version': system.GetBoard().GetECVersion()}
    volatiles['ro_main_firmware'] = {
        'version': system.GetBoard().GetMainFWVersion()}
    probe_volatile = False
    probe_initial_config = False

  if probe_initial_config:
    ic_probes = FilterProbes(_INITIAL_CONFIG_PROBE_MAP, arch, None)
  else:
    ic_probes = {}
  found_probe_value_map = {}
  missing_component_classes = []
  for comp_class, probe_fun in comp_probes.items():
    probe_values = RunProbe(probe_fun)
    if not probe_values:
      missing_component_classes.append(comp_class)
    elif len(probe_values) == 1:
      found_probe_value_map[comp_class] = probe_values.pop()
    else:
      found_probe_value_map[comp_class] = sorted(probe_values)
  for ic_class, probe_fun in ic_probes.items():
    probe_value = RunProbe(probe_fun)
    if probe_value is not None:
      initial_configs[ic_class] = probe_value

  if probe_volatile:
    main_fw_file = crosfw.LoadMainFirmware().GetFileName()
    volatiles.update(CalculateFirmwareHashes(main_fw_file))
    ec_fw_file = crosfw.LoadEcFirmware().GetFileName()
    if ec_fw_file is not None:
      volatiles.update(CalculateFirmwareHashes(ec_fw_file))

  if probe_vpd:
    image_file = crosfw.LoadMainFirmware().GetFileName()
    for which, vpd in (('ro', ReadRoVpd(image_file)),
                       ('rw', ReadRwVpd(image_file))):
      for k, v in sorted(vpd.items()):
        volatiles['vpd.%s.%s' % (which, k)] = v
  return ProbeResults(
    found_probe_value_map=found_probe_value_map,
    missing_component_classes=missing_component_classes,
    found_volatile_values=volatiles,
    initial_configs=initial_configs)
