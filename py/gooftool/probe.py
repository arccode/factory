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

from __future__ import print_function

import collections
import hashlib
import logging
import os
import re
import string  # pylint: disable=W0402
import struct
import subprocess
import sys

from array import array
from glob import glob
from fcntl import ioctl
from tempfile import NamedTemporaryFile

import factory_common  # pylint: disable=W0611

from cros.factory.gooftool import edid
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import vblock
from cros.factory.gooftool.common import Shell
# pylint: disable=E0611
from cros.factory.hwid.v2.hwid_tool import ProbeResults, COMPACT_PROBE_STR
from cros.factory.test.l10n import regions
from cros.factory.utils import process_utils
from cros.factory.utils.type_utils import Error
from cros.factory.utils.type_utils import Obj


try:
  sys.path.append('/usr/local/lib/flimflam/test')
  import flimflam  # pylint: disable=F0401
except:  # pylint: disable=W0702
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


def CompactStr(data):
  """Converts data to string with compressed white space.

  Args:
    data: Single string or a list/tuple of strings.

  Returns:
    If data is a string, compress all contained contiguous spaces to
    single spaces.  If data is a list or tuple, space-join and then
    treat like string input.
  """
  if isinstance(data, list) or isinstance(data, tuple):
    data = ' '.join(x for x in data if x)
  return re.sub(r'\s+', ' ', data).strip()


def DictCompactProbeStr(content):
  return {COMPACT_PROBE_STR: CompactStr(content)}


def ParseKeyValueData(pattern, data):
  """Converts structured text into a {(key, value)} dict.

  Args:
    pattern: A regex pattern to decode key/value pairs
    data: The text to be parsed.

  Returns:
    A { key: value, ... } dict.

  Raises:
    ValueError: When the input is invalid.
  """
  parsed_list = {}
  for line in data.splitlines():
    matched = re.match(pattern, line.strip())
    if not matched:
      raise ValueError('Invalid data: %s' % line)
    (name, value) = (matched.group(1), matched.group(2))
    if name in parsed_list:
      raise ValueError('Duplicate key: %s' % name)
    parsed_list[name] = value
  return parsed_list


def _ShellOutput(command, on_error=''):
  """Returns shell command output.

  When the execution failed, usually the caller would want either empty string
  or None. However because most probe results expect empty string (for schema
  validation), here we set default on_error to empty string ('').

  command: A shell command passed to Shell().
  on_error: What to return if execution failed, defaults to empty string.
  """
  result = Shell(command)
  return result.stdout.strip() if result.success else on_error


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
  all_fields_list = field_list + (optional_field_list or [])
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
  """Returns dict that contains the values of PCI.

  Args:
    path: Path used to search for PCI sysfs data.

  Returns:
    A dict that contains at least the value of PCI 'vendor', 'device', and
    'revision_id'. Returns None if the information cannot be found.
  """
  field_data = _ReadSysfsFields(path, ['vendor', 'device'])
  if field_data is None:
    return None
  # Add PCI 'revision_id' field
  pci_revision_id_offset = 0x08
  try:
    with open(os.path.join(path, 'config'), 'rb') as f:
      f.seek(pci_revision_id_offset)
      rev_byte = f.read(1)
    if len(rev_byte) == 1:
      field_data['revision_id'] = hex(ord(rev_byte))
  except IOError:
    logging.exception('Cannot read config in the sysfs: %s', path)
    return None
  field_data.update(DictCompactProbeStr([
      '%s:%s (rev %s)' % (field_data['vendor'].replace('0x', ''),
                          field_data['device'].replace('0x', ''),
                          field_data['revision_id'].replace('0x', ''))]))
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
  device_id = _ReadSysfsDeviceId(os.path.join(path, 'device'))
  if device_id:
    return device_id

  name_path = os.path.join(path, 'name')
  if os.path.exists(name_path):
    with open(name_path) as f:
      device_id = f.read().strip()
    if device_id:
      return DictCompactProbeStr(device_id.strip(chr(0)).split(chr(0)))

  return None


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


class _GobiDevices(object):
  """Wrapper around Gobi specific utility information."""
  # TODO(bhthompson): This will need to be rewritten when gobi-fw is
  # deprecated, see crbug.com/217324

  @classmethod
  def IsDeviceGobi(cls):
    """Return true if there is a Gobi modem, false if not."""
    for path in glob('/sys/class/net/*/device/uevent'):
      with open(path) as f:
        if 'DRIVER=gobi' in [x.strip() for x in f.readlines()]:
          return True
    return False

  @classmethod
  def ReadFirmwareList(cls):
    """Return a list of firmware tuples from the `gobi-fw list` command"""
    if not cls.IsDeviceGobi():
      return None
    firmwares = []
    Firmware = collections.namedtuple('Firmware', 'attrs active build_id '
                                      'carrier')
    # Split utility output into a list and remove the legend and last newline.
    # The attrs field consists of some/all of the characters AIPM from the
    # gobi-fw utility 'Legend: A available I installed P pri M modem * active'
    # We separate out the * for active as it is an initial configuration,
    # modifiable by the user or tests to enable different carriers/regions.
    for l in _ShellOutput('gobi-fw list').splitlines()[1:]:
      m = re.match(r'^([A ][I ][P ][M ])([* ]) (\S+)\s+(.+)$', l)
      if not m:
        raise ValueError('Unable to parse line %r in gobi-fw output' % l)
      firmwares.append(Firmware(m.group(1), m.group(2) != ' ', m.group(3),
                                m.group(4)))
    return firmwares

  @classmethod
  def ActiveFirmware(cls):
    """Return the string of the active firmware (build_id for Gobi)."""
    if not cls.IsDeviceGobi():
      return None
    firmwares = cls.ReadFirmwareList()
    active_firmwares = [fw.build_id for fw in firmwares if fw.active]
    active_firmware = active_firmwares[0] if active_firmwares else None
    return active_firmware

