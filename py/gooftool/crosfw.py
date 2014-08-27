# pylint: disable=W0201
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""ChromeOS Firmware Utilities

This modules provides easy access to ChromeOS firmware.

To access the contents of a firmware image, use FimwareImage().
To access the flash chipset containing firmware, use Flashrom().
To get the content of (cacheable) firmware, use LoadMainFirmware() or
  LoadEcFirmware().
"""

import collections
import logging
import re

from tempfile import NamedTemporaryFile

import fmap

import factory_common  # pylint: disable=W0611
from cros.factory.common import Shell


# Names to select target bus.
TARGET_MAIN = 'main'
TARGET_EC = 'ec'
TARGET_PD = 'pd'

# Types of named tuples
WpStatus = collections.namedtuple('WpStatus', 'enabled offset size')


class Flashrom(object):
  """Wrapper for calling system command flashrom(8)."""

  # flashrom(8) command line parameters
  _VALID_TARGETS = (TARGET_MAIN, TARGET_EC, TARGET_PD)
  _TARGET_MAP = {
      TARGET_MAIN: "-p host",
      TARGET_EC: "-p ec",
      TARGET_PD: "-p ec:dev=1",
  }
  _WRITE_FLAGS = "--fast-verify"
  _READ_FLAGS = ""

  def __init__(self, target=None):
    self._target = target or TARGET_MAIN

  def _InvokeCommand(self, param, ignore_status=False):
    command = ' '.join(['flashrom', self._TARGET_MAP[self._target], param])
    logging.debug('Flashrom._InvokeCommand: %s', command)
    result = Shell(command)
    if not (ignore_status or result.success):
      raise IOError, "Failed in command: %s\n%s" % (command, result.stderr)
    return result

  def GetTarget(self):
    """Gets current target (bus) to access."""
    return self._target

  def SetTarget(self, target):
    """Sets current target (bus) to access."""
    assert target in self._VALID_TARGETS, "Unknown target: %s" % target
    self._target = target

  def GetSize(self):
    return int(self._InvokeCommand("--get-size").stdout.splitlines()[-1], 0)

  def GetName(self):
    """Returns a key-value dict for chipset info, or None for any failure."""
    results = self._InvokeCommand("--flash-name", ignore_status=True).stdout
    match_list = re.findall(r'\b(\w+)="([^"]*)"', results)
    return dict(match_list) if match_list else None

  def Read(self, filename=None, sections=None):
    """Reads whole image from selected flash chipset.

    Args:
      filename: File name to receive image. None to use temporary file.
      sections: List of sections to read. None to read whole image.

    Returns:
      Image data read from flash chipset.
    """
    if filename is None:
      with NamedTemporaryFile(prefix='fw_%s_' % self._target) as f:
        return self.Read(f.name)
    sections_param = [name % '-i %s' for name in sections or []]
    self._InvokeCommand("-r '%s' %s %s" % (filename, ' '.join(sections_param),
                                           self._READ_FLAGS))
    with open(filename, 'rb') as file_handle:
      return file_handle.read()

  def Write(self, data=None, filename=None, sections=None):
    """Writes image into selected flash chipset.

    Args:
      data: Image data to write. None to write given file.
      filename: File name of image to write if data is None.
      sections: List of sections to write. None to write whole image.
    """
    assert (((data is not None) and (filename is None)) or
            ((data is None) and (filename is not None))), \
                "Either data or filename should be None."
    if data is not None:
      with NamedTemporaryFile(prefix='fw_%s_' % self._target) as f:
        f.write(data)
        f.flush()
        return self.Write(None, f.name)
    sections_param = [('-i %s' % name) for name in (sections or [])]
    self._InvokeCommand("-w '%s' %s %s" % (filename, ' '.join(sections_param),
                                           self._WRITE_FLAGS))

  def GetWriteProtectionStatus(self):
    """Gets write protection status from selected flash chipset.

    Returns: A named tuple with (enabled, offset, size).
    """
    # flashrom(8) output: WP: status: 0x80
    #                     WP: status.srp0: 1
    #                     WP: write protect is %s. (disabled/enabled)
    #                     WP: write protect range: start=0x%8x, len=0x%08x
    results = self._InvokeCommand("--wp-status").stdout
    status = re.findall(r'WP: write protect is (\w+)\.', results)
    if len(status) != 1:
      raise IOError, "Failed getting write protection status"
    status = status[0]
    if status not in ('enabled', 'disabled'):
      raise ValueError, "Unknown write protection status: %s" % status

    wp_range = re.findall(r'WP: write protect range: start=(\w+), len=(\w+)',
                          results)
    if len(wp_range) != 1:
      raise IOError, "Failed getting write protection range"
    wp_range = wp_range[0]
    return WpStatus(True if status == 'enabled' else False,
                    int(wp_range[0], 0),
                    int(wp_range[1], 0))

  def EnableWriteProtection(self, offset, size):
    """Enables write protection by specified range."""
    self._InvokeCommand('--wp-range 0x%06X 0x%06X --wp-enable' % (offset, size))
    # Try to verify write protection by attempting to disable it.
    self._InvokeCommand('--wp-disable --wp-range 0 0', ignore_status=True)
    # Verify the results
    result = self.GetWriteProtectionStatus()
    if ((not result.enabled) or (result.offset != offset) or
        (result.size != size)):
      raise IOError, "Failed to enabled write protection."

  def DisableWriteProtection(self):
    """Tries to Disable whole write protection range and status."""
    self._InvokeCommand('--wp-disable --wp-range 0 0')
    result = self.GetWriteProtectionStatus()
    if (result.enabled or (result.offset != 0) or (result.size != 0)):
      raise IOError, "Failed to disable write protection."


class FirmwareImage(object):
  """Provides access to firmware image via FMAP sections."""
  def __init__(self, image_source):
    self._image = image_source
    self._fmap = fmap.fmap_decode(self._image)
    self._areas = dict(
        (entry['name'], [entry['offset'], entry['size']])
        for entry in self._fmap['areas'])

  def get_size(self):
    """Returns the size of associate firmware image."""
    return len(self._image)

  def has_section(self, name):
    """Returns if specified section is available in image."""
    return name in self._areas

  def get_section_area(self, name):
    """Returns the area (offset, size) information of given section."""
    if not self.has_section(name):
      raise ValueError('get_section_area: invalid section: %s' % name)
    return self._areas[name]

  def get_section(self, name):
    """Returns the content of specified section."""
    area = self.get_section_area(name)
    return self._image[area[0]:(area[0] + area[1])]

  def get_section_offset(self, name):
    area = self.get_section_area(name)
    return self._image[area[0]:(area[0] + area[1])]

  def put_section(self, name, value):
    """Updates content of specified section in image."""
    area = self.get_section_area(name)
    if len(value) != area[1]:
      raise ValueError("Value size (%d) does not fit into section (%s, %d)" %
                       (len(value), name, area[1]))
    self._image = (self._image[0:area[0]] +
                   value +
                   self._image[(area[0] + area[1]):])
    return True

  def get_fmap_blob(self):
    """Returns the re-encoded fmap blob from firmware image."""
    return fmap.fmap_encode(self._fmap)


class FirmwareContent(object):
  """Wrapper around flashrom for a specific firmware target.

  This class keeps track of all the instances of itself that exist.
  The goal being that only one instance ever gets created for each
  target. This mapping of targets to instances is tracked by the
  _target_cache class data member.
  """

  # Cache of target:instance pairs.
  _target_cache = {}

  @classmethod
  def Load(cls, target):
    """Create class instance for target, using cached copy if available."""
    if target in cls._target_cache:
      return cls._target_cache[target]
    obj = cls()
    obj.target = target
    obj.flashrom = Flashrom(target)
    cls._target_cache[target] = obj
    return obj

  def GetChipId(self):
    """Caching get of flashrom chip identifier.  None if no chip is present."""
    if not hasattr(self, 'chip_id'):
      info = self.flashrom.GetName()
      self.chip_id = ' '.join([info['vendor'], info['name']]) if info else None
    return self.chip_id

  def GetFileName(self):
    """Filename containing firmware data.  None if no chip is present."""
    if self.GetChipId() is None:
      return None
    if not hasattr(self, 'filename'):
      fileref = NamedTemporaryFile(prefix='fw_%s_' % self.target)
      self.flashrom.Read(filename=fileref.name)
      self.fileref = fileref
      self.filename = fileref.name
    return self.filename

  def Write(self, sections=None):
    """Call flashrom write for specific sections."""
    self.flashrom.Write(filename=self.GetFileName(), sections=sections)

  def GetFirmwareImage(self):
    """Returns a FirmwareImage instance."""
    with open(self.GetFileName(), 'rb') as image:
      return FirmwareImage(image.read())


def LoadEcFirmware():
  """Returns flashrom data from Embedded Controller chipset."""
  return FirmwareContent.Load(TARGET_EC)


def LoadPDFirmware():
  """Returns flashrom data from Power Delivery chipset."""
  return FirmwareContent.Load(TARGET_PD)

def LoadMainFirmware():
  """Returns flashrom data from main firmware (also known as BIOS)."""
  return FirmwareContent.Load(TARGET_MAIN)
