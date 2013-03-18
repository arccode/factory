#!/usr/bin/python
# pylint: disable=W0212
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import logging
import mox
import os
import unittest2
import yaml

from collections import namedtuple
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
from cros.factory.hwid import HWIDException
from cros.factory.gooftool import Mismatch
from cros.factory.gooftool import ProbedComponentResult

_TEST_DATA_PATH = os.path.join(os.path.dirname(__file__), 'testdata')

# A stub for stdout
StubStdout = namedtuple('StubStdout', ['stdout'])

class MockMainFirmware(object):
  def __init__(self):
    self.GetFileName = lambda: "firmware"
    self.Write = lambda sections: sections == ['GBB']

class MockFile(object):
  def __init__(self):
    self.name = 'filename'
    self.read = lambda: "read_results"
  def __enter__(self):
    return self
  def __exit__(self, filetype, value, traceback):
    pass

class UtilTest(unittest2.TestCase):
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


class GooftoolTest(unittest2.TestCase):
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

    self._gooftool3 = Gooftool(probe=self._mock_probe, hwid_version=3,
                              board='TEST_BOARD', hwdb_path=_TEST_DATA_PATH)
    self._gooftool3._util = self.mox.CreateMock(gooftool.Util)
    self._gooftool3._util.shell = self.mox.CreateMock(Shell)

    self._gooftool3._crosfw = self.mox.CreateMock(crosfw)
    self._gooftool3._unpack_bmpblock = self.mox.CreateMock(unpack_bmpblock)
    self._gooftool3._read_ro_vpd = self.mox.CreateMock(ReadRoVpd)
    self._gooftool3._named_temporary_file = self.mox.CreateMock(
        NamedTemporaryFile)

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

  def testVerifyComponentsV3(self):
    '''Test if the Gooftool.VerifyComponent() works properly.

    This test tries to probe four components [bluetooth, battery, cpu,
    audio_codec], where
      'bluetooth' returns a valid result.
      'battery' returns a false result.
      'cpu' does not return any result.
      'audio_codec' returns multiple results.
    '''

    self._mock_probe(
        probe_initial_config=False,
        probe_volatile=False,
        target_comp_classes=['bluetooth', 'battery', 'cpu', 'audio_codec']
        ).AndReturn(
            ProbeResults(
                found_probe_value_map={
                    'bluetooth': '0123:abcd 0001',
                    'battery': 'fake value',
                    'audio_codec': ['Codec 1', 'HDMI 1', 'fake value']},
                missing_component_classes=[],
                found_volatile_values={},
                initial_configs={}))

    self.mox.ReplayAll()

    self.assertEquals(
        {'bluetooth': [('bluetooth_0', '0123:abcd 0001', None)],
         'battery': [(None, 'fake value', mox.IsA(str))],
         'cpu': [(None, None, mox.IsA(str))],
         'audio_codec': [('codec_1', 'Codec 1', None),
                         ('hdmi_1', 'HDMI 1', None),
                         (None, 'fake value', mox.IsA(str))]},
        self._gooftool3.VerifyComponentsV3(
            ['bluetooth', 'battery', 'cpu', 'audio_codec']))

  def testVerifyBadComponents3(self):
    self._mock_probe(
        probe_initial_config=False,
        probe_volatile=False,
        target_comp_classes='cpu').AndReturn(
            ProbeResults(
                found_probe_value_map={},
                missing_component_classes=[],
                found_volatile_values={},
                initial_configs={}))
    self._mock_probe(
        probe_initial_config=False,
        probe_volatile=False,
        target_comp_classes=['cpu', 'bad_class_name']).AndReturn(
            ProbeResults(
                found_probe_value_map={},
                missing_component_classes=[],
                found_volatile_values={},
                initial_configs={}))

    self.mox.ReplayAll()

    self.assertRaises(HWIDException, self._gooftool3.VerifyComponentsV3, 'cpu')
    self.assertRaises(HWIDException, self._gooftool3.VerifyComponentsV3,
                      ['cpu', 'bad_class_name'])

  def testGenerateHwidV3(self):
    mock_device_info = {
        'component.has_cellular': 'n',
        'component.keyboard': 'us',
    }
    with open(os.path.join(_TEST_DATA_PATH, 'test_probe_result.yaml')) as f:
      # pylint: disable=E1101
      mock_probe_result = hwid_tool.ProbeResults.Decode(f.read())
    self.assertEquals(
        'CHROMEBOOK A5AU-LU 3324',
        self._gooftool3.GenerateHwidV3(
            mock_device_info, mock_probe_result).encoded_string)

    mock_device_info = {
        'component.has_cellular': 'y',
        'component.keyboard': 'gb'
    }
    self.assertEquals(
        'CHROMEBOOK A7IU-YS 5271',
        self._gooftool3.GenerateHwidV3(
            mock_device_info, mock_probe_result).encoded_string)
    mock_device_info = {
        'component.has_cellular': 'y'
    }
    self.assertRaisesRegexp(
        Error, r'Components .* are unprobeable and were not specified in '
        'device info', self._gooftool3.GenerateHwidV3, mock_device_info,
        mock_probe_result)
    mock_device_info = {
        'component.foo': 'bar'
    }
    self.assertRaisesRegexp(
        KeyError, r"Unexpected key 'component\.foo'",
        self._gooftool3.GenerateHwidV3, mock_device_info, mock_probe_result)

  def testVerifyHwidV3(self):
    sample_probe_result = yaml.load(open(os.path.join(
        _TEST_DATA_PATH, 'test_probe_result.yaml')).read())
    sample_ro_vpd = {
      'vpd_ro_field_1': 'VPD_RO_FIELD_1',
      'vpd_ro_field_2': 'VPD_RO_FIELD_2'
    }
    sample_rw_vpd = {
      'vpd_rw_field_1': 'VPD_RW_FIELD_1',
      'vpd_rw_field_2': 'VPD_RW_FIELD_2'
    }
    mock_probe_result = copy.deepcopy(sample_probe_result)
    mock_ro_vpd = copy.deepcopy(sample_ro_vpd)
    mock_rw_vpd = copy.deepcopy(sample_rw_vpd)
    # pylint: disable=E1101
    self.assertEquals(
        None, self._gooftool3.VerifyHwidV3(
            'CHROMEBOOK A5AU-LU 3324',
            hwid_tool.ProbeResults.Decode(yaml.dump(mock_probe_result)),
            mock_ro_vpd, mock_rw_vpd))
    mock_probe_result = copy.deepcopy(sample_probe_result)
    mock_ro_vpd = copy.deepcopy(sample_ro_vpd)
    mock_rw_vpd = copy.deepcopy(sample_rw_vpd)
    del mock_ro_vpd['vpd_ro_field_1']
    # pylint: disable=E1101
    self.assertRaisesRegexp(
        Error, r'Missing required RO VPD field: .*',
        self._gooftool3.VerifyHwidV3, 'CHROMEBOOK A5AU-LU 3324',
        hwid_tool.ProbeResults.Decode(yaml.dump(mock_probe_result)),
        mock_ro_vpd, mock_rw_vpd)
    mock_probe_result = copy.deepcopy(sample_probe_result)
    mock_ro_vpd = copy.deepcopy(sample_ro_vpd)
    mock_rw_vpd = copy.deepcopy(sample_rw_vpd)
    del mock_rw_vpd['vpd_rw_field_1']
    # pylint: disable=E1101
    self.assertRaisesRegexp(
        Error, r'Missing required RW VPD field: .*',
        self._gooftool3.VerifyHwidV3, 'CHROMEBOOK A5AU-LU 3324',
        hwid_tool.ProbeResults.Decode(yaml.dump(mock_probe_result)),
        mock_ro_vpd, mock_rw_vpd)
    mock_probe_result = copy.deepcopy(sample_probe_result)
    mock_ro_vpd = copy.deepcopy(sample_ro_vpd)
    mock_rw_vpd = copy.deepcopy(sample_rw_vpd)
    mock_probe_result['found_probe_value_map']['audio_codec'][1] = 'HDMI 2'
    # pylint: disable=E1101
    self.assertRaisesRegexp(
        HWIDException, r'Component class .* has extra components: .* and '
        'missing components: .*', self._gooftool3.VerifyHwidV3,
        'CHROMEBOOK A5AU-LU 3324',
        hwid_tool.ProbeResults.Decode(yaml.dump(mock_probe_result)),
        mock_ro_vpd, mock_rw_vpd)
    mock_probe_result = copy.deepcopy(sample_probe_result)
    mock_ro_vpd = copy.deepcopy(sample_ro_vpd)
    mock_rw_vpd = copy.deepcopy(sample_rw_vpd)
    mock_probe_result['found_probe_value_map']['cellular'] = (
        '89ab:abcd Cellular Card')
    mock_probe_result['missing_component_classes'].remove('cellular')
    # pylint: disable=E1101
    self.assertRaisesRegexp(
        HWIDException, r'Component class .* has extra components: .* and '
        'missing components: .*', self._gooftool3.VerifyHwidV3,
        'CHROMEBOOK A5AU-LU 3324',
        hwid_tool.ProbeResults.Decode(yaml.dump(mock_probe_result)),
        mock_ro_vpd, mock_rw_vpd)

if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  unittest2.main()