class _NetworkDevices(object):
  """A general probing module for network devices."""

  cached_dev_list = None

  @classmethod
  def _GetIwconfigDevices(cls, extension='IEEE 802.11'):
    """Wrapper around iwconfig(8) information.

    Example output:

    eth0    no wireless extensions.

    wlan0   IEEE 802.11abgn ESSID:off/any
            Mod:Managed Access Point: Not-Associated Tx-Power=20 dBm
            ...

    Returns a list of network objects having WiFi extension.
    """
    return [Obj(devtype='wifi',
                path='/sys/class/net/%s/device' % node.split()[0])
            for node in _ShellOutput('iwconfig').splitlines()
            if extension in node]

  @classmethod
  def _GetIwDevices(cls, iw_type='managed'):
    """Wrapper around iw(8) information.

    Command 'iw' explicitly said "Do NOT screenscrape this tool" but we have no
    any better solutions. A typical output for 'iw dev' on mwifiex:

    phy#0
          Interface p2p0
                  ifindex 4
                  wdev 0x3
                  addr 28:c2:dd:45:94:39
                  type P2P-client
          Interface uap0
                  ifindex 3
                  wdev 0x2
                  addr 28:c2:dd:45:94:39
                  type AP
          Interface mlan0
                  ifindex 2
                  wdev 0x1
                  addr 28:c2:dd:45:94:39
                  type managed

    p2p0 and uap0 are virtual nodes and what we really want is mlan0 (managed).

    Returns:
      A list of network objects with correct iw type.
    """
    data = [line.split()[1] for line in _ShellOutput('iw dev').splitlines()
            if ' ' in line and line.split()[0] in ['Interface', 'type']]
    i = iter(data)
    return [Obj(devtype='wifi', path='/sys/class/net/%s/device' % name)
            for name in i if i.next() == iw_type]

  @classmethod
  def _GetFlimflamDevices(cls):
    """Wrapper around flimflam (shill), the ChromeOS connection manager.

    This object is a wrapper around the data from the flimflam module, providing
    dbus format post processing.

    Returns:
      A list of network objects in Obj, having:
        devtype: A string in flimflam Type (wifi, cellular, ethernet).
        path: A string for /sys node device path.
        attributes: A dictionary for additional attributes.
    """
    def _ProcessDevice(device):
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
            if 'Cellular.%s' % key in properties)
      return result

    return [_ProcessDevice(device) for device in
            flimflam.FlimFlam().GetObjectList('Device')]

  @classmethod
  def GetDevices(cls, devtype):
    """Returns network device information by given type.

    Returned data is a list of Objs corresponding to detected devices.
    Each has devtype (in same way as flimflam type classification) and path
    (location of related data in sysfs) fields.  For cellular devices, there is
    also an attributes field which contains a dict of attribute:value items.
    """
    if cls.cached_dev_list is None:
      dev_list = cls._GetFlimflamDevices()

      # On some Brillo (AP-type) devices, WiFi interfaces are blacklisted by
      # shill and needs to be discovered manually, so we have to try 'iw config'
      # or 'iw dev' to get a more correct list.
      # 'iwconfig' is easier to parse, but for some WiFi drivers, for example
      # mwifiex, do not support wireless extensions and only provide the new
      # CFG80211/NL80211. Also mwifiex will create two more virtual nodes 'uap0,
      # p2p0' so we can't rely on globbing /sys/class/net/*/wireless. The only
      # solution is to trust 'iw dev'.

      existing_nodes = [dev.path for dev in dev_list]
      dev_list += [dev for dev in cls._GetIwconfigDevices()
                   if dev.path not in existing_nodes]

      existing_nodes = [dev.path for dev in dev_list]
      dev_list += [dev for dev in cls._GetIwDevices()
                   if dev.path not in existing_nodes]

      cls.cached_dev_list = dev_list

    return [dev for dev in cls.cached_dev_list if dev.devtype == devtype]

  @classmethod
  def ReadSysfsDeviceIds(cls, devtype, ignore_usb=False):
    """Return _ReadSysfsDeviceId result for each device of specified type."""
    ids = [_ReadSysfsDeviceId(dev.path, ignore_usb)
           for dev in cls.GetDevices(devtype)]
    # Filter out 'None' results
    return sorted(device for device in ids if device is not None)


