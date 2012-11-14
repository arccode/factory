#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import mox
import os
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory import gooftool
from cros.factory.common import Error
from cros.factory.common import Shell
from cros.factory.gooftool import Gooftool
from cros.factory.gooftool.probe import Probe
from cros.factory.hwdb import hwid_tool
from cros.factory.hwdb.hwid_tool import ProbeResults  # pylint: disable=E0611
from cros.factory.gooftool import Mismatch
from cros.factory.gooftool import ProbedComponentResult

class GooftoolTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()

    # Probe should always be mocked in the unit test since this test is not
    # likely to be ran on a DUT.
    self._mock_probe = self.mox.CreateMock(Probe)
    testdata_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                 'testdata')
    test_db = hwid_tool.HardwareDb(testdata_path)

    self._util = gooftool.Util()
    self._util._shell = self.mox.CreateMock(Shell)

    self._gooftool = Gooftool(probe=self._mock_probe, hardware_db=test_db)
    self._gooftool._util = self._util  # pylint: disable=W0212

    # Mock out small wrapper functions that do not need unittests.
    self.mox.StubOutWithMock(self._util, "_IsDeviceFixed")

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testVerifyComponents(self):
    '''Test if the Gooftool.VerifyComponent() works properly.

    This test tries to probe three components [camera, battery, cpu], where
      'camera' returns a valid result.
      'battery' returns a false result.
      'cpu' does not return any result.
      'tpm' returns multiple results.
    '''

    self._mock_probe(
        probe_initial_config=False,
        probe_volatile=False,
        target_comp_classes=['camera', 'battery', 'cpu', 'tpm']).AndReturn(
            ProbeResults(
                found_probe_value_map={
                    'camera': 'CAMERA_1',
                    'battery': 'fake value',
                    'tpm': ['TPM_1', 'TPM_2', 'fake value']},
                missing_component_classes={},
                found_volatile_values=[],
                initial_configs={}))

    self.mox.ReplayAll()

    self.assertEquals(
        {'camera': [('camera_1', 'CAMERA_1', None)],
         'battery': [(None, 'fake value', mox.IsA(str))],
         'cpu': [(None, None, mox.IsA(str))],
         'tpm': [('tpm_1', 'TPM_1', None),
                 ('tpm_2', 'TPM_2', None),
                 (None, 'fake value', mox.IsA(str))]},
        self._gooftool.VerifyComponents(['camera', 'battery', 'cpu', 'tpm']))

  def testVerifyBadComponents(self):
    self.mox.ReplayAll()

    self.assertRaises(ValueError, self._gooftool.VerifyComponents, [])
    self.assertRaises(ValueError, self._gooftool.VerifyComponents, [])
    self.assertRaises(ValueError,
                      self._gooftool.VerifyComponents, ['bad_class_name'])
    self.assertRaises(
        ValueError,
        self._gooftool.VerifyComponents, ['camera', 'bad_class_name'])

  def testFindBOMMismatches(self):
    self.mox.ReplayAll()

    # expect fully matched result
    self.assertEquals(
        {},
        self._gooftool.FindBOMMismatches(
            'BENDER',
            'LEELA',
            {'camera': [ProbedComponentResult('camera_1', 'CAMERA_1', None)],
             'tpm': [ProbedComponentResult('tpm_1', 'TPM_1', None)],
             'vga': [ProbedComponentResult('vga_1', 'VGA_1', None)]}))

    # expect mismatch results
    self.assertEquals(
        {'camera': Mismatch(
            expected=set(['camera_1']), actual=set(['camera_2'])),
         'vga': Mismatch(
            expected=set(['vga_1']), actual=set(['vga_2']))},
        self._gooftool.FindBOMMismatches(
            'BENDER',
            'LEELA',
            {'camera': [ProbedComponentResult('camera_2', 'CAMERA_2', None)],
             'tpm': [ProbedComponentResult('tpm_1', 'TPM_1', None)],
             'vga': [ProbedComponentResult('vga_2', 'VGA_2', None)]}))

  def testFindBOMMismatchesMissingDontcare(self):
    self.mox.ReplayAll()

    # expect fully matched result
    self.assertEquals(
        {},
        self._gooftool.FindBOMMismatches(
            'BENDER',
            'FRY',
             # expect = don't care, actual = some value
            {'camera': [ProbedComponentResult('camera_2', 'CAMERA_2', None)],
             # expect = don't care, actual = missing
             'cpu': [ProbedComponentResult(None, None, "Missing")],
             # expect = missing, actual = missing
             'cellular': [ProbedComponentResult(None, None, "Missing")]}))

    # expect mismatch results
    self.assertEquals(
        {'cellular': Mismatch(
            expected=None,
            actual=[ProbedComponentResult('cellular_1', 'CELLULAR_1', None)]),
         'dram': Mismatch(
            expected=set(['dram_1']), actual=set([None]))},
        self._gooftool.FindBOMMismatches(
            'BENDER',
            'FRY',
             # expect correct value
            {'camera': [ProbedComponentResult('camera_2', 'CAMERA_2', None)],
             # expect = missing, actual = some value
             'cellular': [ProbedComponentResult(
                 'cellular_1', 'CELLULAR_1', None)],
             # expect = some value, actual = missing
             'dram': [ProbedComponentResult(None, None, 'Missing')]}))

  def testFindBOMMismatchesError(self):
    self.mox.ReplayAll()

    self.assertRaises(
      ValueError, self._gooftool.FindBOMMismatches, 'NO_BARD', 'LEELA',
      {'camera': [ProbedComponentResult('camera_1', 'CAMERA_1', None)]})
    self.assertRaises(
      ValueError, self._gooftool.FindBOMMismatches, 'BENDER', 'NO_BOM', {})
    self.assertRaises(
      ValueError, self._gooftool.FindBOMMismatches, 'BENDER', None, {})
    self.assertRaises(
      ValueError, self._gooftool.FindBOMMismatches, 'BENDER', 'LEELA', None)

  def testGetPrimaryDevicePath(self):
    '''Test for GetPrimaryDevice.'''

    self._util._IsDeviceFixed(   # pylint: disable=W0212
        "sda").MultipleTimes().AndReturn(True)
    self._util._IsDeviceFixed(   # pylint: disable=W0212
        "sdb").MultipleTimes().AndReturn(False)

    stub_cgpt_result = lambda: None
    stub_cgpt_result.stdout = "/dev/sda3\n/dev/sda1\n/dev/sdb1"
    self._util._shell(  # pylint: disable=W0212
        'cgpt find -t rootfs').MultipleTimes().AndReturn(stub_cgpt_result)

    self.mox.ReplayAll()

    self.assertEquals("/dev/sda", self._util.GetPrimaryDevicePath())
    self.assertEquals("/dev/sda1", self._util.GetPrimaryDevicePath(1))
    self.assertEquals("/dev/sda2", self._util.GetPrimaryDevicePath(2))

    # also test thin callers
    self.assertEquals("/dev/sda5", self._gooftool.GetReleaseRootPartitionPath())
    self.assertEquals("/dev/sda4",
                      self._gooftool.GetReleaseKernelPartitionPath())

  def testGetPrimaryDevicePathMultiple(self):
    '''Test for GetPrimaryDevice when multiple primary devices are found.'''

    self._util._IsDeviceFixed(  # pylint: disable=W0212
        "sda").MultipleTimes().AndReturn(True)
    self._util._IsDeviceFixed(  # pylint: disable=W0212
        "sdb").MultipleTimes().AndReturn(True)

    stub_cgpt_result = lambda: None
    stub_cgpt_result.stdout = "/dev/sda3\n/dev/sda1\n/dev/sdb1"
    self._util._shell(  # pylint: disable=W0212
        'cgpt find -t rootfs').AndReturn(stub_cgpt_result)

    self.mox.ReplayAll()

    self.assertRaises(Error, self._util.GetPrimaryDevicePath)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
