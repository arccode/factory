#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
Extracts data from firmware binaries and sends it to the shopfloor server.

Example:
  ./rma_save_data.py --firmware bios.bin --rma RMA00001234 --outdir /tmp/
  ./rma_save_data.py --ro_vpd ro_vpd.bin --rw_vpd rw_vpd.bin --gbb gbb.bin \
                     --rma RMA00001234 --outdir /tmp/
"""

import logging
import optparse
import os
import re
import sys
import xmlrpclib

from httplib import socket
from subprocess import Popen, PIPE

_GBB_UTILITY_LOCATION = '/usr/bin/gbb_utility'
_SHOPFLOOR_SERVER_URL = 'http://192.168.2.1:8082'
_VPD_UTILITY_LOCATION = '/usr/sbin/vpd'

_options = None

class ServerFault(Exception):
  pass


def _server_api(call):
  """Decorator of calls to remote server.

  Converts xmlrpclib.Fault generated during remote procedural call to
  a simplified form (shopfloor.ServerFault).
  """
  def wrapped_call(*args, **kargs):
    try:
      return call(*args, **kargs)
    except xmlrpclib.Fault as e:
      logging.exception('Shopfloor server:')
      raise ServerFault(e.faultString.partition(':')[2])
  wrapped_call.__name__ = call.__name__
  return wrapped_call


def get_instance(shopfloor_url):
  """Gets an instance (for client side) to access the shop floor server.

  Args:
    shopfloor_url - String. URL (including port) of the shopfloor server.

  Returns:
    xmlrpc proxy object to the shopfloor server.
  """
  return xmlrpclib.ServerProxy(shopfloor_url)


@_server_api
def server_is_up(server):
  """Checks if the given instance is successfully connected.

  Args:
    server - xmlrpc proxy object to hte shopfloor server.

  Returns:
    Bool - True if the server responds, False otherwise.
  """
  try:
    server.Ping()
  except socket.error:
    return False
  return True


@_server_api
def SaveDeviceData(shopfloor, device_data, overwrite=False):
  """Sends device data to the shopfloor server.

  Args:
    shopfloor - xmlrpc proxy to shopfloor server.
    device_data - dictionary containing device information.
    overwrite - Bool. Whether to replace data if it exists on
                the server.

  Returns:
    dictionary - Contents defined by link RMA shopfloor module.

  """
  return shopfloor.SaveDeviceData(device_data, overwrite)


class Obj(object):
  """Generic wrapper allowing dot-notation dict access."""

  def __init__(self, **field_dict):
    self.__dict__.update(field_dict)

  def __eq__(self, other):
    return self.__dict__ == other.__dict__

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return repr(self.__dict__)

  def is_valid(self):
    return False if None in self.__dict__.values() else True


class DeviceData(object):
  """Container for device-specific data."""

  def __init__(self, serial_number, vpd, hwid):
    self.serial_number = serial_number
    self.vpd = vpd
    self.hwid = hwid

  @classmethod
  def FromDictionary(cls, dictionary):
    vpd = VPD(dictionary['vpd']['ro'], dictionary['vpd']['rw'])
    return DeviceData(dictionary['rma_number'], vpd, dictionary['hwid'])

  def __eq__(self, other):
    return self.__dict__ == other.__dict__

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return repr(self.__dict__)

  def __str__(self):
    pretty_str = 'RMA Number: %s\n' % self.serial_number
    pretty_str += 'HWID: %s\n' % self.hwid
    pretty_str += str(self.vpd) + "\n"
    return pretty_str

  def is_valid(self):
    if self.serial_number is None:
      return False
    if not self.vpd.is_valid():
      return False
    if self.hwid is None or self.hwid == 'X86 LINK TEST 6638':
      return False
    return True


class VPD(object):
  """Vital Product Data container."""

  _REQUIRED_RO_VPD_FIELDS = ('als_cal_data', 'initial_locale',
      'initial_timezone', 'keyboard_layout','serial_number')

  def __init__(self, ro_vpd, rw_vpd):
    self.ro = ro_vpd
    self.rw = rw_vpd

  def __eq__(self, other):
    return self.__dict__ == other.__dict__

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    censored_dict = self.__dict__.copy()
    for key in censored_dict['rw']:
      if key in ['ubind_attribute', 'gbind_attribute']:
        censored_dict['rw'][key] = 'REDACTED'
    return repr(censored_dict)

  def __str__(self):

    def format_vpd_str(vpd_dict):
      keys = vpd_dict.keys()
      keys.sort()
      vpd_str = ''
      for key in keys:
        vpd_str += '  %s: %s\n' % (key, vpd_dict[key])
      return vpd_str

    vpd_str = 'RO VPD:\n'
    vpd_str += format_vpd_str(self.ro)
    vpd_str += 'RW VPD:\n'
    vpd_str += format_vpd_str(self.rw)
    return vpd_str

  def is_valid(self):
    if None in self.__dict__.values():
      return False
    for field in self._REQUIRED_RO_VPD_FIELDS:
      if field not in self.ro:
        return False
    return True


def Shell(command, stdin=None):
  """Convenience wrapper for running a shell command."""

  process = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
  stdout, stderr = process.communicate(input=stdin)
  status = process.poll()
  return Obj(stdout=stdout, stderr=stderr, status=status, success=(status == 0))


def ExtractVPD(partition, filename):
  """Returns the VPD from a firmware or vpd binary."""

  vpd_dict = {}
  vpd_response = Shell(_options.vpd_utility + ' -l -i %s -f %s' %
                       (partition, filename))
  raw_vpd = vpd_response.stdout # pylint: disable=E1101
  for line in raw_vpd.splitlines():
    match = re.match('"(.*)"="(.*)"$', line.strip())
    (name, value) = (match.group(1), match.group(2))
    vpd_dict[name] = value
  return vpd_dict


def GetHWID(filename):
  """Returns the HWID from a firmware or gbb binary."""

  gbb_response = Shell(_GBB_UTILITY_LOCATION + ' -g --hwid %s' % filename)
  raw_gbb = gbb_response.stdout # pylint: disable=E1101
  match = re.match('hardware_id: (.*)', raw_gbb.strip())
  if match is None:
    logging.warning('Unable to find HWID in gbb: %s', filename)
    return None
  return match.group(1)


def DeviceDataFromFirmwareRegions(ro_vpd_file, rw_vpd_file, gbb_file,
                                  rma_number):
  """Read device data from a device's firmware.

  Args:
    ro_vpd_file: Path to a file containing either a RO_VPD region
                 or entire firmware image.
    rw_vpd_file: Path to a file containing either a RW_VPD region
                 or entire firmware image.
    gbb_file: Path to a file containing either a GBB region
              or entire firmware image.
    rma_number: The RMA number for the device.

  Returns:
    A DeviceData object containing VPD and HWID info extracted from
    the firmware files.
  """

  serial_number = rma_number
  ro_vpd = ExtractVPD('RO_VPD', ro_vpd_file)
  rw_vpd = ExtractVPD('RW_VPD', rw_vpd_file)
  vpd = VPD(ro_vpd, rw_vpd)
  hwid = GetHWID(gbb_file)
  return DeviceData(serial_number, vpd, hwid)


def prompt(question):
  """Display the question to the user and wait for input."""

  sys.stdout.write(question)
  answer = raw_input().lower()
  if answer in ['y', 'yes']:
    return True
  elif answer in ['n', 'no']:
    return False
  else:
    return prompt(question)


def option_parser():
  parser = optparse.OptionParser()
  parser.add_option('-f', '--firmware', dest='firmware', metavar='FILE',
                    help='Location of source firmware binary.')
  parser.add_option('--gbb', dest='gbb', metavar='FILE',
                    help='Location of file containing the Google binary block.')
  parser.add_option('--gbb_utility', dest='gbb_utility', metavar='FILE',
                    default=_GBB_UTILITY_LOCATION,
                    help='Location of gbb utility.')
  parser.add_option('-o', '--outdir', dest='output_directory', metavar='DIR',
                    default=os.getcwd(),
                    help=('Location of output directory. '
                          'Defaults to the current directory.'))
  parser.add_option('-r', '--rma', dest='rma_number', metavar='RMAxxxxxxxx',
                    help='RMA number.')
  parser.add_option('--ro_vpd', dest='ro_vpd', metavar='FILE',
                    help='Location of file containing the read-only VPD.')
  parser.add_option('--rw_vpd', dest='rw_vpd', metavar='FILE',
                    help='Location of file containing the read-write VPD.')
  parser.add_option('-s', '--shopfloor', dest='shopfloor_url', metavar='URL',
                    default=_SHOPFLOOR_SERVER_URL,
                    help='URL of shopfloor server to send data.')
  parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                    help='Enable debug logging.')
  parser.add_option('--vpd_utility', dest='vpd_utility', metavar='FILE',
                    default=_VPD_UTILITY_LOCATION,
                    help='Location of vpd utility.')
  return parser


def main():
  """Main entry when invoked from the command line."""

  global _options

  parser = option_parser()
  (_options, args) = parser.parse_args()

  if _options.verbose:
    logging.basicConfig(
        level=logging.DEBUG if _options.verbose else logging.INFO)

  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  if not os.path.exists(_options.gbb_utility):
    parser.error('Unable to find GBB utility: %s' % _options.gbb_utility)

  if not os.path.exists(_options.vpd_utility):
    parser.error('Unable to find VPD utility: %s' % _options.vpd_utility)

  shopfloor = get_instance(_options.shopfloor_url)
  if not server_is_up(shopfloor):
    logging.fatal('Unable to connect with shopfloor server: %s',
                  _options.shopfloor_url)
    sys.exit(1)

  if not _options.firmware and (not _options.ro_vpd or not _options.rw_vpd or
                               not _options.gbb):
    parser.error('You must specify a firmware file. (-f)')

  if not _options.rma_number:
    parser.error('You must specify an RMA number. (-r)')

  ro_vpd = _options.ro_vpd if _options.ro_vpd else _options.firmware
  rw_vpd = _options.rw_vpd if _options.rw_vpd else _options.firmware
  gbb = _options.gbb if _options.gbb else _options.firmware

  device_data = DeviceDataFromFirmwareRegions(ro_vpd, rw_vpd, gbb,
                                              _options.rma_number)
  if not device_data.is_valid():
    logging.warning('Device data is not valid. Not sending data to shopfloor '
                  'server: %r', device_data)
    sys.exit(0) # Return success to proceed with flashing netboot firmware.

  reply = SaveDeviceData(shopfloor, device_data)
  if reply['status'] == 'success':
    logging.info('Successfully sent device data to shopfloor server.')
    sys.exit(0)
  elif reply['status'] == 'conflict':
    existing_device_data = DeviceData.FromDictionary(reply['data'])
    if device_data == existing_device_data:
      logging.info('Found existing identical device data.')
      sys.exit(0)
    if prompt(
        'RMA data for %s already exists.\n'
        'Existing data:\n'
        '====================\n'
        '%s\n'
        'New data:\n'
        '====================\n'
        '%s\n'
        'Do you want to replace it (Y/N)? ' %
        (_options.rma_number, existing_device_data, device_data)):
      reply = SaveDeviceData(shopfloor, device_data, overwrite=True)
      if reply['status'] != 'success':
        logging.fatal('Unexpected error while overwriting data: %s', reply)
        sys.exit(1)
  else:
    logging.fatal('Invalid reply from shopfloor server: %s', reply)
    sys.exit(1)


if __name__ == '__main__':
  main()