class _InputDevices(object):
  """Parses /proc/bus/input/devices and turns into a key-value dataset."""

  def __init__(self, path='/proc/bus/input/devices'):
    dataset = []
    data = {}
    entry = None
    with open(path) as f:
      for line in f:
        prefix = line[0]
        content = line[3:].strip()
        # Format: PREFIX: Key=Value
        #  I: Bus=HHHH Vendor=HHHH Product=HHHH Version=HHHH
        #  N: Name="XXXX"
        #  P: Phys=XXXX
        #  S: Sysfs=XXXX
        if prefix == 'I':
          if data:
            dataset.append(Obj(**data))
          data = {}
          for entry in content.split():
            key, value = entry.split('=', 1)
            data[key] = value
        elif prefix in ['N', 'S']:
          key, value = content.split('=', 1)
          data[key] = value.strip('"')

      # Flush output
      if data:
        dataset.append(Obj(**data))
    self._dataset = dataset

  def FindByNamePattern(self, regex):
    """Finds devices by given regular expression."""
    return [data for data in self._dataset if re.match(regex, data.Name)]


class _TouchInputData(object):  # pylint: disable=W0232
  """Base class for collecting touchpad and touchscreen information."""

  @classmethod
  def GenericInput(cls, name_pattern, sysfs_files=None, filter_rule=None):
    """A generic touch device resolver."""
    input_devices = _InputDevices()
    data = input_devices.FindByNamePattern(name_pattern)

    if filter_rule:
      data = [entry for entry in data if filter_rule(entry)]

    if not data:
      return None

    # TODO(hungte) Should we support multiple components in future?
    if len(data) > 1:
      logging.warning('TouchInputData: multiple components matched for %s: %s',
                      name_pattern, data)

    entry = data[0]
    result = {'ident_str': entry.Name}

    # Ignore Linux dummy ID (0).
    if int(entry.Vendor, 16):
      result['vendor_id'] = entry.Vendor
      result['product_id'] = entry.Product
    if int(entry.Version, 16):
      result['version'] = entry.Version

    # Find out more information from sysfs.
    for name in sysfs_files or []:
      # entry.Sysfs starts with '/' and ends at input node, for example:
      # /devices/pci0000:00/0000:00:02.0/i2c-2/2-004a/input/input7
      path = os.path.join('/sys', entry.Sysfs.lstrip('/'), 'device', name)
      if not os.path.exists(path):
        continue
      with open(path) as f:
        result[name] = f.read().strip()

    return Obj(**result)

  @classmethod
  def SynapticsInput(cls, name_pattern, sysfs_files=None):
    data = cls.GenericInput(name_pattern, sysfs_files,
                            filter_rule=lambda e: e.Vendor == '06cb')
    if not data:
      return None

    rmi4update_program = '/usr/sbin/rmi4update'
    if not os.path.exists(rmi4update_program):
      return data

    devs = glob(os.path.join('/sys/bus/hid/devices/', '*:%s:%s.*'
                             % (data.vendor_id.upper(), data.product_id.upper()),
                             'hidraw/hidraw*'))
    if not devs:
      return data

    hidraw_dev = '/dev/' + devs[0].split('/')[-1]

    result = Shell(rmi4update_program + ' -p -d ' + hidraw_dev)
    if not result.success:
      return data

    data.fw_version = result.stdout.strip()
    return data

class _TouchpadData(_TouchInputData):
  """Return Obj with hw_ident and fw_ident string fields."""

  @classmethod
  def Synaptics(cls):

    def SynapticsSyndetect():
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

    def SynapticsByName():
      return cls.SynapticsInput(r'^SYNA.*', ['fw_version'])

    return SynapticsSyndetect() or SynapticsByName()

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
  def Elan(cls):
    for driver_link in glob('/sys/bus/i2c/drivers/elan_i2c/*'):
      if not os.path.islink(driver_link):
        continue

      with open(os.path.join(driver_link, 'name'), 'r') as f:
        name = f.read().strip()
      with open(os.path.join(driver_link, 'product_id'), 'r') as f:
        product_id = f.read().strip()
      with open(os.path.join(driver_link, 'firmware_version'), 'r') as f:
        firmware_version = f.read().strip()
      with open(os.path.join(driver_link, 'fw_checksum'), 'r') as f:
        fw_checksum = f.read().strip()
      return Obj(ident_str=name, product_id=product_id,
                 fw_version=firmware_version, fw_csum=fw_checksum)
    return None

  @classmethod
  def Generic(cls):
    return cls.GenericInput(r'.*[Tt](?:ouch|rack) *[Pp]ad',
                            ['fw_version', 'hw_version', 'config_csum'])

  @classmethod
  def HidOverI2c(cls):
    # Since hid-over-i2c support many classes of devices,
    # no good method to differentiate touchpad/touchscreen .. from others.
    # so we use a list of tuple [("vendor id","product id"),...] to list
    # all known touchpad here so that we can report touchpad info correctly.
    # ("06cb","7a3b") is synaptics hid-over-i2c touchpad.
    known_list = [
        '06cb:7a3b',  # Synaptics hid-over-i2c touchpad.
    ]
    def in_known_list(entry):
      return '%s:%s' % (entry.Vendor, entry.Product) in known_list
    return cls.GenericInput(r'hid-over-i2c.*', filter_rule=in_known_list)

  cached_data = None

  @classmethod
  def Get(cls):
    if cls.cached_data is None:
      cls.cached_data = Obj(ident_str=None)
      for vendor_fun in [cls.Cypress, cls.Synaptics, cls.Elan,
                         cls.HidOverI2c, cls.Generic]:
        data = vendor_fun()
        if data is not None:
          cls.cached_data = data
          break
    return cls.cached_data


