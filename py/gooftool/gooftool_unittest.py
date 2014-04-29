#!/usr/bin/python
# pylint: disable=W0212
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for gooftool module."""

import logging
import mox
import os
import unittest

from collections import namedtuple
from contextlib import contextmanager
from tempfile import NamedTemporaryFile

import factory_common  # pylint: disable=W0611
from cros.factory import gooftool
from cros.factory.common import Error
from cros.factory.common import Shell
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import Gooftool
from cros.factory.gooftool.bmpblk import unpack_bmpblock
from cros.factory.gooftool.probe import Probe, ReadRoVpd
from cros.factory.hwdb import hwid_tool
from cros.factory.hwdb.hwid_tool import ProbeResults  # pylint: disable=E0611
from cros.factory.gooftool import Mismatch
from cros.factory.gooftool import ProbedComponentResult
from cros.factory.system import vpd
from cros.factory.test import branding
from cros.factory.utils import file_utils
from cros.factory.utils.process_utils import CheckOutput

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

# A stub for stdout
StubStdout = namedtuple('StubStdout', ['stdout'])

class MockMainFirmware(object):
  """Mock main firmware object."""
  def __init__(self):
    self.GetFileName = lambda: "firmware"
    self.Write = lambda sections: sections == ['GBB']

class MockFile(object):
  """Mock file object."""
  def __init__(self):
    self.name = 'filename'
    self.read = lambda: "read_results"
  def __enter__(self):
    return self
  def __exit__(self, filetype, value, traceback):
    pass

class UtilTest(unittest.TestCase):
  """Unit test for Util."""
  def setUp(self):
    self.mox = mox.Mox()

    self._util = gooftool.Util()

    # Mock out small wrapper functions that do not need unittests.
    self._util.shell = self.mox.CreateMock(Shell)
    self.mox.StubOutWithMock(self._util, "_IsDeviceFixed")
    self.mox.StubOutWithMock(self._util, "FindScript")

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testGetPrimaryDevicePath(self):
    '''Test for GetPrimaryDevice.'''

    self._util._IsDeviceFixed(
        "sda").MultipleTimes().AndReturn(True)
    self._util._IsDeviceFixed(
        "sdb").MultipleTimes().AndReturn(False)

    self._util.shell('cgpt find -t rootfs').MultipleTimes().AndReturn(
        StubStdout("/dev/sda3\n/dev/sda1\n/dev/sdb1"))

    self.mox.ReplayAll()

    self.assertEquals("/dev/sda", self._util.GetPrimaryDevicePath())
    self.assertEquals("/dev/sda1", self._util.GetPrimaryDevicePath(1))
    self.assertEquals("/dev/sda2", self._util.GetPrimaryDevicePath(2))

    # also test thin callers
    self.assertEquals("/dev/sda5", self._util.GetReleaseRootPartitionPath())
    self.assertEquals("/dev/sda4", self._util.GetReleaseKernelPartitionPath())

  def testGetPrimaryDevicePathMultiple(self):
    '''Test for GetPrimaryDevice when multiple primary devices are found.'''

    self._util._IsDeviceFixed(
        "sda").MultipleTimes().AndReturn(True)
    self._util._IsDeviceFixed(
        "sdb").MultipleTimes().AndReturn(True)

    self._util.shell('cgpt find -t rootfs').AndReturn(
        StubStdout("/dev/sda3\n/dev/sda1\n/dev/sdb1"))

    self.mox.ReplayAll()

    self.assertRaises(Error, self._util.GetPrimaryDevicePath)

  def testFindRunScript(self):
    self._util.FindScript(mox.IsA(str)).MultipleTimes().AndReturn("script")

    stub_result = lambda: None
    stub_result.success = True
    self._util.shell("script").AndReturn(stub_result)  # option = []
    self._util.shell("script").AndReturn(stub_result)  # option = None
    self._util.shell("script a").AndReturn(stub_result)
    self._util.shell("script a b").AndReturn(stub_result)
    self._util.shell("c=d script a b").AndReturn(stub_result)
    self._util.shell("c=d script").AndReturn(stub_result)

    self.mox.ReplayAll()

    self._util.FindAndRunScript("script")
    self._util.FindAndRunScript("script", None)
    self._util.FindAndRunScript("script", ["a"])
    self._util.FindAndRunScript("script", ["a", "b"])
    self._util.FindAndRunScript("script", ["a", "b"], ["c=d"])
    self._util.FindAndRunScript("script", None, ["c=d"])

  def testGetCrosSystem(self):
    self._util.shell('crossystem').AndReturn(StubStdout(
        'first_flag   =   123  # fake comment\n'
        'second_flag  =   flag_2_value  # another fake comment'))

    self.mox.ReplayAll()
    self.assertEqual({'first_flag': '123', 'second_flag': 'flag_2_value'},
                     self._util.GetCrosSystem())


class GooftoolTest(unittest.TestCase):
  """Unit test for Gooftool."""
  def setUp(self):
    self.mox = mox.Mox()

    # Probe should always be mocked in the unit test since this test is not
    # likely to be ran on a DUT.
    self._mock_probe = self.mox.CreateMock(Probe)
    test_db = hwid_tool.HardwareDb(_TEST_DATA_PATH)

    self._gooftool = Gooftool(probe=self._mock_probe, hardware_db=test_db)
    self._gooftool._util = self.mox.CreateMock(gooftool.Util)
    self._gooftool._util.shell = self.mox.CreateMock(Shell)

    self._gooftool._crosfw = self.mox.CreateMock(crosfw)
    self._gooftool._unpack_bmpblock = self.mox.CreateMock(unpack_bmpblock)
    self._gooftool._read_ro_vpd = self.mox.CreateMock(ReadRoVpd)
    self._gooftool._named_temporary_file = self.mox.CreateMock(
        NamedTemporaryFile)

    gooftool.CheckOutput = self.mox.CreateMock(CheckOutput)

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

  def testVerifyKey(self):
    self._gooftool._util.GetReleaseKernelPartitionPath().AndReturn("kernel")

    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())

    self._gooftool._util.FindAndRunScript("verify_keys.sh",
                                          ["kernel", "firmware"])

    self.mox.ReplayAll()
    self._gooftool.VerifyKeys()

  def testVerifySystemTime(self):
    self._gooftool._util.GetReleaseRootPartitionPath().AndReturn("root")

    self._gooftool._util.FindAndRunScript("verify_system_time.sh", ["root"])

    self.mox.ReplayAll()
    self._gooftool.VerifySystemTime()

  def testVerifyRootFs(self):
    self._gooftool._util.GetReleaseRootPartitionPath().AndReturn("root")

    self._gooftool._util.FindAndRunScript("verify_rootfs.sh", ["root"])

    self.mox.ReplayAll()
    self._gooftool.VerifyRootFs()

  def testVerifyTPM(self):
    gooftool.CheckOutput(
        ['cryptohome', '--action=tpm_status']).AndReturn(
             '''TPM Enabled: true
             TPM Owned: false
             TPM Being Owned: false
             TPM Ready: false
             TPM Password:''')
    self.mox.ReplayAll()
    self._gooftool.VerifyTPM()

  def testClearGBBFlags(self):
    self._gooftool._util.FindAndRunScript("clear_gbb_flags.sh")
    self.mox.ReplayAll()
    self._gooftool.ClearGBBFlags()

  def testPrepareWipe(self):
    self._gooftool._util.GetReleaseRootPartitionPath(
        ).AndReturn("root1")
    self._gooftool._util.FindAndRunScript("prepare_wipe.sh", ["root1"], [])

    self._gooftool._util.GetReleaseRootPartitionPath(
        ).AndReturn("root2")
    self._gooftool._util.FindAndRunScript("prepare_wipe.sh", ["root2"],
                                          ["FACTORY_WIPE_TAGS=fast"])

    self.mox.ReplayAll()

    self._gooftool.PrepareWipe(False)
    self._gooftool.PrepareWipe(True)

  def testWriteHWID(self):
    self._gooftool._crosfw.LoadMainFirmware().MultipleTimes().AndReturn(
      MockMainFirmware())
    self._gooftool._util.shell('gbb_utility --set --hwid="hwid1" "firmware"')
    self._gooftool._util.shell('gbb_utility --set --hwid="hwid2" "firmware"')

    self.mox.ReplayAll()

    self._gooftool.WriteHWID("hwid1")
    self._gooftool.WriteHWID("hwid2")

  def testVerifyWPSwitch(self):
    # 1st call: enabled
    self._gooftool._util.shell('crossystem wpsw_cur').AndReturn(StubStdout('1'))
    # 2nd call: disabled
    self._gooftool._util.shell('crossystem wpsw_cur').AndReturn(StubStdout('0'))

    self.mox.ReplayAll()

    self._gooftool.VerifyWPSwitch()
    self.assertRaises(Error, self._gooftool.VerifyWPSwitch)

  def _SetupBrandingMocks(self, ro_vpd, fake_rootfs_path):
    """Set up mocks for VerifyBranding tests.

    Args:
      ro_vpd: The dictionary to use for the RO VPD.
      fake_rootfs_path: A path at which we pretend to mount the release rootfs.
    """

    # Fake partition to return from MountPartition mock.
    @contextmanager
    def MockPartition(path):
      yield path

    self.mox.StubOutWithMock(vpd.ro, "GetAll")
    self.mox.StubOutWithMock(gooftool, "MountPartition")

    vpd.ro.GetAll().AndReturn(ro_vpd)
    if fake_rootfs_path:
      # Pretend that '/dev/rel' is the release rootfs path.
      self._gooftool._util.GetReleaseRootPartitionPath().AndReturn('/dev/rel')
      # When '/dev/rel' is mounted, return a context manager yielding
      # fake_rootfs_path.
      gooftool.MountPartition('/dev/rel').AndReturn(
          MockPartition(fake_rootfs_path))

  def testVerifyBranding_NoBrandCode(self):
    self._SetupBrandingMocks({}, '/doesntexist')
    self.mox.ReplayAll()
    # Should fail, since rlz_brand_code isn't present anywhere
    self.assertRaisesRegexp(ValueError, 'rlz_brand_code is not present',
                            self._gooftool.VerifyBranding)

  def testVerifyBranding_AllInVPD(self):
    self._SetupBrandingMocks(
        dict(rlz_brand_code='ABCD', customization_id='FOO'), None)
    self.mox.ReplayAll()
    self.assertEquals(dict(rlz_brand_code='ABCD', customization_id='FOO'),
                      self._gooftool.VerifyBranding())

  def testVerifyBranding_BrandCodeInVPD(self):
    self._SetupBrandingMocks(dict(rlz_brand_code='ABCD'), None)
    self.mox.ReplayAll()
    self.assertEquals(dict(rlz_brand_code='ABCD', customization_id=None),
                      self._gooftool.VerifyBranding())

  def testVerifyBranding_BrandCodeInRootFS(self):
    with file_utils.TempDirectory() as tmp:
      # Create a /opt/oem/etc/BRAND_CODE file within the fake mounted rootfs.
      rlz_brand_code_path = os.path.join(
          tmp, branding.BRAND_CODE_PATH.lstrip('/'))
      file_utils.TryMakeDirs(os.path.dirname(rlz_brand_code_path))
      with open(rlz_brand_code_path, 'w') as f:
        f.write('ABCD')

      self._SetupBrandingMocks({}, tmp)
      self.mox.ReplayAll()
      self.assertEquals(dict(rlz_brand_code='ABCD', customization_id=None),
                        self._gooftool.VerifyBranding())

  def testVerifyBranding_BadBrandCode(self):
    self._SetupBrandingMocks(dict(rlz_brand_code='ABCDx',
                                  customization_id='FOO'), None)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Bad format for rlz_brand_code',
                            self._gooftool.VerifyBranding)

  def testVerifyBranding_BadConfigurationId(self):
    self._SetupBrandingMocks(dict(rlz_brand_code='ABCD',
                                  customization_id='FOOx'), None)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Bad format for customization_id',
                            self._gooftool.VerifyBranding)

  def testCheckDevSwitchForDisabling(self):
    # 1st call: virtual switch
    self._gooftool._util.GetVBSharedDataFlags().AndReturn(0x400)

    # 2nd call: dev mode disabled
    self._gooftool._util.GetVBSharedDataFlags().AndReturn(0)
    self._gooftool._util.GetCurrentDevSwitchPosition().AndReturn(0)

    # 3rd call: dev mode enabled
    self._gooftool._util.GetVBSharedDataFlags().AndReturn(0)
    self._gooftool._util.GetCurrentDevSwitchPosition().AndReturn(1)

    self.mox.ReplayAll()
    self.assertTrue(self._gooftool.CheckDevSwitchForDisabling())
    self.assertFalse(self._gooftool.CheckDevSwitchForDisabling())
    self.assertRaises(Error, self._gooftool.CheckDevSwitchForDisabling)

  def testSetFirmwareBitmapLocalePass(self):
    '''Test for a normal process of setting firmware bitmap locale.'''

    # Stub data from VPD for en.
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())
    self._gooftool._read_ro_vpd("firmware").AndReturn(
        {'initial_locale': 'zh-TW'})
    self._gooftool._named_temporary_file().AndReturn(MockFile())
    self._gooftool._util.shell('gbb_utility -g --bmpfv=filename firmware')

    # Stub for multiple available locales in the firmware bitmap.
    self._gooftool._unpack_bmpblock('read_results').AndReturn(
        {'locales': ['ja', 'zh', 'en']})

    # Expect index = 1 for zh is matched.
    self._gooftool._util.shell('crossystem loc_idx=1')

    self.mox.ReplayAll()
    self._gooftool.SetFirmwareBitmapLocale()

  def testSetFirmwareBitmapLocaleNoMatch(self):
    """Test for setting firmware bitmap locale without matching default locale.
    """

    # Stub data from VPD for en.
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())
    self._gooftool._read_ro_vpd("firmware").AndReturn(
        {'initial_locale': 'en'})
    self._gooftool._named_temporary_file().AndReturn(MockFile())
    self._gooftool._util.shell('gbb_utility -g --bmpfv=filename firmware')

    # Stub for multiple available locales in the firmware bitmap, but missing
    # 'en'.
    self._gooftool._unpack_bmpblock('read_results').AndReturn(
        {'locales': ['ja', 'fr', 'zh']})

    self.mox.ReplayAll()
    self.assertRaises(Error, self._gooftool.SetFirmwareBitmapLocale)

  def testSetFirmwareBitmapLocaleNoVPD(self):
    '''Test for setting firmware bitmap locale without default locale in VPD.'''

    # VPD has no locale data.
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())
    self._gooftool._read_ro_vpd("firmware").AndReturn({})

    self.mox.ReplayAll()
    self.assertRaises(Error, self._gooftool.SetFirmwareBitmapLocale)

  def testGetSystemDetails(self):
    '''Test for GetSystemDetails to ensure it returns desired keys.'''

    self._gooftool._util.shell(mox.IsA(str)).MultipleTimes().AndReturn(
        StubStdout("stub_value"))
    self._gooftool._util.GetCrosSystem().AndReturn({'key':'value'})

    self.mox.ReplayAll()
    self.assertEquals(
        set(['platform_name', 'crossystem', 'modem_status', 'ec_wp_status',
         'bios_wp_status']),
        set(self._gooftool.GetSystemDetails().keys()))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
