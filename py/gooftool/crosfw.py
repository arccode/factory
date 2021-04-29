# pylint: disable=attribute-defined-outside-init
# Copyright 2012 The Chromium OS Authors. All rights reserved.
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
import os
import re
import tempfile

from cros.factory.gooftool import common
from cros.factory.utils import fmap


# Names to select target bus.
TARGET_MAIN = 'main'
TARGET_EC = 'ec'
TARGET_PD = 'pd'

CROS_PD_PATH = '/dev/cros_pd'

# Types of named tuples
WpStatus = collections.namedtuple('WpStatus', 'enabled offset size')

# All Chrome OS images are FMAP based.
FirmwareImage = fmap.FirmwareImage


class Flashrom:
  """Wrapper for calling system command flashrom(8)."""

  # flashrom(8) command line parameters
  _VALID_TARGETS = (TARGET_MAIN, TARGET_EC, TARGET_PD)
  _TARGET_MAP = {
      TARGET_MAIN: '-p host',
      TARGET_EC: '-p ec',
      TARGET_PD: '-p ec:type=pd',
  }
  _WRITE_FLAGS = '--noverify-all'
  _READ_FLAGS = ''

  def __init__(self, target=None):
    self._target = target or TARGET_MAIN

  def _InvokeCommand(self, param, ignore_status=False):
    command = ' '.join(['flashrom', self._TARGET_MAP[self._target], param])

    if self._target == TARGET_PD and not os.path.exists(CROS_PD_PATH):
      # crbug.com/p/691901: 'flashrom' does not return PD information reliably
      # using programmer "-p ec:type=pd". As a result, we want to only read PD
      # information if /dev/cros_pd exists.
      logging.debug('%s._InvokeCommand: Ignore command because %s does not '
                    'exist: [%s]', self.__class__, CROS_PD_PATH, command)
      command = 'false'
    else:
      logging.debug('%s._InvokeCommand: %s', self.__class__, command)

    result = common.Shell(command)
    if not (ignore_status or result.success):
      raise IOError('Failed in command: %s\n%s' % (command, result.stderr))
    return result

  def GetTarget(self):
    """Gets current target (bus) to access."""
    return self._target

  def SetTarget(self, target):
    """Sets current target (bus) to access."""
    assert target in self._VALID_TARGETS, 'Unknown target: %s' % target
    self._target = target

  def GetSize(self):
    return int(self._InvokeCommand('--flash-size').stdout.splitlines()[-1], 0)

  def GetName(self):
    """Returns a key-value dict for chipset info, or None for any failure."""
    results = self._InvokeCommand('--flash-name', ignore_status=True).stdout
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
      with tempfile.NamedTemporaryFile(prefix='fw_%s_' % self._target) as f:
        return self.Read(f.name)
    sections_param = ['-i %s' % name for name in sections or []]
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
    assert ((data is None) ^ (filename is None)), (
        'Either data or filename should be None.')
    if data is not None:
      with tempfile.NamedTemporaryFile(prefix='fw_%s_' % self._target) as f:
        f.write(data)
        f.flush()
        self.Write(None, f.name)
        return
    sections_param = [('-i %s' % name) for name in sections or []]
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
    results = self._InvokeCommand('--wp-status').stdout
    status = re.findall(r'WP: write protect is (\w+)\.', results)
    if len(status) != 1:
      raise IOError('Failed getting write protection status')
    status = status[0]
    if status not in ('enabled', 'disabled'):
      raise ValueError('Unknown write protection status: %s' % status)

    wp_range = re.findall(r'WP: write protect range: start=(\w+), len=(\w+)',
                          results)
    if len(wp_range) != 1:
      raise IOError('Failed getting write protection range')
    wp_range = wp_range[0]
    return WpStatus(status == 'enabled',
                    int(wp_range[0], 0),
                    int(wp_range[1], 0))

  def EnableWriteProtection(self, offset, size):
    """Enables write protection by specified range."""
    self._InvokeCommand('--wp-range 0x%06X,0x%06X --wp-enable' % (offset, size))
    result = self.GetWriteProtectionStatus()
    if ((not result.enabled) or (result.offset != offset) or
        (result.size != size)):
      raise IOError('Failed to enabled write protection.')

    # Try to verify write protection by attempting to disable it.
    self._InvokeCommand('--wp-disable --wp-range 0,0', ignore_status=True)
    # Verify the results
    result = self.GetWriteProtectionStatus()
    if ((not result.enabled) or (result.offset != offset) or
        (result.size != size)):
      raise IOError('Software write protection can be disabled. Please make '
                    'sure hardware write protection is enabled.')

  def DisableWriteProtection(self):
    """Tries to Disable whole write protection range and status."""
    self._InvokeCommand('--wp-disable --wp-range 0,0')
    result = self.GetWriteProtectionStatus()
    if result.enabled or (result.offset != 0) or (result.size != 0):
      raise IOError('Failed to disable write protection.')


class FirmwareContent:
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
    obj.cached_files = []
    cls._target_cache[target] = obj
    return obj

  def GetChipId(self):
    """Caching get of flashrom chip identifier.  None if no chip is present."""
    if not hasattr(self, 'chip_id'):
      info = self.flashrom.GetName()
      self.chip_id = ' '.join([info['vendor'], info['name']]) if info else None
    return self.chip_id

  def GetFileName(self, sections=None):
    """Filename containing firmware data.  None if no chip is present.

    Args:
      sections: Restrict the sections of firmware data to be stored in the file.

    Returns:
      Name of the file which contains the firmware data.
    """
    if self.GetChipId() is None:
      return None

    sections = set(sections) if sections else None

    for (fileref, sections_in_file) in self.cached_files:
      if sections_in_file is None or (
          sections is not None and sections.issubset(sections_in_file)):
        return fileref.name

    fileref = tempfile.NamedTemporaryFile(prefix='fw_%s_' % self.target)
    self.flashrom.Read(filename=fileref.name, sections=sections)
    self.cached_files.append((fileref, sections))
    return fileref.name

  def Write(self, filename):
    """Call flashrom write for specific sections."""
    for (fileref, sections_in_file) in self.cached_files:
      if fileref.name == filename:
        self.flashrom.Write(filename=filename, sections=sections_in_file)
        return
    raise ValueError('%r is not found in the cached files' % (filename,))

  def GetFirmwareImage(self, sections=None):
    """Returns a fmap.FirmwareImage instance.

    Args:
      sections: Restrict the sections of firmware data to be stored in the file.

    Returns:
      An instance of FormwareImage.
    """
    with open(self.GetFileName(sections=sections), 'rb') as image:
      return fmap.FirmwareImage(image.read())


def LoadEcFirmware():
  """Returns flashrom data from Embedded Controller chipset."""
  return FirmwareContent.Load(TARGET_EC)


def LoadPDFirmware():
  """Returns flashrom data from Power Delivery chipset."""
  return FirmwareContent.Load(TARGET_PD)


def LoadMainFirmware():
  """Returns flashrom data from main firmware (also known as BIOS)."""
  return FirmwareContent.Load(TARGET_MAIN)