class _TouchscreenData(_TouchInputData):  # pylint: disable=W0232
  """Return Obj with hw_ident and fw_ident string fields."""

  @classmethod
  def Elan(cls):
    for device_path in glob('/sys/bus/i2c/devices/*'):
      driver_link = os.path.join(device_path, 'driver')
      if not os.path.islink(driver_link):
        continue
      driver_name = os.path.basename(os.readlink(driver_link))
      if driver_name != 'elants_i2c':
        continue

      with open(os.path.join(device_path, 'name'), 'r') as f:
        device_name = f.read().strip()
      with open(os.path.join(device_path, 'hw_version'), 'r') as f:
        hw_version = f.read().strip()
      with open(os.path.join(device_path, 'fw_version'), 'r') as f:
        fw_version = f.read().strip()
      return Obj(ident_str=device_name, hw_version=hw_version,
                 fw_version=fw_version)
    return None

  @classmethod
  def Synaptics(cls):
    return cls.SynapticsInput(r'SYTS.*', ['fw_version'])
  @classmethod
  def Generic(cls):
    return cls.GenericInput(r'.*[Tt]ouch *[Ss]creen',
                            ['fw_version', 'hw_version', 'config_csum'])

  cached_data = None

  @classmethod
  def Get(cls):
    if cls.cached_data is None:
      cls.cached_data = Obj(ident_str=None)
      for vendor_fun in [cls.Elan, cls.Synaptics, cls.Generic]:
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
    probe_class: Probe class for which the probe fun produces results.
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
  """Looks for codec strings.

  Collect /sys/kernel/debug/asoc/codecs for ASOC (ALSA
  SOC) drivers, /proc/asound for HDA codecs, then PCM details.

  There is a set of known invalid codec names that are not included in the
  return value.
  """
  KNOWN_INVALID_CODEC_NAMES = set([
      'snd-soc-dummy',
      'ts3a227e.4-003b',  # autonomous audiojack switch, not an audio codec
      'dw-hdmi-audio'  # this is a virtual audio codec driver
      ])
  asoc_path = '/sys/kernel/debug/asoc/codecs'
  if os.path.exists(asoc_path):
    with open(asoc_path) as f:
      results = [DictCompactProbeStr(codec) for codec in f.read().splitlines()
                 if codec not in KNOWN_INVALID_CODEC_NAMES]
  else:
    results = []

  grep_result = _ShellOutput('grep -R "Codec:" /proc/asound/*')
  match_set = set()
  for line in grep_result.splitlines():
    match_set |= set(re.findall(r'.*Codec:(.*)', line))
  results += [DictCompactProbeStr(match) for match in sorted(match_set) if
              match]
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


def _GetV4L2Data(video_idx):
  # Get information from video4linux2 (v4l2) interface.
  # See /usr/include/linux/videodev2.h for definition of these consts.
  # 'ident' values are defined in include/media/v4l2-chip-ident.h
  info = {}
  VIDIOC_DBG_G_CHIP_IDENT = 0xc02c5651
  V4L2_DBG_CHIP_IDENT_SIZE = 11
  V4L2_INDEX_REVISION = V4L2_DBG_CHIP_IDENT_SIZE - 1
  V4L2_INDEX_IDENT = V4L2_INDEX_REVISION - 1
  V4L2_VALID_IDENT = 3  # V4L2_IDENT_UNKNOWN + 1

  # Get v4l2 capability
  V4L2_CAPABILITY_FORMAT = '<16B32B32BII4I'
  V4L2_CAPABILITY_STRUCT_SIZE = struct.calcsize(V4L2_CAPABILITY_FORMAT)
  V4L2_CAPABILITIES_OFFSET = struct.calcsize(V4L2_CAPABILITY_FORMAT[0:-3])
  # struct v4l2_capability
  # {
  #   __u8  driver[16];
  #   __u8  card[32];
  #   __u8  bus_info[32];
  #   __u32 version;
  #   __u32 capabilities;  /* V4L2_CAPABILITIES_OFFSET */
  #   __u32 reserved[4];
  # };

  IOCTL_VIDIOC_QUERYCAP = 0x80685600

  # Webcam should have CAPTURE capability but no OUTPUT capability.
  V4L2_CAP_VIDEO_CAPTURE = 0x00000001
  V4L2_CAP_VIDEO_OUTPUT = 0x00000002

  # V4L2 encode/decode device should have the following capabilities.
  V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
  V4L2_CAP_VIDEO_OUTPUT_MPLANE = 0x00002000
  V4L2_CAP_STREAMING = 0x04000000
  V4L2_CAP_VIDEO_CODEC = (V4L2_CAP_VIDEO_CAPTURE_MPLANE |
                          V4L2_CAP_VIDEO_OUTPUT_MPLANE |
                          V4L2_CAP_STREAMING)

  def _TryIoctl(fileno, request, *args):
    """Try to invoke ioctl without raising an exception if it fails."""
    try:
      ioctl(fileno, request, *args)
    except:  # pylint: disable=W0702
      pass

  try:
    with open('/dev/video%d' % video_idx, 'r+') as f:
      # Read chip identifier.
      buf = array('i', [0] * V4L2_DBG_CHIP_IDENT_SIZE)
      _TryIoctl(f.fileno(), VIDIOC_DBG_G_CHIP_IDENT, buf, 1)
      v4l2_ident = buf[V4L2_INDEX_IDENT]
      if v4l2_ident >= V4L2_VALID_IDENT:
        info['ident'] = 'V4L2:%04x %04x' % (v4l2_ident,
                                            buf[V4L2_INDEX_REVISION])
      # Read V4L2 capabilities.
      buf = array('B', [0] * V4L2_CAPABILITY_STRUCT_SIZE)
      _TryIoctl(f.fileno(), IOCTL_VIDIOC_QUERYCAP, buf, 1)
      capabilities = struct.unpack_from('<I', buf, V4L2_CAPABILITIES_OFFSET)[0]
      if ((capabilities & V4L2_CAP_VIDEO_CAPTURE) and
          (not capabilities & V4L2_CAP_VIDEO_OUTPUT)):
        info['type'] = 'webcam'
      elif capabilities & V4L2_CAP_VIDEO_CODEC == V4L2_CAP_VIDEO_CODEC:
        info['type'] = 'video_codec'
  except:  # pylint: disable=W0702
    pass

  return info


