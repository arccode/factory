#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility to access ChromeOS Netboot firmware settings."""

from __future__ import print_function

import argparse
import pprint
import socket
import struct
import sys

import factory_common  # pylint:disable=unused-import
from cros.factory.utils import fmap


# Values to encode netboot settings.
CODE_TFTP_SERVER_IP = 1
CODE_KERNEL_ARGS = 2
CODE_BOOT_FILE = 3
CODE_ARGS_FILE = 4

SETTINGS_FMAP_SECTION = 'SHARED_DATA'


class Image(object):
  """A class to represent a firmware image.

  Areas in the image should be accessed using the [] operator which takes
  the area name as its key.

  Attributes:
      data: The data in the entire image.
  """

  def __init__(self, data):
    """Initialize an instance of Image

    Args:
        self: The instance of Image.
        data: The data contianed within the image.
    """
    try:
      # FMAP identifier used by the cros_bundle_firmware family of utilities.
      obj = fmap.fmap_decode(data, fmap_name='FMAP')
    except struct.error:
      # FMAP identifier used by coreboot's FMAP creation tools.
      # The name signals that the FMAP covers the entire flash unlike, for
      # example, the EC RW firmware's FMAP, which might also come as part of
      # the image but covers a smaller section.
      obj = fmap.fmap_decode(data, fmap_name='FLASH')
    self.areas = {}
    for area in obj['areas']:
      self.areas[area['name']] = area
    self.data = data

  def __setitem__(self, key, value):
    """Write data into an area of the image.

    If value is smaller than the area it's being written into, it will be
    padded out with NUL bytes. If it's too big, a ValueError exception
    will be raised.

    Args:
        self: The image instance.
        key: The name of the area to overwrite.
        value: The data to write into the area.

    Raises:
        ValueError: 'value' was too large to write into the selected area.
    """
    area = self.areas[key]
    if len(value) > area['size']:
      raise ValueError('Too much data for FMAP area %s' % key)
    value = value.ljust(area['size'], '\0')
    self.data = (self.data[:area['offset']] + value +
                 self.data[area['offset'] + area['size']:])

  def __getitem__(self, key):
    """Retrieve the data in an area of the image.

    Args:
        self: The image instance.
        key: The area to retrieve.

    Returns:
        The data in that area of the image.
    """
    area = self.areas[key]
    return self.data[area['offset']:area['offset'] + area['size']]


