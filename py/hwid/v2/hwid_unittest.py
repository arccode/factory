#!/usr/bin/env python2
# pylint: disable=E1101
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import os
import re
import shutil
import unittest

from contextlib import contextmanager
from tempfile import mkdtemp
from traceback import format_exc

import factory_common  # pylint: disable=unused-import

from cros.factory.gooftool.common import Shell
from cros.factory.hwid.v2 import hwid_tool
from cros.factory.utils.debug_utils import SetupLogging
from cros.factory.utils.type_utils import Error


COMPONENT_CLASSES = set([
    'audio_codec', 'battery', 'bluetooth', 'video', 'cellular', 'chassis',
    'cpu', 'display_panel', 'dram', 'ec_flash_chip', 'embedded_controller',
    'ethernet', 'flash_chip', 'region', 'storage', 'stylus', 'touchpad',
    'touchscreen', 'tpm', 'usb_hosts', 'wireless', 'pmic', 'mainboard',
])


@contextmanager
def LogOnException(test_name, *log_files):
  try:
    yield
  except Exception as e:
    regexp = r'line ([0-9]+), in %s\s*([^\n]+)\n' % test_name
    line_no, line_str = re.findall(regexp, format_exc(e), re.M)[0]
    print '------ FAILURE at %s line %s: %r' % (test_name, line_no, line_str)
    print '\n', e, '\n'
    for f in log_files:
      if os.path.exists(f):
        print '-- %s:\n%s' % (f, open(f).read())
    raise


# NOTE: While the data below is mostly realistic, it may have been
# altered or be out of date.  For example, the volatile results have
# been truncated to fit in 80 columns.
g_zgb_probe_results_str = '''
found_probe_value_map:
  audio_codec: { compact_str: 'Realtek ALC271X' }
  battery: { compact_str: 'SANYO AS10B73 Li-ion 4400000' }
  bluetooth: { compact_str: '0cf3:3005 0001' }
  mainboard: { compact_str: 'PVT' }
  cellular:
    compact_str: '05c6:9215 Qualcomm Incorporated Qualcomm Gobi2000 0002'
  chassis: { compact_str: 'custom' }
  cpu: { compact_str: 'Intel(R) Atom(TM) CPU N570 @ 1.66GHz [4 cores]' }
  display_panel: { compact_str: 'AUO:5c20 [1366x768]' }
  dram: { compact_str: '0|2048|DDR3-800,DDR3-1066,DDR3-1333' }
  ec_flash_chip: { compact_str: 'Winbond W25X40' }
  embedded_controller: { compact_str: 'nuvoton npce781' }
  ethernet: { compact_str: '0b95:772a ASIX Elec. Corp. AX88x72A 0001' }
  flash_chip: { compact_str: 'Winbond W25Q32' }
  pmic: { compact_str: '99999-pmic' }
  region: { compact_str: 'us' }
  storage: { compact_str: 'ATA SanDisk SSD P4 1 #31277232' }
  stylus: { compact_str: 'stylus' }
  touchpad: { compact_str: 'SynPS/2 Synaptics TouchPad' }
  tpm: { compact_str: '49465800:1.2.3.18' }
  usb_hosts:
  - { compact_str: '8086:27cc' }
  - { compact_str: '8086:27c8' }
  - { compact_str: '8086:27c9' }
  - { compact_str: '8086:27ca' }
  - { compact_str: '8086:27cb' }
  video:
    compact_str: '04f2:b1d8 Sonix Technology Co., Ltd. Chicony 1.3M WebCam 5582'
  wireless: { compact_str: '168c:0030' }
found_volatile_values:
  hash_gbb: { compact_str: 'gv2#af80b996717d4b35ad0fab38974dd6c249dc6be6a7f33' }
  key_recovery: { compact_str: 'kv3#9bd99a594c45b6739899a17ec29ac2289ee75463' }
  key_root: { compact_str: 'kv3#9f59876c7f7dc881f02d934786c6b7c2c17dcaac' }
  ro_ec_firmware: { compact_str: 'ev2#6067f5a021f599f4ddff8ed96ba30a2dc9d2653' }
  ro_main_firmware: { compact_str: 'mv2#58b7c3484b4ce620cba066401a3e7c39a57ed' }
initial_configs:
  rw_firmware: '9999'
missing_component_classes:
- touchscreen
'''