@_ComponentProbe('video')
def _ProbeVideo():
  # TODO(tammo/sheckylin): Try to replace the code below with OpenCV calls.

  KNOWN_INVALID_VIDEO_IDS = set([])

  result = []
  for video_node in glob('/sys/class/video4linux/video*'):
    video_idx = re.search(r'video(\d+)$', video_node).group(1)

    info = {}
    video_data = _ReadSysfsNodeId(video_node)
    if video_data[COMPACT_PROBE_STR] in KNOWN_INVALID_VIDEO_IDS:
      continue

    if video_data:
      info.update(video_data)

    # Also check video max packet size
    video_max_packet_size = _ReadSysfsFields(
        os.path.join(video_node, 'device', 'ep_82'),
        ['wMaxPacketSize'])
    # We do not want to override compact_str in info
    if video_max_packet_size:
      info.update({'wMaxPacketSize': video_max_packet_size['wMaxPacketSize']})
    # For SOC videos
    video_data_soc = _ReadSysfsFields(video_node, ['device/control/name'])
    if video_data_soc:
      info.update(video_data_soc)
    # Get video4linux2 (v4l2) info.
    v4l2_data = _GetV4L2Data(int(video_idx))
    if v4l2_data:
      info.update(v4l2_data)

    result.append(info)
  return result


@_ComponentProbe('cellular')
def _ProbeCellular():
  # It is found that some cellular components may have their interface listed in
  # shill but not available from /sys (for example, shill Interface=no_netdev_23
  # but no /sys/class/net/no_netdev_23. Meanwhile, 'modem status' gives right
  # Device info like 'Device: /sys/devices/ff500000.usb/usb1/1-1'.
  # Unfortunately, information collected by shill, 'modem status', or the USB
  # node under Device are not always synced.
  data = (_NetworkDevices.ReadSysfsDeviceIds('cellular') or
          [dev.attributes for dev in _NetworkDevices.GetDevices('cellular')])
  if data:
    modem_status = _ShellOutput('modem status')
    for key in ['carrier', 'firmware_revision', 'Revision']:
      matches = re.findall(
          r'^\s*' + key + ': (.*)$', modem_status, re.M)
      if matches:
        data[0][key] = matches[0]
    # For some chipsets we can use custom utilities for more data
    if _GobiDevices.IsDeviceGobi():
      full_fw_string = []
      for fw in _GobiDevices.ReadFirmwareList():
        fw_string = '%s  %s %s' % (fw.attrs, fw.build_id, fw.carrier)
        full_fw_string.append(fw_string)
      data[0]['firmwares'] = ', '.join(full_fw_string)
      data[0]['active_firmware'] = str(_GobiDevices.ActiveFirmware())
  return data


@_ComponentProbe('wimax')
def _ProbeWimax():
  return _NetworkDevices.ReadSysfsDeviceIds('wimax')


@_ComponentProbe('display_converter')
def _ProbeDisplayConverter():
  """Try brand-specific probes, return the first viable result."""
  def ProbeChrontel():
    """Search style borrowed from the /etc/init/chrontel.conf behavior."""
    _LoadKernelModule('i2c_dev', error_on_fail=False)
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
  stdout = _ShellOutput(cmd).splitlines()
  return [{'model': stdout[0], 'cores': str(len(stdout)),
           COMPACT_PROBE_STR: CompactStr(
               '%s [%d cores]' % (stdout[0], len(stdout)))}]


