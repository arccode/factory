# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''Checks eMMC firmware version using the CID register values from sysfs.

This depends on the kernel exposing the CID fields directly in sysfs, this
enables future proofing by leaving the CID parsing to the kernel. The CID
register is only read for the purposes of logging.

If the test fails, then the test displays an error message and hangs forever.

Values used in this test, these are defined by JEDEC:

CID: Card IDentification register, 128 bit wide register readable from a
     standard eMMC device providing basic identification information.
MID: Manufacturer ID, 8 bit field in CID register, unique to a given eMMC
     vendor.
PNM: Product name, 48 bit wide field in CID register, a 6 ASCII character
     string providing the name of a eMMC device.
PRV: Product revision, 8 bit field in CID register, a vendor specific value
     typically representing a firmware version.
'''


import logging
import re
import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.event_log import Log
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

class eMMCCheckFWVersionTest(unittest.TestCase):
  ARGS = [
    Arg('valid_versions', list, 'A list of tuples, specifying the MID, PNM '
        'and a regex for the versions supported for that MID/PNM.'),
    Arg('cid_path', str, 'Path to CID value',
        default='/sys/devices/dw_mmc.0/mmc_host/mmc0/mmc0:0001/cid'),
    Arg('mid_path', str, 'Path to MID value',
        default='/sys/devices/dw_mmc.0/mmc_host/mmc0/mmc0:0001/manfid'),
    Arg('pnm_path', str, 'Path to PNM value',
        default='/sys/devices/dw_mmc.0/mmc_host/mmc0/mmc0:0001/name'),
    Arg('prv_path', str, 'Path to PRV value',
        default='/sys/devices/dw_mmc.0/mmc_host/mmc0/mmc0:0001/prv'),
    Arg('emmc_updater_available', bool, 'Boolean for if an eMMC FW update '
        'utility is available.', default=False)
  ]

  def _ValidatePRVField(self, mid, pnm, prv, valid_versions):
    """Validate the PRV field for a given manufacturer.

    Args:
      mid: string of the hex representation of the MID value
      pnm: string of the PNM value
      prv: string of the hex representation of the PRV value
      valid_versions: A list of tuples, specifying the MID, PNM, and a regex
                      for the versions supported for that MID/PNM.

    Returns:
      Boolean, true if FW revision is valid, false if not.

    Raises:
      ValueError if the MID value is not found in the test valid_versions
      AssertionErrror if prv length is not 2

    # Doctests
    >>> from cros.factory.test.args import Args
    >>> test = eMMCCheckFWVersionTest()
    >>> test._ValidatePRVField("00", "PARTNM", "01", [("00", "PARTNM", r"..")])
    True
    >>> test._ValidatePRVField("00", "PARTNM", "10", [("00", "PARTNM", r"2.")])
    False
    >>> test._ValidatePRVField("00", "BADPRT", "01", [("00", "PARTNM", r"..")])
    Traceback (most recent call last):
        ...
    ValueError: MID 00 PNM BADPRT not found in test list, wrong eMMC?
    >>> test._ValidatePRVField("99", "PARTNM", "01", [("00", "PARTNM", r"..")])
    Traceback (most recent call last):
        ...
    ValueError: MID 99 PNM PARTNM not found in test list, wrong eMMC?
    >>> test._ValidatePRVField("00", "PART", "123", [("00", "PART", r"..")])
    Traceback (most recent call last):
        ...
    AssertionError: Invalid prv length
    """
    for valid_mid, valid_pnm, regex in valid_versions:
      if valid_mid == mid and valid_pnm == pnm:
        self.assertTrue(len(prv) == 2, 'Invalid prv length')
        if re.match(regex, prv):
          logging.info('The eMMC firmware version %s is correct.', prv)
          return True
        else:
          logging.info('The eMMC FW version %s does not match %s.', prv, regex)
          return False
    raise ValueError('MID %s PNM %s not found in test list, wrong eMMC?' %
                     (mid, pnm))

  def runTest(self):
    self.assertTrue(os.path.exists(self.args.cid_path), 'cid_path %s is not '
                    'found, bad path?' % (self.args.cid_path))
    self.assertTrue(os.path.exists(self.args.mid_path), 'mid_path %s is not '
                    'found, bad path?' % (self.args.mid_path))
    self.assertTrue(os.path.exists(self.args.pnm_path), 'pnm_path %s is not '
                    'found, bad path?' % (self.args.pnm_path))
    self.assertTrue(os.path.exists(self.args.prv_path), 'prv_path %s is not '
                    'found, bad path?' % (self.args.prv_path))
    cid = open(self.args.cid_path).read().strip()
    mid = open(self.args.mid_path).read().strip()[-2:]
    pnm = open(self.args.pnm_path).read().strip()
    prv = open(self.args.prv_path).read().strip()[-2:]
    logging.info('Raw CID value: %s', cid)
    logging.info('MID: %s, PNM: %s, PRV: %s', mid, pnm, prv)
    Log('emmc_obtained', cid=cid, mid=mid, pnm=pnm, prv=prv)
    if self._ValidatePRVField(mid, pnm, prv, self.args.valid_versions):
      return # Pass the test

    if self.args.emmc_updater_available:
      ui = test_ui.UI()
      template = ui_templates.OneSection(ui)
      template.SetTitle(test_ui.MakeLabel(
          'eMMC Firmware Version Incorrect',
          'eMMC 韧体版本不对'))
      template.SetState(
          '<div class=test-status-failed style="font-size: 150%">' +
          test_ui.MakeLabel(
              'The eMMC firmware version (%s) is incorrect. '
              '<br>Please run the eMMC firmware update tool.' % prv,

              'eMMC 韧体版（%s）版本不对。'
              '<br>必须更新 eMMC 韧体并重新安装工厂测试软件。' % prv) +
          '</div>')
      ui.Run()  # Forever
    else:
      self.fail('The eMMC firmware version (%s) is incorrect. However, no '
                'update is currently available.' % prv)
