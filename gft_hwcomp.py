#!/usr/bin/python
#
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import pprint
import re
import sys

import flashrom_util
import gft_common
import gft_fwhash
import vblock

from gft_common import DebugMsg, VerboseMsg, WarningMsg, ErrorMsg, ErrorDie


def Memorize(f):
  """ Decorator for functions that need memorization."""
  memorize_data = {}
  def memorize_call(*args):
    index = repr(args)
    if index in memorize_data:
      value = memorize_data[index]
      # DebugMsg('Memorize: using cached value for: %s %s' % (repr(f), index))
      return value
    value = f(*args)
    memorize_data[index] = value
    return value
  return memorize_call


class HardwareComponents(object):
  """ Hardware Components Scanner """

  # Function names in this class are used for reflection, so please don't change
  # the function names even if they are not comliant to coding style guide.

  version = 3

  # We divide all component IDs (cids) into 5 categories:
  #  - enumerable: able to get the results by running specific commands;
  #  - PCI: PCI devices;
  #  - USB: USB devices;
  #  - probable: returns existed or not by given some pre-defined choices;
  #  - pure data: data for some special purpose, can't be tested;

  _enumerable_cids = [
    'data_display_geometry',
    'hash_ec_firmware',
    'hash_ro_firmware',
    'part_id_audio_codec',
    'part_id_cpu',
    'part_id_display_panel',
    'part_id_dram',
    'part_id_embedded_controller',
    'part_id_ethernet',
    'part_id_flash_chip',
    'part_id_ec_flash_chip',
    'part_id_hwqual',
    'part_id_storage',
    'part_id_tpm',
    'part_id_wireless',
    'vendor_id_touchpad',
    'version_rw_firmware',
    ]
  _pci_cids = [
    'part_id_chipset',
    'part_id_usb_hosts',
    'part_id_vga',
    ]
  _usb_cids = [
    'part_id_bluetooth',
    'part_id_webcam',
    'part_id_3g',
    'part_id_gps',
    ]
  _probable_cids = [
    'key_recovery',
    'key_root',
    'part_id_cardreader',
    'part_id_chrontel',
    ]
  _pure_data_cids = [
    'data_bitmap_fv',
    'data_recovery_url',
    ]

  # _not_test_cids and _to_be_tested_cids will be re-created for each match.
  _not_test_cids = []
  _to_be_tested_cids = []

  # TODO(hungte) unify the 'not available' style messages
  _not_present = 'Not Present'
  _no_match = 'No match'

  def __init__(self, verbose=False):
    self._initialized = False
    self._verbose = verbose
    self._pp = pprint.PrettyPrinter()

    # cache for firmware images
    self._flashrom = flashrom_util.flashrom_util(
        verbose_msg=VerboseMsg,
        exception_type=gft_common.GFTError,
        system_output=gft_common.SystemOutput)
    self._temp_files = []

    # variables for matching
    self._enumerable_system = None
    self._pci_system = None
    self._usb_system = None
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

  def get_all_enumerable_components(self):
    results = {}
    for cid in self._enumerable_cids:
      if self._verbose:
        sys.stdout.flush()
        sys.stderr.write('<Fetching property %s>\n' % cid)
      components = self.force_get_property('get_' + cid)
      if not isinstance(components, list):
        components = [components]
      results[cid] = components
    return results

  def get_all_pci_components(self):
    cmd = 'lspci -n | cut -f3 -d" "'
    return gft_common.SystemOutput(cmd, progress_messsage='Probing PCI: ',
                                   show_progress=self._verbose).splitlines()

  def get_all_usb_components(self):
    cmd = 'lsusb | cut -f6 -d" "'
    return gft_common.SystemOutput(cmd, progress_messsage='Probing USB: ',
                                   show_progress=self._verbose).splitlines()

  @Memorize
  def load_module(self, name):
    grep_cmd = ('lsmod 2>/dev/null | grep -q %s' % name)
    loaded = (os.system(grep_cmd) == 0)
    if not loaded:
      if os.system('modprobe %s >/dev/null 2>&1' % name) != 0:
        ErrorMsg("Cannot load module: %s" % name)
    return loaded

  def check_enumerable_component(self, cid, exact_values, approved_values):
    if '*' in approved_values:
      return

    for value in exact_values:
      if value not in approved_values:
        if cid in self._failures:
          self._failures[cid].append(value)
        else:
          self._failures[cid] = [value]

  def check_pci_usb_component(self, cid, system_values, approved_values):
    if '*' in approved_values:
      self._system[cid] = ['*']
      return

    for value in approved_values:
      if value in system_values:
        self._system[cid] = [value]
        return

    self._failures[cid] = [self._no_match]

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
      self._failures[cid] = value

  def get_data_display_geometry(self):
    # Get edid from driver.
    # TODO(nsanders): this is driver specific.
    # TODO(waihong): read-edid is also x86 only.
    # format:   Mode "1280x800" -> 1280x800
    # TODO(hungte) merge this with get_part_id_display_panel

    cmd = ('cat "$(find /sys/devices/ -name edid | grep LVDS)" | '
           'parse-edid 2>/dev/null | grep "Mode " | cut -d\\" -f2')
    output = gft_common.SystemOutput(cmd).splitlines()
    return (output if output else [''])

  def get_hash_ec_firmware(self):
    """
    Returns a hash of Embedded Controller firmware parts,
    to confirm we have proper updated version of EC firmware.
    """

    image_file = self.load_ec_firmware()
    if not image_file:
      ErrorDie('get_hash_ec_firmware: cannot read firmware')
    return gft_fwhash.GetECHash(file_source=image_file)

  def get_hash_ro_firmware(self):
    """
    Returns a hash of Read Only (BIOS) firmware parts,
    to confirm we have proper keys / boot code / recovery image installed.
    """

    image_file = self.load_main_firmware()
    if not image_file:
      ErrorDie('get_hash_ro_firmware: cannot read firmware')
    return gft_fwhash.GetBIOSReadOnlyHash(file_source=image_file)

  def get_part_id_audio_codec(self):
    cmd = 'grep -R Codec: /proc/asound/* | head -n 1 | sed s/.\*Codec://'
    part_id = gft_common.SystemOutput(
        cmd, progress_messsage='Searching Audio Codecs: ',
        show_progress=self._verbose).strip()
    return part_id

  def get_part_id_cpu(self):
    cmd = 'grep -m 1 "model name" /proc/cpuinfo | sed s/.\*://'
    part_id = gft_common.SystemOutput(cmd).strip()
    return part_id

  def get_part_id_display_panel(self):
    # format:   ModelName "SEC:4231" -> SEC:4231

    cmd = ('cat "$(find /sys/devices/ -name edid | grep LVDS)" | '
           'parse-edid 2>/dev/null | grep ModelName | cut -d\\" -f2')
    output = gft_common.SystemOutput(cmd).strip()
    return (output if output else self._not_present)

  def get_part_id_embedded_controller(self):
    # example output:
    #  Found Nuvoton WPCE775x (id=0x05, rev=0x02) at 0x2e

    parts = []
    res = gft_common.SystemOutput(
        'superiotool',
        progress_messsage='Probing Embedded Controller: ',
        show_progress=self._verbose,
        ignore_status=True).splitlines()
    for line in res:
      match = re.search(r'Found (.*) at', line)
      if match:
        parts.append(match.group(1))
    part_id = ', '.join(parts)
    return part_id

  def get_part_id_ethernet(self):
    """
    Returns a colon delimited string where the first section
    is the vendor id and the second section is the device id.
    """

    # Ethernet is optional so mark it as not present. A human
    # operator needs to decide if this is acceptable or not.
    vendor_file = '/sys/class/net/eth0/device/vendor'
    part_file = '/sys/class/net/eth0/device/device'
    if os.path.exists(part_file) and os.path.exists(vendor_file):
      vendor_id = gft_common.ReadOneLine(vendor_file).replace('0x', '')
      part_id = gft_common.ReadOneLine(part_file).replace('0x', '')
      return '%s:%s' % (vendor_id, part_id)
    else:
      return self._not_present

  def get_part_id_dram(self):
    # TODO(hungte) if we only want DRAM size, maybe no need to use mosys
    self.load_module('i2c_dev')
    cmd = ('mosys -l memory spd print geometry | '
           'grep size_mb | cut -f2 -d"|"')
    part_id = gft_common.SystemOutput(cmd).strip()
    if part_id != '':
      return part_id
    else:
      return self._not_present

  def get_part_id_flash_chip(self):
    (chip_id, _) = self._load_firmware('main')
    return chip_id

  def get_part_id_ec_flash_chip(self):
    (chip_id, _) = self._load_firmware('ec')
    return chip_id

  def get_part_id_hwqual(self):
    part_id = gft_common.SystemOutput('crossystem hwid').strip()
    return (part_id if part_id else self._not_present)

  def get_part_id_storage(self):
    cmd = ('cd $(find /sys/devices -name sda)/../..; '
           'cat vendor model | tr "\n" " " | sed "s/ \\+/ /g"')
    part_id = gft_common.SystemOutput(cmd).strip()
    return part_id

  def get_part_id_tpm(self):
    """ Returns Manufacturer_info : Chip_Version """
    cmd = 'tpm_version'
    tpm_output = gft_common.SystemOutput(cmd)
    tpm_lines = tpm_output.splitlines()
    tpm_dict = {}
    for tpm_line in tpm_lines:
      [key, colon, value] = tpm_line.partition(':')
      tpm_dict[key.strip()] = value.strip()
    part_id = ''
    (key1, key2) = ('Manufacturer Info', 'Chip Version')
    if key1 in tpm_dict and key2 in tpm_dict:
      part_id = tpm_dict[key1] + ':' + tpm_dict[key2]
    return part_id

  def get_part_id_wireless(self):
    """
    Returns a colon delimited string where the first section
    is the vendor id and the second section is the device id.
    """

    part_id = gft_common.ReadOneLine('/sys/class/net/wlan0/device/device')
    vendor_id = gft_common.ReadOneLine('/sys/class/net/wlan0/device/vendor')
    return '%s:%s' % (vendor_id.replace('0x', ''), part_id.replace('0x', ''))

  def get_closed_vendor_id_touchpad(self, vendor_name):
    """ Using closed-source method to derive vendor information by name. """
    part_id = ''
    if vendor_name.lower() == 'synaptics':
      detect_program = '/opt/Synaptics/bin/syndetect'
      model_string_str = 'Model String'
      firmware_id_str = 'Firmware ID'
      if os.path.exists(detect_program):
        data = gft_common.SystemOutput(
            detect_program,
            progress_messsage='Synaptics Touchpad: ',
            show_progress=self._verbose,
            ignore_status=True)
        properties = dict(map(str.strip, line.split('=', 1))
                          for line in data.splitlines() if '=' in line)
        model = properties.get(model_string_str, 'UnknownModel')
        firmware_id = properties.get(firmware_id_str, 'UnknownFWID')

        # The pattern " on xxx Port" may vary by the detection approach,
        # so we need to strip it.
        model = re.sub(' on [^ ]* [Pp]ort$', '', model)

        # Format: Model #FirmwareId
        part_id = '%s #%s' % (model, firmware_id)
    return part_id

  def get_vendor_id_touchpad(self):
    # First, try to use closed-source method to probe touch pad
    part_id = self.get_closed_vendor_id_touchpad('Synaptics')
    if part_id != '':
      return part_id
    else:
      # If the closed-source method above fails to find vendor infomation,
      # try an open-source method.
      cmd_grep = 'grep -i Touchpad /proc/bus/input/devices | sed s/.\*=//'
      part_id = gft_common.SystemOutput(
          cmd_grep,
          progress_messsage='Finding Touchpad: ',
          show_progress=self._verbose).strip('"')
      return part_id

  def get_vendor_id_webcam(self):
    cmd = 'cat /sys/class/video4linux/video0/name'
    part_id = gft_common.SystemOutput(cmd).strip()
    return part_id

  def get_version_rw_firmware(self):
    """
    Returns the version of Read-Write (writable) firmware from VBLOCK sections.

    If A/B has different version, that means this system needs a reboot +
    firmwar update so return value is a "error report" in the form "A=x, B=y".
    """

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

  @Memorize
  def _read_gbb_component(self, name):
    image_file = self.load_main_firmware()
    if not image_file:
      ErrorDie('cannot load main firmware')
    filename = gft_common.GetTemporaryFileName('gbb%s' % name)
    self._temp_files.append(filename)
    if os.system('gbb_utility -g --%s=%s %s >/dev/null 2>&1' %
                 (name, filename, image_file)) != 0:
      ErrorDie('cannot get %s from GBB' % name)
    value = gft_common.ReadBinaryFile(filename)
    return value

  def probe_key_recovery(self, part_id):
    current_key = self._read_gbb_component('recoverykey')
    file_path = os.path.join(self._file_base, part_id)
    target_key = gft_common.ReadBinaryFile(file_path)
    return current_key.startswith(target_key)

  def probe_key_root(self, part_id):
    current_key = self._read_gbb_component('rootkey')
    file_path = os.path.join(self._file_base, part_id)
    target_key = gft_common.ReadBinaryFile(file_path)
    return current_key.startswith(target_key)

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

  def probe_part_id_chrontel(self, part_id):
    if part_id == self._not_present:
      return True

    if part_id == 'ch7036':
      self.load_module('i2c_dev')
      probe_cmd = 'ch7036_monitor -p >/dev/null 2>&1'
      present = os.system(probe_cmd) == 0
      return present

    return False

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

  def pformat(self, obj):
    return '\n' + self._pp.pformat(obj) + '\n'

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
        progress_messsage='Reading %s firmware: ' % target_name,
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

    Returns:
        A file name of cached image.
    """
    (_, image_file) = self._load_firmware('main')
    return image_file

  def load_ec_firmware(self):
    """ Loads and cache EC firmware image.

    Returns:
        A file name of cached image.
    """
    (_, image_file) = self._load_firmware('ec')
    return image_file

  def initialize(self, force=False):
    if self._initialized and not force:
      return
    # probe current system components
    DebugMsg('Starting to probe system components...')
    self._enumerable_system = self.get_all_enumerable_components()
    self._pci_system = self.get_all_pci_components()
    self._usb_system = self.get_all_usb_components()
    self._initialized = True

  def match_current_system(self, filename, ignored_cids=[]):
    """ Matches a given component list to current system.
        Returns: (current, failures)
    """

    # assert self._initialized, 'Not initialized.'
    self._to_be_tested_cids = (self._enumerable_cids +
                               self._pci_cids +
                               self._usb_cids +
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
    for cid in self._pci_cids:
      if cid not in self._to_be_tested_cids:
        VerboseMsg('gft_hwcomp: match: ignored: %s' % cid)
      else:
        self.check_pci_usb_component(cid, self._pci_system, approved[cid])
    for cid in self._usb_cids:
      if cid not in self._to_be_tested_cids:
        VerboseMsg('gft_hwcomp: match: ignored: %s' % cid)
      else:
        self.check_pci_usb_component(cid, self._usb_system, approved[cid])
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
  if not args:
    print 'Usage: %s components_db_files...\n' % self_path
    sys.exit(1)
  components = HardwareComponents(verbose=True)
  print 'Starting to probe system...'
  components.initialize()
  print 'Starting to match system...'

  for arg in args:
    (matched, failures) = components.match_current_system(arg)
    print 'Probed (%s):' % arg
    print components.pformat(matched)
    print 'Failures (%s):' % arg
    print components.pformat(failures)

if __name__ == '__main__':
  _main(sys.argv[0], sys.argv[1:])