g_dummy_volatiles_results_str = '''
found_probe_value_map: {}
found_volatile_values:
  hash_gbb: { compact_str: 'aaaa' }
  key_recovery: { compact_str: 'bbbb' }
  key_root: { compact_str: 'cccc' }
  ro_ec_firmware: { compact_str: 'dddd' }
  ro_main_firmware: { compact_str: 'eeee' }
initial_configs: {}
missing_component_classes: []
'''

g_dummy_volatiles_alt_results_str = '''
found_probe_value_map: {}
found_volatile_values:
  hash_gbb: { compact_str: 'AAAA' }
  key_recovery: { compact_str: 'BBBB' }
  key_root: { compact_str: 'CCCC' }
  ro_ec_firmware: { compact_str: 'DDDD' }
  ro_main_firmware: { compact_str: 'EEEE' }
initial_configs: {}
missing_component_classes: []
'''


class HwidTest(unittest.TestCase):

  def setUp(self):
    path = os.path.dirname(__file__)
    self.hwid_tool_cmd = os.path.join(path, 'hwid_tool.py')
    self.dir = mkdtemp()
    self.test_log = os.path.join(self.dir, 'test_log')
    logging.shutdown()
    reload(logging)
    SetupLogging(level=logging.INFO, log_file_name=self.test_log)
    self.hwid_tool_log = os.path.join(self.dir, 'hwid_tool_log')
    comp_classes = COMPONENT_CLASSES | set(['keyboard'])
    registry = hwid_tool.ComponentRegistry(
        opaque_components={'keyboard': []},
        probeable_components=dict(
            (comp_class, {}) for comp_class in comp_classes),
        status=hwid_tool.StatusData.New())
    comp_db = hwid_tool.CompDb(registry)
    comp_db.Write(self.dir)

  def tearDown(self):
    shutil.rmtree(self.dir)

  def runTool(self, args, stdin='', show_stdout=False, assertSuccess=True):
    cmd = '%s -v 4 -l %s -p %s %s' % (
        self.hwid_tool_cmd, self.hwid_tool_log, self.dir, args)
    cmd_result = Shell(cmd, stdin=stdin)
    logging.info(cmd)
    if cmd_result.stderr:
      logging.error('stderr:\n' + cmd_result.stderr)
    if show_stdout:
      logging.info('stdout:\n' + cmd_result.stdout)
    if assertSuccess:
      self.assertTrue(cmd_result.success, 'running %r failed' % cmd)
    return cmd_result

  def testComplexRunthrough(self):
    with LogOnException(
        self._testMethodName, self.test_log, self.hwid_tool_log):
      self.runTool('create_device FOO')
      self.runTool('create_bom --board=FOO --dontcare="*" '
                   '--variant_classes keyboard')
      self.runTool('assimilate_data --board=FOO --create_bom',
                   stdin=g_zgb_probe_results_str,
                   show_stdout=True)
      hw_db = hwid_tool.HardwareDb(self.dir)
      self.assertEqual(
          len(hw_db.comp_db.probeable_components['usb_hosts']), 5,
          hw_db.comp_db.probeable_components.get('usb_hosts', None))
      self.assertEqual(len(hw_db.devices), 1, hw_db.devices.keys())
      device = hw_db.devices['FOO']
      self.assertEqual(len(device.boms), 2, device.boms.keys())
      self.assertEqual(len(device.initial_configs), 1,
                       device.initial_configs.keys())
      self.assertEqual(device.initial_configs['0'].constraints['rw_firmware'],
                       '9999', device.initial_configs['0'].constraints)
      self.runTool('create_bom --board=FOO --missing="*" -n OOGG')
      hw_db = hwid_tool.HardwareDb(self.dir)
      hw_db.comp_db.AddComponent('keyboard', comp_name='sunrex_kbd_us')
      hw_db.comp_db.Write(self.dir)
      device = hw_db.devices['FOO']
      self.assertTrue('OOGG' in device.boms, device.boms.keys())
      self.runTool('create_variant --board=FOO -c sunrex_kbd_us')
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(len(device.variants), 1, device.variants.keys())
      self.runTool('assign_variant --board=FOO --bom OOGG --variant A')
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(device.boms['OOGG'].variants, ['A'])
      self.runTool('apply_initial_config -b FOO --bom OOGG --ic 0',
                   show_stdout=True)
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(device.initial_configs['0'].enforced_for_boms,
                       ['OOGG'])
      self.runTool('set_hwid_status "FOO OOGG A-*" supported')
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      status = device.GetHwidStatus('OOGG', 'A', 'A')
      self.assertEqual(status, 'supported', status)
      self.runTool('hwid_overview', show_stdout=True)
      self.runTool('hwid_list', show_stdout=True)
      self.runTool('component_breakdown', show_stdout=True)

  def testStatusChanges(self):
    with LogOnException(
        self._testMethodName, self.test_log, self.hwid_tool_log):
      self.runTool('create_device FOO')
      hw_db = hwid_tool.HardwareDb(self.dir)
      hw_db.comp_db.AddComponent('keyboard', comp_name='sunrex_kbd_us')
      hw_db.comp_db.AddComponent('keyboard', comp_name='sunrex_kbd_gb')
      hw_db.comp_db.Write(self.dir)
      self.runTool('create_bom --board=FOO --dontcare="*" -n BAR '
                   '--variant_classes keyboard')
      self.runTool('create_variant --board=FOO -c sunrex_kbd_us')
      self.runTool('create_variant --board=FOO -c sunrex_kbd_gb')
      self.runTool('assign_variant --board=FOO --bom BAR --variant A')
      self.runTool('assign_variant --board=FOO --bom BAR --variant B')
      self.runTool('assimilate_data --board=FOO',
                   stdin=g_dummy_volatiles_results_str,
                   show_stdout=True)
      self.runTool('assimilate_data --board=FOO',
                   stdin=g_dummy_volatiles_alt_results_str,
                   show_stdout=True)
      self.runTool('set_hwid_status "FOO BAR A-*" supported')
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(device.hwid_status.supported, ['BAR A-A', 'BAR A-B'],
                       device.hwid_status.supported)
      self.runTool('set_hwid_status "FOO BAR B-B" deprecated')
      self.runTool('set_hwid_status "FOO BAR A-B" deprecated')
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(device.hwid_status.supported, ['BAR A-A'],
                       device.hwid_status.supported)
      self.assertEqual(device.hwid_status.deprecated, ['BAR *-B'],
                       device.hwid_status.deprecated)
      self.runTool('set_hwid_status "FOO BAR A-A" deprecated')
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(device.hwid_status.supported, [],
                       device.hwid_status.supported)
      self.assertEqual(device.hwid_status.deprecated, ['BAR *-B', 'BAR A-A'],
                       device.hwid_status.deprecated)
      self.runTool('set_hwid_status "FOO BAR B-A" deprecated')
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(device.hwid_status.supported, [],
                       device.hwid_status.supported)
      self.assertEqual(device.hwid_status.deprecated, ['BAR *-*'],
                       device.hwid_status.deprecated)

  def testRename(self):
    with LogOnException(
        self._testMethodName, self.test_log, self.hwid_tool_log):
      hw_db = hwid_tool.HardwareDb(self.dir)
      hw_db.comp_db.AddComponent('keyboard', comp_name='kbd_0')
      hw_db.comp_db.AddComponent('keyboard', comp_name='kbd_1')
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_0', probe_result='XXX')
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_1', probe_result='YYY')
      hw_db.comp_db.AddComponent('tpm', comp_name='tpm_0', probe_result='ZZZ')
      hw_db.comp_db.Write(self.dir)
      rename_stdin_0 = 'kbd_0 sunrex_kbd_us\n'
      self.runTool('rename_components', stdin=rename_stdin_0)
      hw_db = hwid_tool.HardwareDb(self.dir)
      self.assertEqual(hw_db.comp_db.opaque_components['keyboard'],
                       ['kbd_1', 'sunrex_kbd_us'],
                       hw_db.comp_db.opaque_components)
      variant_component_spec = hw_db.comp_db.CreateComponentSpec(
          components=['tpm_0'], dontcare=[], missing=[])
      bom_component_spec = hw_db.comp_db.CreateComponentSpec(
          components=['kbd_1', 'cpu_0', 'cpu_1'],
          dontcare=list(hw_db.comp_db.all_comp_classes -
                        set(['keyboard', 'cpu', 'tpm'])),
          missing=[])
      device = hw_db.CreateDevice('FOO')
      device.CreateVariant(variant_component_spec)
      device.CreateBom('BAR', bom_component_spec)
      hw_db.Write()
      rename_stdin_1 = (
          'kbd_1 sunrex_kbd_gb\n'
          'cpu_1 ibm_deep_blue_4\n'
          'tpm_0 nsa_spies_on_U_2000\n')
      self.runTool('rename_components', stdin=rename_stdin_1)
      hw_db = hwid_tool.HardwareDb(self.dir)
      self.assertEqual(hw_db.comp_db.opaque_components['keyboard'],
                       ['sunrex_kbd_gb', 'sunrex_kbd_us'],
                       hw_db.comp_db.opaque_components)
      self.assertEqual(sorted(hw_db.comp_db.probeable_components['cpu'].keys()),
                       ['cpu_0', 'ibm_deep_blue_4'],
                       hw_db.comp_db.probeable_components)
      self.assertTrue('FOO' in hw_db.devices, hw_db.devices.keys())
      device = hw_db.devices['FOO']
      bom = device.boms['BAR'].primary
      self.assertEqual(bom.components['cpu'], ['cpu_0', 'ibm_deep_blue_4'],
                       bom.components)
      self.assertEqual(bom.components['keyboard'], 'sunrex_kbd_gb',
                       bom.components)
      variant = device.variants['A']
      self.assertEqual(variant.components['tpm'], 'nsa_spies_on_U_2000',
                       variant.components)

  def testFilterDatabase(self):
    with LogOnException(
        self._testMethodName, self.test_log, self.hwid_tool_log):
      hw_db = hwid_tool.HardwareDb(self.dir)
      hw_db.comp_db.AddComponent('keyboard', comp_name='kbd_0')
      hw_db.comp_db.AddComponent('keyboard', comp_name='kbd_1')
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_0', probe_result='XXX')
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_1', probe_result='YYY')
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_2', probe_result='ZZZ')
      hw_db.comp_db.AddComponent('tpm', comp_name='tpm_0', probe_result='AAA')
      device = hw_db.CreateDevice('FOO')
      var_a = device.CreateVariant(hw_db.comp_db.CreateComponentSpec(
          components=['tpm_0'], dontcare=[], missing=[]))
      device.CreateBom('BAR', hw_db.comp_db.CreateComponentSpec(
          components=['kbd_1', 'cpu_0', 'cpu_1'],
          dontcare=list(hw_db.comp_db.all_comp_classes -
                        set(['keyboard', 'cpu', 'tpm'])),
          missing=[]))
      device.CreateBom('BAZ', hw_db.comp_db.CreateComponentSpec(
          components=[],
          dontcare=list(hw_db.comp_db.all_comp_classes - set(['tpm'])),
          missing=[]))
      device.AddVolatileValue('hash_gbb', 'AAA', 'v0')
      device.AddVolatileValue('key_recovery', 'BBB', 'v1')
      device.AddVolatileValue('key_root', 'CCC', 'v2')
      device.AddVolatileValue('ro_ec_firmware', 'DDD', 'v3')
      device.AddVolatileValue('ro_main_firmware', 'EEE', 'v4')
      device.AddVolatileValue('ro_main_firmware', 'FFF', 'v5')
      vol_a = device.AddVolatile({'hash_gbb': 'v0',
                                  'key_recovery': 'v1',
                                  'key_root': 'v2',
                                  'ro_ec_firmware': 'v3',
                                  'ro_main_firmware': 'v4'})
      vol_b = device.AddVolatile({'hash_gbb': 'v0',
                                  'key_recovery': 'v1',
                                  'key_root': 'v2',
                                  'ro_ec_firmware': 'v3',
                                  'ro_main_firmware': 'v5'})
      device.SetHwidStatus('BAR', var_a, vol_a, 'supported')
      device.SetHwidStatus('BAZ', var_a, vol_b, 'deprecated')
      hw_db.Write()
      self.runTool('filter_database -b FOO')
      filter_path = os.path.join(self.dir, 'filtered_db_FOO')
      f_hw_db = hwid_tool.HardwareDb(filter_path)
      f_device = f_hw_db.devices['FOO']
      self.assertEqual(f_device.boms.keys(), ['BAR'], f_device.boms.keys())
      cpu_comps = f_hw_db.comp_db.probeable_components.get('cpu', [])
      self.assertEqual(sorted(cpu_comps.keys()), ['cpu_0', 'cpu_1'], cpu_comps)
      hw_db = hwid_tool.HardwareDb(self.dir)
      hw_db.devices['FOO'].SetHwidStatus('BAZ', var_a, vol_a, 'supported')
      hw_db.Write()
      self.runTool('filter_database -b FOO')
      f_device = hwid_tool.HardwareDb(filter_path).devices['FOO']
      self.assertEqual(sorted(f_device.boms.keys()), ['BAR', 'BAZ'],
                       f_device.boms.keys())

  def testBomMatrixCreation(self):
    with LogOnException(
        self._testMethodName, self.test_log, self.hwid_tool_log):
      hw_db = hwid_tool.HardwareDb(self.dir)
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_0', probe_result='XXX')
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_1', probe_result='YYY')
      hw_db.comp_db.AddComponent('cpu', comp_name='cpu_2', probe_result='ZZZ')
      hw_db.comp_db.AddComponent('tpm', comp_name='tpm_0', probe_result='AAA')
      hw_db.comp_db.AddComponent('tpm', comp_name='tpm_1', probe_result='BBB')
      hw_db.comp_db.AddComponent('tpm', comp_name='tpm_2', probe_result='CCC')
      hw_db.comp_db.AddComponent('keyboard', comp_name='kbd_0')
      hw_db.comp_db.AddComponent('keyboard', comp_name='kbd_1')
      device = hw_db.CreateDevice('FOO')
      device.CreateBom('BAR', hw_db.comp_db.CreateComponentSpec(
          dontcare=hw_db.comp_db.all_comp_classes))
      cross_comp_classes = set(['cpu', 'tpm', 'keyboard'])
      device.CreateBom('BAZ', hw_db.comp_db.CreateComponentSpec(
          missing=hw_db.comp_db.all_comp_classes - cross_comp_classes,
          components=['cpu_0', 'tpm_0', 'kbd_0']))
      hw_db.Write()
      self.runTool('create_bom_matrix -b FOO --missing %s --cross_comps cpu_0 '
                   'cpu_1 cpu_2 tpm_0 tpm_1 tpm_2 kbd_0 kbd_1' %
                   ' '.join(hw_db.comp_db.all_comp_classes -
                            cross_comp_classes))
      device = hwid_tool.HardwareDb(self.dir).devices['FOO']
      self.assertEqual(len(device.boms), 19,
                       (len(device.boms), device.boms.keys()))


