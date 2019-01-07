#!/usr/bin/env python
# pylint: disable=protected-access
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for gooftool module."""

import __builtin__
from collections import namedtuple
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
from cros.factory.gooftool import vpd
from cros.factory.utils.type_utils import Error
from cros.factory.utils.type_utils import Obj

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

# A stub for stdout
StubStdout = namedtuple('StubStdout', ['stdout'])


class MockMainFirmware(object):
  """Mock main firmware object."""

  def __init__(self, image=None):
    self.GetFileName = lambda *args, **kwargs: 'firmware'
    self.Write = lambda filename: filename == 'firmware'
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

  _SIMPLE_VALID_RO_VPD_DATA = {
      'serial_number': 'A1234',
      'region': 'us',
  }

  _SIMPLE_VALID_RW_VPD_DATA = {
      'gbind_attribute': ('=CjAKIAABAgMEBQYHCAkKCwwNDg8QERITFBUWF'
                          'xgZGhscHR4fEAAaCmNocm9tZWJvb2sQhOfLlA8='),
      'ubind_attribute': ('=CjAKIAABAgMEBQYHCAkKCwwNDg8QERITFBUWF'
                          'xgZGhscHR4fEAEaCmNocm9tZWJvb2sQgdSQ-AI='),
      'rlz_embargo_end_date': '2018-03-09',
      'should_send_rlz_ping': '1',
  }

  def setUp(self):
    self.mox = mox.Mox()

    self._gooftool = core.Gooftool(
        hwid_version=3, project='chromebook', hwdb_path=_TEST_DATA_PATH)
    self._gooftool._util = self.mox.CreateMock(core.Util)
    self._gooftool._util.shell = self.mox.CreateMock(Shell)

    self._gooftool._crosfw = self.mox.CreateMock(crosfw)
    self._gooftool._unpack_bmpblock = self.mox.CreateMock(unpack_bmpblock)
    self._gooftool._vpd = self.mox.CreateMock(self._gooftool._vpd)
    self._gooftool._named_temporary_file = self.mox.CreateMock(
        NamedTemporaryFile)

  def tearDown(self):
    self.mox.VerifyAll()
    self.mox.UnsetStubs()

  def testVerifyECKeyWithPubkeyHash(self):
    f = MockFile()
    f.read = lambda: ''
    stub_result = lambda: None
    stub_result.success = True
    _hash = 'abcdefghijklmnopqrstuvwxyz1234567890abcd'
    futil_out = ('Public Key file:       %s\n'
                 '  Vboot API:           2.1\n'
                 '  ID:                  %s\n'
                 'Signature:             %s\n'
                 '  Vboot API:           2.1\n'
                 '  ID:                  %s\n'
                 'Signature verification succeeded.\n' % (f.name, _hash, f.name,
                                                          _hash))

    self._gooftool._named_temporary_file().AndReturn(f)
    self._gooftool._util.shell(
        'flashrom -p ec -r %s' % f.name).AndReturn(stub_result)
    self._gooftool._util.shell(
        'futility show --type rwsig %s' % f.name).AndReturn(
            Obj(stdout=futil_out, success=True))
    self._gooftool._named_temporary_file().AndReturn(f)
    self._gooftool._util.shell(
        'flashrom -p ec -r %s' % f.name).AndReturn(stub_result)
    self._gooftool._util.shell(
        'futility show --type rwsig %s' % f.name).AndReturn(
            Obj(stdout=futil_out, success=True))
    self.mox.ReplayAll()
    self._gooftool.VerifyECKey(pubkey_hash=_hash)
    self.assertRaises(Error, self._gooftool.VerifyECKey, pubkey_hash='abc123')

  def testVerifyECKeyWithPubkeyPath(self):
    f = MockFile()
    f.read = lambda: ''
    pubkey = 'key.vpubk2'
    stub_result = lambda: None
    stub_result.success = True

    self._gooftool._named_temporary_file().AndReturn(f)
    self._gooftool._util.shell(
        'flashrom -p ec -r %s' % f.name).AndReturn(stub_result)
    self._gooftool._util.shell('futility show --type rwsig --pubkey %s %s' %
                               (pubkey, f.name)).AndReturn(
                                   Obj(success=True))
    self.mox.ReplayAll()
    self._gooftool.VerifyECKey(pubkey_path=pubkey)

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

    self._gooftool._vpd.UpdateData(
        dict(stable_device_secret_DO_NOT_SHARE='00' * 32),
        partition=vpd.VPD_READONLY_PARTITION_NAME)
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
    self._gooftool._vpd.UpdateData(
        dict(stable_device_secret_DO_NOT_SHARE='00' * 32),
        partition=vpd.VPD_READONLY_PARTITION_NAME).AndRaise(Exception())
    self.mox.ReplayAll()
    self.assertRaisesRegexp(Error, 'Error writing device secret',
                            self._gooftool.GenerateStableDeviceSecret)

  def testWriteHWID(self):
    self._gooftool._crosfw.LoadMainFirmware().MultipleTimes().AndReturn(
        MockMainFirmware())
    self._gooftool._util.shell(
        'futility gbb --set --hwid="hwid1" "firmware"')
    self._gooftool._util.shell(
        'futility gbb --set --hwid="hwid2" "firmware"')

    self.mox.ReplayAll()

    self._gooftool.WriteHWID('hwid1')
    self._gooftool.WriteHWID('hwid2')

  def testVerifyWPSwitch(self):
    # 1st call: AP and EC wpsw are enabled.
    self._gooftool._util.shell('crossystem wpsw_cur').AndReturn(StubStdout('1'))
    self._gooftool._util.shell('ectool flashprotect').AndReturn(StubStdout(
        'Flash protect flags: 0x00000008 wp_gpio_asserted\nValid flags:...'))
    # 2nd call: AP wpsw is disabled.
    self._gooftool._util.shell('crossystem wpsw_cur').AndReturn(StubStdout('0'))
    # 3st call: AP wpsw is enabled but EC is disabled.
    self._gooftool._util.shell('crossystem wpsw_cur').AndReturn(StubStdout('1'))
    self._gooftool._util.shell('ectool flashprotect').AndReturn(StubStdout(
        'Flash protect flags: 0x00000000\nValid flags:...'))

    self.mox.ReplayAll()

    self._gooftool.VerifyWPSwitch()
    self.assertRaises(Error, self._gooftool.VerifyWPSwitch)
    self.assertRaises(Error, self._gooftool.VerifyWPSwitch)

  def _SetupVPDMocks(self, ro=None, rw=None):
    """Set up mocks for vpd related tests.

    Args:
      ro: The dictionary to use for the RO VPD if set.
      rw: The dictionary to use for the RW VPD if set.
    """
    if ro is not None:
      self._gooftool._vpd.GetAllData(
          partition=vpd.VPD_READONLY_PARTITION_NAME).InAnyOrder().AndReturn(ro)
    if rw is not None:
      self._gooftool._vpd.GetAllData(
          partition=vpd.VPD_READWRITE_PARTITION_NAME).InAnyOrder().AndReturn(rw)

  def testVerifyVPD_AllValid(self):
    self._SetupVPDMocks(ro=self._SIMPLE_VALID_RO_VPD_DATA,
                        rw=self._SIMPLE_VALID_RW_VPD_DATA)
    self.mox.ReplayAll()
    self._gooftool.VerifyVPD()

  def testVerifyVPD_NoRegion(self):
    ro_vpd_value = self._SIMPLE_VALID_RO_VPD_DATA.copy()
    del ro_vpd_value['region']
    self._SetupVPDMocks(ro=ro_vpd_value, rw=self._SIMPLE_VALID_RW_VPD_DATA)
    self.mox.ReplayAll()
    # Should fail, since region is missing.
    self.assertRaisesRegexp(Error, 'Missing required RO VPD values: region',
                            self._gooftool.VerifyVPD)

  def testVerifyVPD_InvalidRegion(self):
    ro_vpd_value = self._SIMPLE_VALID_RO_VPD_DATA.copy()
    ro_vpd_value['region'] = 'nonexist'
    self._SetupVPDMocks(ro=ro_vpd_value, rw=self._SIMPLE_VALID_RW_VPD_DATA)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Unknown region: "nonexist".',
                            self._gooftool.VerifyVPD)

  def testVerifyVPD_InvalidMACKey(self):
    ro_vpd_value = self._SIMPLE_VALID_RO_VPD_DATA.copy()
    ro_vpd_value['wifi_mac'] = '00:11:de:ad:be:ef'
    self._SetupVPDMocks(ro=ro_vpd_value, rw=self._SIMPLE_VALID_RW_VPD_DATA)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(KeyError,
                            'Unexpected RO VPD: wifi_mac=00:11:de:ad:be:ef.',
                            self._gooftool.VerifyVPD)

  def testVerifyVPD_InvalidRegistrationCode(self):
    rw_vpd_value = self._SIMPLE_VALID_RW_VPD_DATA.copy()
    rw_vpd_value['gbind_attribute'] = 'badvalue'
    self._SetupVPDMocks(ro=self._SIMPLE_VALID_RO_VPD_DATA, rw=rw_vpd_value)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(
        ValueError, 'gbind_attribute is invalid:', self._gooftool.VerifyVPD)

  def testVerifyVPD_InvalidTestingRegistrationCode(self):
    rw_vpd_value = self._SIMPLE_VALID_RW_VPD_DATA.copy()
    rw_vpd_value['gbind_attribute'] = (
        '=CjAKIP______TESTING_______-rhGkyZUn_'
        'zbTOX_9OQI_3EAAaCmNocm9tZWJvb2sQouDUgwQ=')
    self._SetupVPDMocks(ro=self._SIMPLE_VALID_RO_VPD_DATA, rw=rw_vpd_value)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(
        ValueError, 'gbind_attribute is invalid: ', self._gooftool.VerifyVPD)

  def testVerifyVPD_UnexpectedValues(self):
    ro_vpd_value = self._SIMPLE_VALID_RO_VPD_DATA.copy()
    ro_vpd_value['initial_locale'] = 'en-US'
    self._SetupVPDMocks(ro=ro_vpd_value, rw=self._SIMPLE_VALID_RW_VPD_DATA)
    self.mox.ReplayAll()
    self.assertRaisesRegexp(
        KeyError, 'Unexpected RO VPD: initial_locale=en-US',
        self._gooftool.VerifyVPD)

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
    self._SetupVPDMocks(ro=dict(region='tw'))

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
    self._SetupVPDMocks(ro=dict(region='tw'))

    f = MockFile()
    f.read = lambda: ''
    image_file = 'firmware'
    self._gooftool._named_temporary_file().AndReturn(f)
    self._gooftool._util.shell(
        'cbfstool %s extract -n locales -f %s -r COREBOOT'
        % (image_file, f.name))
    self._gooftool._util.shell(
        'futility gbb -g --bmpfv=%s %s' % (f.name, image_file))
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
    self._SetupVPDMocks(ro=dict(region='us'))

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
    self._SetupVPDMocks(ro={})

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
