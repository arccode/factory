# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for EDID data parsing and loading.

See for more info:
  https://en.wikipedia.org/wiki/Extended_display_identification_data
"""

import binascii
import fcntl
import glob
import logging
import os
import re
import time

from cros.factory.gooftool.common import Shell
from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import sys_utils


# Constants lifted from EDID documentation.
VERSION = 0x01
MAGIC = b'\x00\xff\xff\xff\xff\xff\xff\x00'
MAGIC_OFFSET = 0
MANUFACTURER_ID_OFFSET = 8
PRODUCT_ID_OFFSET = 10
VERSION_OFFSET = 18
REVISION_OFFSET = 19
PIXEL_CLOCK_OFFSET = 54
HORIZONTAL_OFFSET = 56
HORIZONTAL_HIGH_OFFSET = 58
VERTICAL_OFFSET = 59
VERTICAL_HIGH_OFFSET = 61
CHECKSUM_OFFSET = 127
I2C_LVDS_ADDRESS = 0x50
MINIMAL_SIZE = 128
MANUFACTURER_ID_BITS = 5

PREFIX_TEGRA = b'edid[000]'


def Parse(content):
  """Public interface of EDID parser.

  Args:
    content: EDID data retrieved from device.
  """
  # Check if it's from Tegra.
  if content.startswith(PREFIX_TEGRA):
    return _ParseTegra(content)
  return _ParseBinaryBlob(content)


def _ParseTegra(content):
  """Parser for EDID data exported by tegra_edid driver.

  When tegra_edid driver is used, the exported EDID is in text format, ex:

    edid[000] = 00 ff ff ff ff ff ff 00 06 af 2c 13 00 00 00 00
    edid[010] = 00 18 01 03 80 1d 10 78 0a bb f5 94 55 54 90 27
    edid[020] = 23 50 54 00 00 00 01 01 01 01 01 01 01 01 01 01
    edid[030] = 01 01 01 01 01 01 26 1b 56 64 50 00 16 30 30 20
    edid[040] = 36 00 25 a4 10 00 00 18 00 00 00 0f 00 00 00 00
    edid[050] = 00 00 00 00 00 00 00 00 00 20 00 00 00 fe 00 41
    edid[060] = 55 4f 0a 20 20 20 20 20 20 20 20 20 00 00 00 fe
    edid[070] = 00 42 31 33 33 58 54 4e 30 31 2e 33 20 0a 00 4b

  Thus, we have to strip the first 12 characters, all white spaces, and all
  newline characters, then transform the rest from hex code into a binary blob.

  Args:
    content: EDID file content from a Tegra device.
  """
  return _ParseBinaryBlob(binascii.unhexlify(
      re.sub(r'\s|(edid\[\d{3}\] = )', '', content)))


def _ParseBinaryBlob(blob):
  """Binary EDID Parser (light-weight parse-edid replacement).

  Simple parsing of EDID.  The full-feature parser (parse-edid) has
  many more dependencies, and so is too heavy-weight for use here.

  TODO(hungte) Use parse-edid if it becomes practical/available.
  Specifically once we know that it will be available on all of our
  systems.

  Args:
    blob: a binary blob with encoded EDID.

  Returns:
    A dict of extracted keys to extracted EDID fields.  Return None if
    the blob is not a valid EDID record, and also log warning messages
    indicating the reason for parsing failure.
  """
  def ReadShortBE(offset):
    return (blob[offset] << 8) | blob[offset + 1]

  def ReadShortLE(offset):
    return (blob[offset + 1] << 8) | blob[offset]

  # Check size, magic, and version.
  if len(blob) < MINIMAL_SIZE:
    logging.warning('EDID parsing error: length too small.')
    return None
  if blob[MAGIC_OFFSET:(MAGIC_OFFSET + len(MAGIC))] != MAGIC:
    logging.warning('EDID parse error: incorrect header.')
    return None
  if blob[VERSION_OFFSET] != VERSION:
    logging.warning('EDID parse error: unsupported EDID version.')
    return None
  # Verify checksum.
  if sum(list(blob[:CHECKSUM_OFFSET + 1])) % 0x100 != 0:
    logging.warning('EDID parse error: checksum error.')
    return None
  # Currently we don't support EDID not using pixel clock.
  pixel_clock = ReadShortLE(PIXEL_CLOCK_OFFSET)
  if not pixel_clock:
    logging.warning('EDID parse error: '
                    'non-pixel clock format is not supported yet.')
    return None
  # Extract manufacturer.
  vendor_name = ''
  vendor_code = ReadShortBE(MANUFACTURER_ID_OFFSET)
  # vendor_code: [0 | char1 | char2 | char3]
  for i in range(2, -1, -1):
    vendor_char = (vendor_code >> (i * MANUFACTURER_ID_BITS)) & 0x1F
    vendor_char = chr(vendor_char + ord('@'))
    vendor_name += vendor_char
  product_id = ReadShortLE(PRODUCT_ID_OFFSET)
  width = (blob[HORIZONTAL_OFFSET] | ((blob[HORIZONTAL_HIGH_OFFSET] >> 4) << 8))
  height = (blob[VERTICAL_OFFSET] | ((blob[VERTICAL_HIGH_OFFSET] >> 4) << 8))
  return {'vendor': vendor_name,
          'product_id': '%04x' % product_id,
          'width': str(width),
          'height': str(height)}


def _I2CDump(bus, address, size):
  """Reads binary dump from i2c bus."""
  fd = -1
  I2C_PERIPHERAL = 0x0703
  blob = None
  try:
    fd = os.open(bus, os.O_RDWR)
    if fcntl.ioctl(fd, I2C_PERIPHERAL, address) != 0:
      return None
    time.sleep(0.05)  # Wait i2c to get ready
    if os.write(fd, b'\x00') == 1:
      blob = os.read(fd, size)
  except Exception:
    logging.exception('Fail to dump from i2c bus.')
  finally:
    if fd >= 0:
      os.close(fd)
  return blob


def LoadFromI2C(path):
  """Runs Parse() against the output of _I2CDump on the specified path.

  Args:
    path: i2c path, can be either int type (ex: 0) or string type (ex:
          '/dev/i2c-0')

  Returns:
    Parsed I2c output, None if it fails to dump something for the specific I2C.
  """
  if isinstance(path, int):
    path = '/dev/i2c-%d' % path
  command = 'i2cdetect -y -r %s %d %d' % (
      path.split('-')[1], I2C_LVDS_ADDRESS, I2C_LVDS_ADDRESS)
  # Make sure there is a device in I2C_LVDS_ADDRESS
  blob = None
  if not '--' in Shell(command).stdout:
    blob = _I2CDump(path, I2C_LVDS_ADDRESS, MINIMAL_SIZE)
  return None if blob is None else Parse(blob)


def LoadFromFile(path):
  return Parse(file_utils.ReadFile(path, encoding=None))


class EDIDFunction(probe_function.ProbeFunction):
  # pylint: disable=line-too-long
  """Probe EDID information from file or I2C bus.

  Description
  -----------
  This function tries to search for exported edid files in sysfs matching the
  pattern ``/sys/class/drm/*/edid``. If no edid files are found in sysfs, it
  probes all i2c buses for EDID blobs.

  Once this function finds an EDID data, this function parses the data to
  obtain ``vendor``, ``product_id``, ``width`` and ``height`` fields from
  the EDID data.  The format of an EDID data structure can be found in the
  `wiki page
  <https://en.wikipedia.org/wiki/Extended_display_identification_data>`_.
  The ``vendor`` field this function obtains is actually the manufacturer ID
  (byte 8~9); ``product_id`` is the manufacturer product ID
  listed in the wiki page.

  Examples
  --------
  If you want this function just outputs all EDID data, the probe statement
  is simply::

    {
      "eval": "edid"
    }

  Let's assume the output is ::

    [
      {
        "vendor": "IBM",
        "product_id": "abcd",
        "width": "19200",
        "height": "10800",
        "sysfs_path": "/sys/class/drm/aa/edid"
      },
      {
        "vendor": "IBX",
        "product_id": "1234",
        "width": "192",
        "height": "108",
        "sysfs_path": "/sys/class/drm/bb/edid"
      }
    ]

  If you are only interested in the monitor made by IBM, you can modify
  the probe statement to ::

    {
      "eval": "edid",
      "expect": {
        "vendor": "IBM"
      }
    }

  so that the probed results will only contain the one with ``"vendor": "IBM"``.

  Another use case is to ask this function to probe the EDID file in/on a
  specific path or i2c bus.  For example::

    {
      "eval": "edid:/dev/i2c-3"
    }

  """
  path_to_identity = {}
  identity_to_edid = {}

  ARGS = [
      Arg('path', str,
          'EDID file path or the number of I2C bus or the path of the i2c '
          'bus (i.e. "/dev/i2c-<bus_number>").',
          default=None),
  ]

  ROOT_PATH = '/'
  I2C_DEVICE_PREFIX = 'dev/i2c-'
  SYSFS_PATH_PATTERN = 'sys/class/drm/*/edid'
  DEV_PATH_PATTERN = I2C_DEVICE_PREFIX + '[0-9]*'

  def Probe(self):
    self.MayInitCachedData()

    if not self.args.path:
      return list(self.identity_to_edid.values())

    if self.args.path in self.path_to_identity:
      return self.identity_to_edid[self.path_to_identity[self.args.path]]

    if self.args.path.isdigit():
      path = os.path.join(self.ROOT_PATH,
                          self.I2C_DEVICE_PREFIX + self.args.path)
      if path in self.path_to_identity:
        return self.identity_to_edid[self.path_to_identity[path]]

    logging.error('The given path is invalid, available edid path are: %r',
                  list(self.path_to_identity))
    return function.NOTHING

  @classmethod
  def MayInitCachedData(cls):
    if cls.path_to_identity:
      return

    for pattern_type, glob_pattern in [
        ('sysfs_path', os.path.join(cls.ROOT_PATH, cls.SYSFS_PATH_PATTERN)),
        ('dev_path', os.path.join(cls.ROOT_PATH, cls.DEV_PATH_PATTERN))]:
      for path in glob.glob(glob_pattern):
        result = cls.ProbeEDID(path)
        if not result:
          continue

        identity = (result['vendor'], result['product_id'])
        cls.path_to_identity[path] = identity

        cls.identity_to_edid.setdefault(identity, result)
        cls.identity_to_edid[identity][pattern_type] = path

      # If we already get results from sysfs, we don't need to probe i2c.
      if cls.path_to_identity:
        break

  @classmethod
  def ProbeEDID(cls, path):
    if path.startswith(os.path.join(cls.ROOT_PATH, cls.I2C_DEVICE_PREFIX)):
      sys_utils.LoadKernelModule('i2c_dev')
      parsed_edid = LoadFromI2C(path)
    else:
      parsed_edid = LoadFromFile(path)
    return parsed_edid