@_ComponentProbe('cpu', 'arm')
def _ProbeCpuArm():
  """Reformat /proc/cpuinfo data."""
  # For platforms like arm, it sometimes gives the model name in 'Processor',
  # and sometimes in 'model name'. But they all give something like 'ARMv7
  # Processor rev 4 (v71)' only. So to uniquely identify an ARM CPU, we should
  # use the 'Hardware' field.
  with open('/proc/cpuinfo') as f:
    cpuinfo = f.read()
    try:
      model = re.search(r'^(?:Processor|model name)\s*: (.*)$',
                        cpuinfo, re.MULTILINE).group(1)
    except AttributeError:
      model = 'unknown'
      logging.error("Unable to find 'Processor' or 'model name' field in "
                    "/proc/cpuinfo, can't determine CPU model.")
    try:
      hardware = re.search(r'^Hardware\s*: (.*)$',
                           cpuinfo, re.MULTILINE).group(1)
    except AttributeError:
      hardware = 'unknown'
      logging.error("Unable to find 'Hardware' field in /proc/cpuinfo, "
                    "can't determine CPU hardware.")
  cores = 0
  while os.path.exists('/sys/devices/system/cpu/cpu%s' % cores):
    cores += 1
  return [{'model': model, 'cores': str(cores), 'hardware': hardware,
           COMPACT_PROBE_STR: CompactStr(
               '%s [%d cores] %s' % (model, cores, hardware))}]


@_ComponentProbe('customization_id')
def _ProbeCustomizationId():
  """Probes the customization_id of the DUT in RO VPD."""
  customization_id = ReadRoVpd().get('customization_id', None)
  return [{'id': customization_id}] if customization_id else []


@_ComponentProbe('display_panel')
def _ProbeDisplayPanel():
  """Combine all available edid data, from sysfs and directly from the i2c."""
  edid_list = []
  glob_list = [
      '/sys/class/drm/*LVDS*/edid',
      '/sys/kernel/debug/edid*',
  ]
  path_list = []
  for path in glob_list:
    path_list += glob(path)
  for path in path_list:
    with open(path) as f:
      parsed_edid = edid.Parse(f.read())
      if parsed_edid:
        edid_list.append(parsed_edid)
  _LoadKernelModule('i2c_dev', error_on_fail=False)
  for path in sorted(glob('/dev/i2c-[0-9]*')):
    parsed_edid = edid.LoadFromI2c(path)
    if parsed_edid:
      edid_list.append(parsed_edid)
  return edid_list


@_ComponentProbe('dram')
def _ProbeDram():
  """Combine mosys memory timing and geometry information."""
  # TODO(tammo): Document why mosys cannot load i2c_dev itself.
  _LoadKernelModule('i2c_dev', error_on_fail=False)
  part_data = _ShellOutput('mosys -k memory spd print id')
  timing_data = _ShellOutput('mosys -k memory spd print timings')
  size_data = _ShellOutput('mosys -k memory spd print geometry')
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
  ret = []
  ec_chip_id = crosfw.LoadEcFirmware().GetChipId()
  if ec_chip_id is not None:
    ret.append({COMPACT_PROBE_STR: ec_chip_id})
  pd_chip_id = crosfw.LoadPDFirmware().GetChipId()
  if pd_chip_id is not None:
    ret.append({COMPACT_PROBE_STR: pd_chip_id})
  return ret


@_ComponentProbe('embedded_controller')
def _ProbeEmbeddedController():
  """Reformat mosys output."""
  # Example mosys command output:
  # vendor="VENDOR" name="CHIPNAME" fw_version="ECFWVER"
  ret = []
  info_keys = ('vendor', 'name')
  for name in ('ec', 'pd'):
    try:
      ec_info = dict(
          (key, _ShellOutput(['mosys', name, 'info', '-s', key]))
          for key in info_keys)
      ec_info[COMPACT_PROBE_STR] = CompactStr(
          [ec_info[key] for key in info_keys])
    except subprocess.CalledProcessError:
      # The EC type is not supported on this board.
      pass
    else:
      ret.append(ec_info)
  return ret


@_ComponentProbe('power_mgmt_chip')
def _ProbePowerMgmtChip():
  tpschrome_ver = re.findall(
      r'Read from I2C port 0 at 0x90 offset 0x19 = (\w+)',
      _ShellOutput('ectool i2cread 8 0 0x90 0x19'))
  if not tpschrome_ver:
    return []
  return [{'tpschrome_ver': tpschrome_ver[0],
           COMPACT_PROBE_STR: tpschrome_ver[0]}]


@_ComponentProbe('ethernet')
def _ProbeEthernet():
  # Build-in ethernet devices should not be attached to USB. They are usually
  # either PCI or SOC.
  return _NetworkDevices.ReadSysfsDeviceIds('ethernet', ignore_usb=True)


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
    if re.match(r'^loop|^dm-', os.path.basename(node)):
      # Loopback or dm-verity device; skip
      continue

    ret.append(node)

  return ret


