# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A hardware test for probing USB devices.

It uses the lsusb utility to check if there's an USB device with given VID:PID
or containing a specified string in lsusb.

If search_string is defined, it searches for it in 'lsusb -v' and passes if the
string exists, usb_id_list are ignored in this case.

If usb_id_list is defined, it searches for them in 'lsusb -d id' and passes
if any id in the list is found.

If bus_id is defined, the result above is also filtered by given bus id.
"""

import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import component
from cros.factory.device import device_utils
from cros.factory.test import event_log
from cros.factory.utils.arg_utils import Arg


class USBProbeTest(unittest.TestCase):
  ARGS = [
      Arg('bus_id', str, 'Bus id in format [[bus]:][devnum].', optional=True),
      Arg('usb_id_list', list, 'A list of "VID:[PID]" to be searched.',
          optional=True),
      Arg('use_re', bool,
          'True to treat search_string as a regular expression.',
          default=False),
      Arg('search_string', str, 'manual string to check for in lsusb -v.',
          optional=True),
  ]

  def _ProbeUSB(self, search_string, lsusb_options, use_re):
    """Search for a string in lsusb -v.

    If self.args.use_re is enabled, search lsusb via re.search.

    Args:
      string_string: string to search for.
      lsusb_options: extra options for lsusb command.
      use_re: True to treat search_string as a regular expression.

    Returns:
      True if the string is found, false if not.
    """
    response = self._dut.CheckOutput(['lsusb'] + lsusb_options)
    if use_re:
      return bool(re.search(search_string, response))
    else:
      return search_string in response

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

  def runTest(self):
    bus_id_option = ['-s', self.args.bus_id] if self.args.bus_id else []

    if self.args.search_string:
      usb_string = self.args.search_string
      probed_result = self._ProbeUSB(usb_string, ['-v'] + bus_id_option,
                                     self.args.use_re)
      event_log.Log('usb_probe', result=probed_result, usb_string=usb_string)
      self.assertTrue(probed_result,
                      'String: %s was not found in lsusb -v.' % usb_string)
    elif self.args.usb_id_list:
      for usb_id in self.args.usb_id_list:
        try:
          self._ProbeUSB('', ['-d', usb_id] + bus_id_option, False)
          event_log.Log('usb_probe', usb_id=usb_id)
          return
        except component.CalledProcessError:
          pass
      self.fail('Cannot found any one of %r in lsusb.'
                % self.args.usb_id_list)
    else:
      self.fail('Either search_string or usb_id_list must be set')
