# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to initiate and verify recovery mode memory re-train process.

Usage examples::

    with AutomatedSequence(id='MRCCache', label=_('MRC Cache')):
      FactoryTest(
          id='Create',
          label=_('Create Cache'),
          pytest_name='mrc_cache',
          dargs={'mode': 'create'})

      RebootStep(
          id='Reboot',
          label=_('Reboot'),
          iterations=1)

      FactoryTest(
          id='Verify',
          label=_('Verify'),
          pytest_name='mrc_cache',
          dargs={'mode': 'verify'})

"""

import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.file_utils import UnopenedTemporaryFile

class MrcCacheTest(unittest.TestCase):
  ARGS = [
      Arg('mode', str,
          'Specify the phase of the test, valid values are:\n'
          '- "create": request memory retraining on next boot.\n'
          '- "verify": verify the mrc cache created by previous step.\n')]

  def Create(self):
    # check RECOVERY_MRC_CACHE exists
    self.dut.CheckCall('flashrom -p host -r /dev/null -i RECOVERY_MRC_CACHE')
    # request to retrain memory
    self.dut.CheckCall('crossystem recovery_request=0xC4')

  def Verify(self):
    with UnopenedTemporaryFile() as f:
      self.dut.CheckCall('flashrom -p host -r /dev/null '
                         '-i RECOVERY_MRC_CACHE:%s' % f)
      self.dut.CheckCall('futility validate_rec_mrc %s' % f)

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def runTest(self):
    if self.args.mode == 'create':
      self.Create()
    elif self.args.mode == 'verify':
      self.Verify()
    else:
      self.fail('Unknown mode: %s' % self.args.mode)