def _GetEMMC5FirmwareVersion(node_path):
  """Extracts eMMC 5.0 firmware version from EXT_CSD[254:261].

  Args:
    node_path: the node_path returned by _GetFixedDevices(). For example,
        '/sys/class/block/mmcblk0'.

  Returns:
    A string indicating the firmware version if firmware version is found.
    Return None if firmware version doesn't present.
  """
  ext_csd = process_utils.GetLines(Shell(
      'mmc extcsd read /dev/%s' % os.path.basename(node_path)).stdout)
  # The output for firmware version is encoded by hexdump of a ASCII
  # string or hexdump of hexadecimal values, always in 8 characters.
  # For example, version 'ABCDEFGH' is:
  # [FIRMWARE_VERSION[261]]: 0x48
  # [FIRMWARE_VERSION[260]]: 0x47
  # [FIRMWARE_VERSION[259]]: 0x46
  # [FIRMWARE_VERSION[258]]: 0x45
  # [FIRMWARE_VERSION[257]]: 0x44
  # [FIRMWARE_VERSION[256]]: 0x43
  # [FIRMWARE_VERSION[255]]: 0x42
  # [FIRMWARE_VERSION[254]]: 0x41
  #
  # Some vendors might use hexadecimal values for it.
  # For example, version 3 is:
  # [FIRMWARE_VERSION[261]]: 0x00
  # [FIRMWARE_VERSION[260]]: 0x00
  # [FIRMWARE_VERSION[259]]: 0x00
  # [FIRMWARE_VERSION[258]]: 0x00
  # [FIRMWARE_VERSION[257]]: 0x00
  # [FIRMWARE_VERSION[256]]: 0x00
  # [FIRMWARE_VERSION[255]]: 0x00
  # [FIRMWARE_VERSION[254]]: 0x03
  #
  # To handle both cases, this function returns a 64-bit hexadecimal value
  # and will try to decode it as a ASCII string or as a 64-bit little-endian
  # integer. It returns '4142434445464748 (ABCDEFGH)' for the first example
  # and returns '0300000000000000 (3)' for the second example.

  pattern = re.compile(r'^\[FIRMWARE_VERSION\[(\d+)\]\]: (.*)$')
  data = dict(m.groups() for m in map(pattern.match, ext_csd) if m)
  if not data:
    return None

  raw_version = [int(data[str(i)], 0) for i in range(254, 262)]
  version = ''.join(('%02x' % c for c in raw_version))

  # Try to decode it as a ASCII string.
  # Note vendor may choose SPACE (0x20) or NUL (0x00) to pad version string,
  # so we want to strip both in the human readable part.
  ascii = ''.join(map(chr, raw_version)).strip(' \0')
  if len(ascii) > 0 and all(c in string.printable for c in ascii):
    version += ' (%s)' % ascii
  else:
    # Try to decode it as a 64-bit little-endian integer.
    version += ' (%s)' % struct.unpack_from('<q', version.decode('hex'))
  return version


@_ComponentProbe('region')
def _ProbeRegion():
  """Probes the region of the DUT based on the region field in RO VPD."""
  region_code = ReadRoVpd().get('region', None)
  if region_code:
    region_obj = regions.REGIONS[region_code]
    ret = [{'region_code': region_obj.region_code,}]
  else:
    ret = []

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
    optional_fields = ['cid', 'prv']
    data = (_ReadSysfsFields(dev_path, ata_fields) or
            _ReadSysfsFields(dev_path, emmc_fields, optional_fields) or
            None)
    if not data:
      return None
    emmc5_fw_ver = _GetEMMC5FirmwareVersion(node_path)
    if emmc5_fw_ver is not None:
      data['emmc5_fw_ver'] = emmc5_fw_ver
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
  for key in ('product_id', 'vendor_id', 'version', 'fw_version', 'hw_version',
              'fw_csum', 'config_csum'):
    value = getattr(data, key, '')
    if value:
      results[key] = value
  return [results]


@_ComponentProbe('touchscreen')
def _ProbeTouchscreen():
  data = _TouchscreenData.Get()
  if data.ident_str is None:
    return []

  results = {'id': data.ident_str}
  results.update(DictCompactProbeStr(data.ident_str))
  for key in ('product_id', 'vendor_id', 'version', 'fw_version', 'hw_version',
              'fw_csum', 'config_csum'):
    value = getattr(data, key, '')
    if value:
      results[key] = value
  return [results]


@_ComponentProbe('tpm')
def _ProbeTpm():
  """Return Manufacturer_info : Chip_Version string from tpm_version output."""
  tpm_data = [line.partition(':') for line in
              _ShellOutput('tpm_version').splitlines()]
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
  arch = _ShellOutput('crossystem arch')
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
  return _NetworkDevices.ReadSysfsDeviceIds('wifi')


@_ComponentProbe('pmic')
def _ProbePmic():
  pmics = glob('/sys/bus/platform/devices/*-pmic')
  return ([{COMPACT_PROBE_STR: os.path.basename(x)} for x in pmics]
          if pmics else [])


@_ComponentProbe('board_version')
def _ProbeBoardVersion():
  result = Shell('mosys platform version')
  board_version = result.stdout.strip() if result.success else None
  if board_version is None:
    return []
  else:
    return [{COMPACT_PROBE_STR: board_version}]


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
    modem_status = _ShellOutput(cmd)
    info = re.findall(r'^\s*firmware_revision:\s*(.*)', modem_status)
    if info and info[0]:
      return info[0]
    return None
  results = [GetVersionString(dev.attributes) for dev in
             _NetworkDevices.GetDevices('cellular')]
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
  touchdata = _TouchpadData.Get()
  return touchdata.__dict__.get('fw_version')


@_InitialConfigProbe('storage_fw_version')
def _ProbeStorageFirmwareVersion():
  """Returns firmware rev for all fixed devices."""
  ret = []
  for f in _GetFixedDevices():
    smartctl = Shell('smartctl --all %s' %
                     os.path.join('/dev', os.path.basename(f))).stdout
    matches = re.findall(r'(?m)^Firmware Version:\s+(.+)$', smartctl)
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
      logging.error('Failed calling gbb_utility to calcuate GBB hash.')
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
    key_info = _ShellOutput('vbutil_key --unpack %s' % f.name)
    sha1sum = re.findall(r'Key sha1sum:[\s]+([\w]+)', key_info)
    if len(sha1sum) != 1:
      logging.error('Failed calling vbutil_key for firmware key hash.')
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


