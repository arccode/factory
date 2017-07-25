#!/usr/bin/python
# pylint: disable=protected-access
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for gooftool module."""

import __builtin__
from collections import namedtuple
from contextlib import contextmanager
import logging
import os
from StringIO import StringIO
from tempfile import NamedTemporaryFile
import time
import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.gooftool.bmpblk import unpack_bmpblock
from cros.factory.gooftool.common import Shell
from cros.factory.gooftool import core
from cros.factory.gooftool import crosfw
from cros.factory.gooftool import probe
from cros.factory.gooftool.probe import Probe
from cros.factory.gooftool.probe import ReadRoVpd
from cros.factory.hwid.v2 import hwid_tool
# pylint: disable=no-name-in-module
from cros.factory.hwid.v2.hwid_tool import ProbeResults
from cros.factory.test.rules import branding
from cros.factory.utils import file_utils
from cros.factory.utils.type_utils import Error
from cros.factory.utils.type_utils import Obj

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

# A stub for stdout
StubStdout = namedtuple('StubStdout', ['stdout'])


class MockMainFirmware(object):
  """Mock main firmware object."""

  def __init__(self, image=None):
    self.GetFileName = lambda: 'firmware'
    self.Write = lambda sections: sections == ['GBB']
    self.GetFirmwareImage = lambda: image


class MockFirmwareImage(object):
  """Mock firmware image object."""

  def __init__(self, section_map):
    self.has_section = lambda name: name in section_map
    self.get_section = lambda name: section_map[name]


class MockFile(object):
  """Mock file object."""

  def __init__(self):
    self.name = 'filename'
    self.read = lambda: 'read_results'

  def __enter__(self):
    return self

  def __exit__(self, filetype, value, traceback):
    pass


class UtilTest(unittest.TestCase):
  """Unit test for core.Util."""

  def setUp(self):
    self.mox = mox.Mox()

    self._util = core.Util()

    # Mock out small wrapper functions that do not need unittests.
    self._util.shell = self.mox.CreateMock(Shell)
    self.mox.StubOutWithMock(self._util, '_IsDeviceFixed')
    self.mox.StubOutWithMock(self._util, 'FindScript')

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testGetPrimaryDevicePath(self):
    """Test for GetPrimaryDevice."""

    self._util._IsDeviceFixed(
        'sda').MultipleTimes().AndReturn(True)

    self._util.shell('rootdev -s -d').MultipleTimes().AndReturn(
        StubStdout('/dev/sda'))

    self.mox.ReplayAll()

    self.assertEquals('/dev/sda', self._util.GetPrimaryDevicePath())
    self.assertEquals('/dev/sda1', self._util.GetPrimaryDevicePath(1))
    self.assertEquals('/dev/sda2', self._util.GetPrimaryDevicePath(2))

    # also test thin callers
    self.assertEquals('/dev/sda5', self._util.GetReleaseRootPartitionPath())
    self.assertEquals('/dev/sda4', self._util.GetReleaseKernelPartitionPath())

  def testGetPrimaryDevicePathNotFixed(self):
    """Test for GetPrimaryDevice when multiple primary devices are found."""

    self._util._IsDeviceFixed(
        'sda').MultipleTimes().AndReturn(False)

    self._util.shell('rootdev -s -d').AndReturn(
        StubStdout('/dev/sda'))

    self.mox.ReplayAll()

    self.assertRaises(Error, self._util.GetPrimaryDevicePath)

  def testFindRunScript(self):
    self._util.FindScript(mox.IsA(str)).MultipleTimes().AndReturn('script')

    stub_result = lambda: None
    stub_result.success = True
    self._util.shell('script').AndReturn(stub_result)  # option = []
    self._util.shell('script').AndReturn(stub_result)  # option = None
    self._util.shell('script a').AndReturn(stub_result)
    self._util.shell('script a b').AndReturn(stub_result)
    self._util.shell('c=d script a b').AndReturn(stub_result)
    self._util.shell('c=d script').AndReturn(stub_result)

    self.mox.ReplayAll()

    self._util.FindAndRunScript('script')
    self._util.FindAndRunScript('script', None)
    self._util.FindAndRunScript('script', ['a'])
    self._util.FindAndRunScript('script', ['a', 'b'])
    self._util.FindAndRunScript('script', ['a', 'b'], ['c=d'])
    self._util.FindAndRunScript('script', None, ['c=d'])

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

    self._gooftool = core.Gooftool(probe=self._mock_probe, hardware_db=test_db)
    self._gooftool._util = self.mox.CreateMock(core.Util)
    self._gooftool._util.shell = self.mox.CreateMock(Shell)
    probe.Shell = self.mox.CreateMock(Shell)

    self._gooftool._crosfw = self.mox.CreateMock(crosfw)
    self._gooftool._unpack_bmpblock = self.mox.CreateMock(unpack_bmpblock)
    self._gooftool._read_ro_vpd = self.mox.CreateMock(ReadRoVpd)
    self._gooftool._named_temporary_file = self.mox.CreateMock(
        NamedTemporaryFile)

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testVerifyComponents(self):
    """Test if the Gooftool.VerifyComponent() works properly.

    This test tries to probe three components [camera, battery, cpu], where
      'camera' returns a valid result.
      'battery' returns a false result.
      'cpu' does not return any result.
      'tpm' returns multiple results.
    """

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

  def testVerifyKey(self):
    self._gooftool._util.GetReleaseKernelPathFromRootPartition(
        '/dev/null').AndReturn('/dev/zero')
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware(
        MockFirmwareImage({'GBB': 'GBB', 'FW_MAIN_A': 'MA', 'FW_MAIN_B': 'MB',
                           'VBLOCK_A': 'VA', 'VBLOCK_B': 'VB'})))
    # TODO(hungte) Improve unit test scope.
    def fake_tmpexc(*unused_args, **unused_kargs):
      return ''

    self.mox.ReplayAll()
    self._gooftool.VerifyKeys('/dev/null', _tmpexec=fake_tmpexc)

  def testVerifySystemTime(self):
    self._gooftool._util.GetReleaseRootPartitionPath().AndReturn('root')
    self._gooftool._util.shell('dumpe2fs -h root').AndReturn(
        Obj(stdout='Filesystem created:     Mon Jan 25 16:13:18 2016\n',
            success=True))
    self._gooftool._util.shell('dumpe2fs -h root').AndReturn(
        Obj(stdout='Filesystem created:     Mon Jan 25 16:13:18 2016\n',
            success=True))

    self.mox.ReplayAll()
    bad_system_time = time.mktime(time.strptime('Sun Jan 24 15:00:00 2016'))
    good_system_time = time.mktime(time.strptime('Tue Jan 26 15:00:00 2016'))

    self._gooftool.VerifySystemTime(system_time=good_system_time)
    self.assertRaises(Error, self._gooftool.VerifySystemTime,
                      release_rootfs='root', system_time=bad_system_time)

  def testVerifyRootFs(self):
    fake_attrs = {'test': 'value'}
    self._gooftool._util.GetPartitionDevice('root3').AndReturn('root')
    self._gooftool._util.GetCgptAttributes('root').AndReturn(fake_attrs)
    self._gooftool._util.InvokeChromeOSPostInstall('root3')
    self._gooftool._util.SetCgptAttributes(fake_attrs, 'root').AndReturn(None)

    self.mox.ReplayAll()
    self._gooftool.VerifyRootFs('root3')

  def testVerifyTPM(self):
    # Mock os.path.exists to ensure that 3.18+ kernel TPM path does not exist.
    self.mox.StubOutWithMock(os.path, 'exists')
    self.mox.StubOutWithMock(__builtin__, 'open')
    os.path.exists('/sys/class/tpm/tpm0/device').AndReturn(False)
    open('/sys/class/misc/tpm0/device/enabled').AndReturn(StringIO('1'))
    open('/sys/class/misc/tpm0/device/owned').AndReturn(StringIO('0'))
    os.path.exists('/sys/class/tpm/tpm0/device').AndReturn(False)
    open('/sys/class/misc/tpm0/device/enabled').AndReturn(StringIO('1'))
    open('/sys/class/misc/tpm0/device/owned').AndReturn(StringIO('1'))
    self.mox.ReplayAll()
    self._gooftool.VerifyTPM()
    self.assertRaises(Error, self._gooftool.VerifyTPM)

  def testVerifyManagementEngineLocked(self):
    data_no_me = {'RO_SECTION': ''}
    data_me_locked = {'SI_ME': chr(0xff) * 1024}
    data_me_unlocked = {'SI_ME': chr(0x55) * 1024}
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(
        MockMainFirmware(MockFirmwareImage(data_no_me)))
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(
        MockMainFirmware(MockFirmwareImage(data_me_locked)))
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(
        MockMainFirmware(MockFirmwareImage(data_me_unlocked)))
    self.mox.ReplayAll()
    self._gooftool.VerifyManagementEngineLocked()
    self._gooftool.VerifyManagementEngineLocked()
    self.assertRaises(Error, self._gooftool.VerifyManagementEngineLocked)

  def testClearGBBFlags(self):
    command = '/usr/share/vboot/bin/set_gbb_flags.sh 0 2>&1'
    self._gooftool._util.shell(command).AndReturn(Obj(success=True))
    self._gooftool._util.shell(command).AndReturn(
        Obj(stdout='Fail', success=False))
    self.mox.ReplayAll()
    self._gooftool.ClearGBBFlags()
    self.assertRaises(Error, self._gooftool.ClearGBBFlags)

  def testGenerateStableDeviceSecretSuccess(self):
    self._gooftool._util.GetReleaseImageVersion().AndReturn('6887.0.0')
    self._gooftool._util.shell(
        'tpm-manager get_random 32', log=False).AndReturn(
            StubStdout('00' * 32 + '\n'))

    stub_result = lambda: None
    stub_result.success = True
    probe.Shell(
        'vpd -i RO_VPD -s "stable_device_secret_DO_NOT_SHARE"="%s"' %
        ('00' * 32)).AndReturn(stub_result)
    self.mox.ReplayAll()
    self._gooftool.GenerateStableDeviceSecret()

  def testGenerateStableDeviceSecretNoOutput(self):
    self._gooftool._util.GetReleaseImageVersion().AndReturn('6887.0.0')
    self._gooftool._util.shell(
        'tpm-manager get_random 32', log=False).AndReturn(StubStdout(''))
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error, 'Error validating device secret',
                            self._gooftool.GenerateStableDeviceSecret)

  def testGenerateStableDeviceSecretShortOutput(self):
    self._gooftool._util.GetReleaseImageVersion().AndReturn('6887.0.0')
    self._gooftool._util.shell(
        'tpm-manager get_random 32', log=False).AndReturn(StubStdout('00' * 31))
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error, 'Error validating device secret',
                            self._gooftool.GenerateStableDeviceSecret)

  def testGenerateStableDeviceSecretBadOutput(self):
    self._gooftool._util.GetReleaseImageVersion().AndReturn('6887.0.0')
    self._gooftool._util.shell(
        'tpm-manager get_random 32', log=False).AndReturn(StubStdout('Err0r!'))
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error, 'Error validating device secret',
                            self._gooftool.GenerateStableDeviceSecret)

  def testGenerateStableDeviceSecretBadReleaseImageVersion(self):
    self._gooftool._util.GetReleaseImageVersion().AndReturn('6886.0.0')
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error, 'Release image version',
                            self._gooftool.GenerateStableDeviceSecret)

  def testGenerateStableDeviceSecretVPDWriteFailed(self):
    self._gooftool._util.GetReleaseImageVersion().AndReturn('6887.0.0')
    self._gooftool._util.shell(
        'tpm-manager get_random 32', log=False).AndReturn(
            StubStdout('00' * 32 + '\n'))
    stub_result = lambda: None
    stub_result.success = False
    probe.Shell(
        'vpd -i RO_VPD -s "stable_device_secret_DO_NOT_SHARE"="%s"' %
        ('00' * 32)).AndReturn(stub_result)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error, 'Error writing device secret',
                            self._gooftool.GenerateStableDeviceSecret)

  def testWriteHWID(self):
    self._gooftool._crosfw.LoadMainFirmware().MultipleTimes().AndReturn(
        MockMainFirmware())
    self._gooftool._util.shell('gbb_utility --set --hwid="hwid1" "firmware"')
    self._gooftool._util.shell('gbb_utility --set --hwid="hwid2" "firmware"')

    self.mox.ReplayAll()

    self._gooftool.WriteHWID('hwid1')
    self._gooftool.WriteHWID('hwid2')

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

    self.mox.StubOutWithMock(core.sys_utils, 'MountPartition')

    self._gooftool._read_ro_vpd().AndReturn(ro_vpd)
    if fake_rootfs_path:
      # Pretend that '/dev/rel' is the release rootfs path.
      self._gooftool._util.GetReleaseRootPartitionPath().AndReturn('/dev/rel')
      # When '/dev/rel' is mounted, return a context manager yielding
      # fake_rootfs_path.
      core.sys_utils.MountPartition('/dev/rel').AndReturn(
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

  def testVerifyReleaseChannel_CanaryChannel(self):
    self._gooftool._util.GetReleaseImageChannel().AndReturn('canary-channel')
    self._gooftool._util.GetAllowedReleaseImageChannels().AndReturn(
        ['dev', 'beta', 'stable'])
    self.mox.ReplayAll()
    self.assertRaisesRegexp(
        Error, 'Release image channel is incorrect: canary-channel',
        self._gooftool.VerifyReleaseChannel)

  def testVerifyReleaseChannel_DevChannel(self):
    self._gooftool._util.GetReleaseImageChannel().AndReturn('dev-channel')
    self._gooftool._util.GetAllowedReleaseImageChannels().AndReturn(
        ['dev', 'beta', 'stable'])
    self.mox.ReplayAll()
    self._gooftool.VerifyReleaseChannel()

  def testVerifyReleaseChannel_DevChannelFailed(self):
    self._gooftool._util.GetReleaseImageChannel().AndReturn('dev-channel')
    self._gooftool._util.GetAllowedReleaseImageChannels().AndReturn(
        ['dev', 'beta', 'stable'])
    enforced_channels = ['stable', 'beta']
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error,
                            'Release image channel is incorrect: dev-channel',
                            self._gooftool.VerifyReleaseChannel,
                            enforced_channels)

  def testVerifyReleaseChannel_BetaChannel(self):
    self._gooftool._util.GetReleaseImageChannel().AndReturn('beta-channel')
    self._gooftool._util.GetAllowedReleaseImageChannels().AndReturn(
        ['dev', 'beta', 'stable'])
    self.mox.ReplayAll()
    self._gooftool.VerifyReleaseChannel()

  def testVerifyReleaseChannel_BetaChannelFailed(self):
    self._gooftool._util.GetReleaseImageChannel().AndReturn('beta-channel')
    self._gooftool._util.GetAllowedReleaseImageChannels().AndReturn(
        ['dev', 'beta', 'stable'])
    enforced_channels = ['stable']
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error,
                            'Release image channel is incorrect: beta-channel',
                            self._gooftool.VerifyReleaseChannel,
                            enforced_channels)

  def testVerifyReleaseChannel_StableChannel(self):
    self._gooftool._util.GetReleaseImageChannel().AndReturn('stable-channel')
    self._gooftool._util.GetAllowedReleaseImageChannels().AndReturn(
        ['dev', 'beta', 'stable'])
    self.mox.ReplayAll()
    self._gooftool.VerifyReleaseChannel()

  def testVerifyReleaseChannel_InvalidEnforcedChannels(self):
    self._gooftool._util.GetReleaseImageChannel().AndReturn('stable-channel')
    self._gooftool._util.GetAllowedReleaseImageChannels().AndReturn(
        ['dev', 'beta', 'stable'])
    enforced_channels = ['canary']
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error,
                            r'Enforced channels are incorrect: \[\'canary\'\].',
                            self._gooftool.VerifyReleaseChannel,
                            enforced_channels)

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
    """Test for a normal process of setting firmware bitmap locale."""

    # Stub data from VPD for zh.
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())
    self._gooftool._read_ro_vpd().AndReturn({'region': 'tw'})

    f = MockFile()
    f.read = lambda: 'ja\nzh\nen'
    image_file = 'firmware'
    self._gooftool._named_temporary_file().AndReturn(f)
    self._gooftool._util.shell(
        'cbfstool %s extract -n locales -f %s -r COREBOOT' %
        (image_file, f.name))

    # Expect index = 1 for zh is matched.
    self._gooftool._util.shell('crossystem loc_idx=1')

    self.mox.ReplayAll()
    self._gooftool.SetFirmwareBitmapLocale()

  def testSetFirmwareBitmapLocaleNoCbfs(self):
    """Test for legacy firmware, which stores locale in bmpblk."""

    # Stub data from VPD for zh.
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())
    self._gooftool._read_ro_vpd().AndReturn({'region': 'tw'})

    f = MockFile()
    f.read = lambda: ''
    image_file = 'firmware'
    self._gooftool._named_temporary_file().AndReturn(f)
    self._gooftool._util.shell(
        'cbfstool %s extract -n locales -f %s -r COREBOOT'
        % (image_file, f.name))
    self._gooftool._util.shell(
        'gbb_utility -g --bmpfv=%s %s' % (f.name, image_file))
    self._gooftool._unpack_bmpblock(f.read()).AndReturn(
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
    self._gooftool._read_ro_vpd().AndReturn({'region': 'us'})

    f = MockFile()
    # Stub for multiple available locales in the firmware bitmap, but missing
    # 'en'.
    f.read = lambda: 'ja\nzh\nfr'
    image_file = 'firmware'
    self._gooftool._named_temporary_file().AndReturn(f)
    self._gooftool._util.shell(
        'cbfstool %s extract -n locales -f %s -r COREBOOT' %
        (image_file, f.name))

    self.mox.ReplayAll()
    self.assertRaises(Error, self._gooftool.SetFirmwareBitmapLocale)

  def testSetFirmwareBitmapLocaleNoVPD(self):
    """Test for setting firmware bitmap locale without default locale in VPD."""

    # VPD has no locale data.
    self._gooftool._crosfw.LoadMainFirmware().AndReturn(MockMainFirmware())
    self._gooftool._read_ro_vpd().AndReturn({})

    self.mox.ReplayAll()
    self.assertRaises(Error, self._gooftool.SetFirmwareBitmapLocale)

  def testGetSystemDetails(self):
    """Test for GetSystemDetails to ensure it returns desired keys."""

    self._gooftool._util.shell(mox.IsA(str)).MultipleTimes().AndReturn(
        StubStdout('stub_value'))
    self._gooftool._util.GetCrosSystem().AndReturn({'key': 'value'})

    self.mox.ReplayAll()
    self.assertEquals(
        set(['platform_name', 'crossystem', 'modem_status', 'ec_wp_status',
             'bios_wp_status']),
        set(self._gooftool.GetSystemDetails().keys()))


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest.main()