class Settings(object):
  """A class which represents a collection of settings.

  The settings can be updated after a firmware image has been built.

  Attributes of this class other than the signature constant are stored in
  the 'value' field of each attribute in the attributes dict.

  Attributes:
      signature: A constant which has a signature value at the front of the
        settings when written into the image.
  """
  signature = 'netboot\0'

  class Attribute(object):
    """A class which represents a particular setting.

    Attributes:
        code: An enum value which identifies which setting this is.
        value: The value the setting has been set to.
    """
    def __init__(self, code, value):
      """Initialize an Attribute instance.

      Args:
          code: The code for this attribute.
          value: The initial value of this attribute.
      """
      self.code = code
      self.value = value

    @staticmethod
    def padded_value(value):
      value_len = len(value)
      pad_len = ((value_len + 3) // 4) * 4 - value_len
      return value + '\0' * pad_len

    def pack(self):
      """Pack an attribute into a binary representation.

      Args:
          self: The Attribute to pack.

      Returns:
          The binary representation.
      """
      if self.value:
        value = self.value.pack()
      else:
        value = ''
      value_len = len(value)
      padded_value = self.padded_value(value)
      format_str = '<II%ds' % len(padded_value)
      return struct.pack(format_str, self.code, value_len, padded_value)

    def __repr__(self):
      return repr(self.value)

    @classmethod
    def unpack(cls, blob, offset=0):
      """Returns a pair of (decoded attribute, decoded length)."""
      header_str = '<II'
      header_len = struct.calcsize(header_str)
      code, value_len = struct.unpack_from(header_str, blob, offset)
      offset += header_len
      value = blob[offset:offset + value_len]
      offset += len(cls.padded_value(value))
      if value:
        setting = IpAddressValue if code == CODE_TFTP_SERVER_IP else StringValue
        value = setting.unpack(value)
      return cls(code, value), offset

  def __init__(self, blob):
    """Initialize an instance of Settings.

    Args:
        self: The instance to initialize.
    """
    # Decode blob if possible.
    decoded = {}
    if blob.startswith(self.signature):
      offset = len(self.signature)
      format_items = '<I'
      items, = struct.unpack_from(format_items, blob, offset)
      offset += struct.calcsize(format_items)
      for unused_i in xrange(items):
        new_attr, new_offset = self.Attribute.unpack(blob, offset)
        offset = new_offset
        decoded[new_attr.code] = new_attr

    def GetAttribute(code):
      return decoded.get(code, self.Attribute(code, None))

    attributes = {
        'tftp_server_ip': GetAttribute(CODE_TFTP_SERVER_IP),
        'kernel_args': GetAttribute(CODE_KERNEL_ARGS),
        'bootfile': GetAttribute(CODE_BOOT_FILE),
        'argsfile': GetAttribute(CODE_ARGS_FILE),
    }
    self.__dict__['attributes'] = attributes

  def __setitem__(self, name, value):
    self.attributes[name].value = value

  def __getattr__(self, name):
    return self.attributes[name].value

  def pack(self):
    """Pack a Settings object into a binary representation.

    The packed binary representation can be put into an image.

    Args:
        self: The instance to pack.

    Returns:
        A binary representation of the settings.
    """
    value = self.signature
    value += struct.pack('<I', len(self.attributes))
    for unused_i, attr in self.attributes.iteritems():
      value += attr.pack()
    return value


class StringValue(object):
  """Class for setting values that are stored simply as strings."""

  def __init__(self, val):
    """Initialize an instance of StringValue.

    Args:
        self: The instance to initialize.
        val: The value of the setting.
    """
    self.val = val

  def pack(self):
    """Pack the setting by returning its value as a string.

    Args:
        self: The instance to pack.

    Returns:
        The val field as a string.
    """
    return str(self.val)

  @classmethod
  def unpack(cls, val):
    return cls(val)

  def __str__(self):
    return str(self.val)

  def __repr__(self):
    return repr(self.val.strip('\0'))


class IpAddressValue(StringValue):
  """Class for IP address setting value."""

  def __init__(self, val):
    """Initialize an IpAddressValue instance.

    Args:
        self: The instance to initialize.
        val: A string representation of the IP address to be set to.
    """
    in_addr = socket.inet_pton(socket.AF_INET, val)
    super(IpAddressValue, self).__init__(in_addr)

  @classmethod
  def unpack(cls, val):
    return cls(socket.inet_ntop(socket.AF_INET, val))

  def __str__(self):
    return socket.inet_ntop(socket.AF_INET, self.val)

  def __repr__(self):
    return repr(str(self))


def DefineCommandLineArgs(parser):
  """Defines arguments in command line invocation.

  Args:
    parser: an argparse.ArgumentParser instance.
  """
  parser.add_argument('--input', '-i', required=True,
                      help='Path to the firmware to modify; required')
  parser.add_argument('--output', '-o',
                      help='Path to store output; if not specified we will '
                           'directly modify the input file')

  parser.add_argument('--tftpserverip',
                      help='Set the TFTP server IP address (defaults to DHCP-'
                           'provided address)')
  parser.add_argument('--bootfile',
                      help='Set the path of the TFTP boot file (defaults to '
                           'DHCP-provided file name)')
  parser.add_argument('--argsfile',
                      help='Set the path of the TFTP file that provides the '
                           'kernel command line (overrides default and --arg)')

  parser.add_argument('--board',
                      help='Set the cros_board to be passed into the kernel')
  parser.add_argument('--factory-server-url',
                      help='Set the Factory Server URL')
  parser.add_argument('--arg', '--kernel_arg', default=[], dest='kernel_args',
                      metavar='kernel_args', action='append',
                      help='Set extra kernel command line parameters (appended '
                           'to default string for factory)')


def NetbootFirmwareSettings(options):
  """Main function to access netboot firmware settings."""
  print('Reading from %s...' % options.input)
  with open(options.input, 'r') as f:
    image = Image(f.read())

  settings = Settings(image[SETTINGS_FMAP_SECTION])
  print('Current settings:')
  pprint.pprint(settings.attributes)

  # pylint: disable=unsubscriptable-object
  if options.tftpserverip:
    settings['tftp_server_ip'] = IpAddressValue(options.tftpserverip)
  if options.bootfile:
    settings['bootfile'] = StringValue(options.bootfile + '\0')
  if options.argsfile:
    settings['argsfile'] = StringValue(options.argsfile + '\0')
  # pylint: enable=unsubscriptable-object

  kernel_args = ''
  if options.board:
    kernel_args += 'cros_board=' + options.board + ' '
  if options.factory_server_url:
    kernel_args += 'omahaserver=' + options.factory_server_url + ' '
  kernel_args += ' '.join(options.kernel_args)
  kernel_args += '\0'
  # pylint: disable=unsubscriptable-object
  settings['kernel_args'] = StringValue(kernel_args)
  # pylint: enable=unsubscriptable-object

  new_blob = settings.pack()
  output_name = options.output or options.input

  # If output is specified with different name, always generate output.
  do_output = output_name != options.input
  if new_blob == image[SETTINGS_FMAP_SECTION][:len(new_blob)]:
    print('Settings not changed.')
  else:
    print('Settings modified. New settings:')
    pprint.pprint(settings.attributes)
    image[SETTINGS_FMAP_SECTION] = new_blob
    do_output = True

  if do_output:
    print('Generating output to %s...' % output_name)
    with open(output_name, 'w') as f:
      f.write(image.data)

def main(argv):
  """Main entry for command line."""
  parser = argparse.ArgumentParser(description=__doc__)
  DefineCommandLineArgs(parser)
  options = parser.parse_args(argv)
  NetbootFirmwareSettings(options)


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