def ReadVpd(kind, fw_image_file=None):
  """Reads data from VPD.

  Args:
    kind: VPD section name to read.
    fw_image_file: A string for path to existing firmware image file. None to
        use the crosfw.LoadMainFirmware().

  Returns:
    A dictionary for the key-value pairs stored in VPD.
  """
  # Do not log command output since this will include private data such as
  # registration codes.
  if fw_image_file is None:
    fw_image_file = crosfw.LoadMainFirmware().GetFileName()

  raw_data = Shell('vpd -l -i %s -f %s' %
                   (kind, fw_image_file), log=False).stdout
  return ParseKeyValueData('"(.*)"="(.*)"$', raw_data)


def ReadRoVpd(fw_image_file=None):
  """Reads VPD data from RO section."""
  return ReadVpd('RO_VPD', fw_image_file)


def ReadRwVpd(fw_image_file=None):
  """Reads VPD data from RW section."""
  return ReadVpd('RW_VPD', fw_image_file)


def DeleteVpd(kind, keys):
  """Deletes VPD data by specified keys.

  Args:
    kind: The VPD section to select.
    keys: A list of VPD key names to delete.

  Returns:
    True if updated successfully, otherwise False.
  """
  command = 'vpd -i %s %s' % (
      kind, ' '.join('-d %s' % k for k in keys))
  return Shell(command).success


def UpdateVpd(kind, values):
  """Updates VPD data by given values.

  Args:
    kind: The VPD section to select.
    values: A dictionary containing VPD values to set.

  Returns:
    True if updated successfully,  otherwise False.
  """
  command = 'vpd -i %s %s' % (
      kind, ' '.join(('-s "%s"="%s"' % (k, v) for k, v in values.iteritems())))
  return Shell(command).success


def DeleteRoVpd(keys):
  """Deletes VPD data in read-only partition before write-protected."""
  return DeleteVpd('RO_VPD', keys)


def DeleteRwVpd(keys):
  """Deletes VPD data in read-write partition."""
  return DeleteVpd('RW_VPD', keys)


def UpdateRoVpd(values):
  """Changes VPD data in read-only partition before write-protected."""
  return UpdateVpd('RO_VPD', values)


def UpdateRwVpd(values):
  """Changes VPD data in read-write partition."""
  return UpdateVpd('RW_VPD', values)


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
    target_comp_classes: Which component classes to probe for.  A None
      value implies all classes.
    fast_fw_probe: Do a fast probe for EC and main firmware version. Setting
      this to True implies probe_volatile, probe_initial_config, probe_vpd,
      and all probing related to VPD (for example, region) are False.
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
                    'ro_ec_firmware', 'ro_pd_firmware', 'ro_main_firmware',
                    'hash_gbb', 'key_recovery', 'key_root'))
  arch = _ShellOutput('crossystem arch')
  comp_probes = FilterProbes(_COMPONENT_PROBE_MAP, arch, target_comp_classes)

  initial_configs = {}
  volatiles = {}

  if fast_fw_probe:
    logging.debug('fast_fw_probe enabled.')
    optional_fields = {
        'ro_ec_firmware': _ShellOutput('mosys ec info -s fw_version'),
        'ro_pd_firmware': _ShellOutput('mosys pd info -s fw_version')
    }
    for k, v in optional_fields.iteritems():
      if v:
        volatiles[k] = {'version': v}
    volatiles['ro_main_firmware'] = {
        'version': _ShellOutput('crossystem ro_fwid')}
    probe_volatile = False
    probe_initial_config = False
    probe_vpd = False

  if probe_initial_config:
    ic_probes = FilterProbes(_INITIAL_CONFIG_PROBE_MAP, arch, None)
  else:
    ic_probes = {}
  found_probe_value_map = {}
  missing_component_classes = []
  # TODO(hungte) Extend _ComponentProbe to support filtering flashrom related
  # probing methods.
  vpd_classes = ['region', 'customization_id']
  for comp_class, probe_fun in comp_probes.items():
    if comp_class in vpd_classes and not probe_vpd:
      logging.info('Ignored probing [%s]', comp_class)
      continue
    logging.info('probing [%s]...', comp_class)
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
    pd_fw_file = crosfw.LoadPDFirmware().GetFileName()
    if pd_fw_file is not None:
      # Currently PD is using same FMAP layout as EC so we have to rename
      # section name to avoid conflict.
      hashes = CalculateFirmwareHashes(pd_fw_file)
      volatiles.update({'ro_pd_firmware': hashes['ro_ec_firmware']})

  if probe_vpd:
    for which, vpd_field in (('ro', ReadRoVpd()),
                             ('rw', ReadRwVpd())):
      for k, v in sorted(vpd_field.items()):
        volatiles['vpd.%s.%s' % (which, k)] = v
  return ProbeResults(
      found_probe_value_map=found_probe_value_map,
      missing_component_classes=missing_component_classes,
      found_volatile_values=volatiles,
      initial_configs=initial_configs)