class HwidRegexpTest(unittest.TestCase):

  def _assertRegexMatches(self, regex, matched_strings, unmatched_strings):
    """Assert if regex matches correctly with given matching strings."""
    failed_to_match = [item for item in matched_strings
                       if not regex.match(item)]
    failed_to_unmatch = [item for item in unmatched_strings
                         if regex.match(item)]
    self.assertFalse(failed_to_match or failed_to_unmatch,
                     'regex %r matching test failed:\n'
                     'should match:%s\n  should NOT match:%s' % (
                         regex.pattern, failed_to_match or 'pass',
                         failed_to_unmatch or 'pass'))

  def testHwidNameRegex(self):
    parseable = [
        'TREE BLUE A-B 1234',
        'WATER YELLOW A-AA 4217',
        'STONE BLACK A-C 3547',
        'SAND 8AA-ABC A-A 1234',
        'ABCDEFGHI 123456789-123456789-123456789-12 A-A 1234',
        'CLOUD WWW-4ZZ-3MABC-2 A-AA 1234']
    unparseable = [
        'TREE A-B 9152',
        'TREE 1-B 9152',
        'TREE A-2 9152',
        'TREE A-B 19152',
        'TREE A-B A152',
        'TREE BLUE A- 4217',
        'TREE BLUE -C 3547',
        'ABCDEFGHIJ 123456789-123456789-123456789-12 A-A 1234',
        'ABCDEFGHI 123456789-123456789-123456789-123 A-A 1234',
        'SAND 8AA_ABC A-A 1234',
        'SAND 8AA.ABC A-A 1234',
        'SAND 8AA ABC A-A 1234']
    self._assertRegexMatches(hwid_tool.HWID_RE, parseable, unparseable)

  def testHwidBbvvNameRegex(self):
    """Ensure the BOM names are parsed correctly with the regular expression"""
    parseable = [
        'TREE BLUE A-B',
        'TREE BLUE *-B',
        'TREE BLUE A-*',
        'TREE BLUE *-*',
        'WATER YELLOW A-AA',
        'STONE BLACK A-C',
        'SAND 8AA-ABC A-A',
        'ABCDEFGHI 123456789-123456789-123456789-12 A-A',
        'CLOUD WWW-4ZZ-3MABC-2 A-AA']
    unparseable = [
        'TREE BLUE A-',
        'TREE BLUE A-1',
        'TREE BLUE -C',
        'TREE BLUE 1-C',
        'ABCDEFGHIJ 123456789-123456789-123456789-12 A-A',
        'ABCDEFGHI 123456789-123456789-123456789-123 A-A',
        'SAND 8AA_ABC A-A',
        'SAND 8AA.ABC A-A',
        'SAND 8AA ABC A-A']
    self._assertRegexMatches(hwid_tool.BBVV_GLOB_RE, parseable, unparseable)

  def testHwidBvvNameRegex(self):
    """Ensure the BOM names are parsed correctly with the regular expression"""
    parseable = [
        'BLUE A-B',
        'BLUE *-B',
        'BLUE A-*',
        'BLUE *-*',
        'YELLOW A-AA',
        'BLACK A-C',
        '8AA-ABC A-A',
        '123456789-123456789-123456789-12 A-A',
        'WWW-4ZZ-3MABC-2 A-AA']
    unparseable = [
        'BLUE A-',
        'BLUE A-1',
        'BLUE -C',
        'BLUE 1-C',
        '123456789-123456789-123456789-123 A-A',
        '8AA_ABC A-A',
        '8AA.ABC A-A',
        '8AA ABC A-A']
    self._assertRegexMatches(hwid_tool.BVV_GLOB_RE, parseable, unparseable)

  def testValidate(self):
    hwid_tool.Validate.BoardName('WATER')
    hwid_tool.Validate.BoardName('ABCDEFGHI')
    self.assertRaises(Error, hwid_tool.Validate.BoardName, ('WATER123'))
    self.assertRaises(Error, hwid_tool.Validate.BoardName, ('123'))
    self.assertRaises(Error, hwid_tool.Validate.BoardName, ('WATER-ABC'))
    self.assertRaises(Error, hwid_tool.Validate.BoardName, ('ABCDEFGHIJ'))

    hwid_tool.Validate.BomName('BLUE')
    hwid_tool.Validate.BomName('8AB-CEF')
    hwid_tool.Validate.BomName('888-4H4-CEF-2')
    self.assertRaises(Error, hwid_tool.Validate.BomName, ('A_B'))
    self.assertRaises(Error, hwid_tool.Validate.BomName, ('A.B'))
    self.assertRaises(Error, hwid_tool.Validate.BomName, ('ABC-ABC ABC'))

if __name__ == '__main__':
  unittest.main()
