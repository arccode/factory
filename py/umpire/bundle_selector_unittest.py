#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import Cookie
import unittest
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.bundle_selector import ParseDUTHeader
from cros.factory.umpire.bundle_selector import SelectBundle


def DutInfo(x_umpire_dut):
  """Converts X-Umpire-DUT header to DUT info dict.
  """
  dut_info = Cookie.SimpleCookie()
  dut_info.load(x_umpire_dut)
  return dict((k, v.value) for k, v in dut_info.iteritems())


class ParseDUTHeaderTest(unittest.TestCase):

  def testSingleKeyValue(self):
    self.assertDictEqual({'sn': 'SN001'}, ParseDUTHeader('sn=SN001'))
    self.assertDictEqual({'mlb_sn': 'MLB001'}, ParseDUTHeader('mlb_sn=MLB001'))
    self.assertDictEqual({'board': 'spring'}, ParseDUTHeader('board=spring'))
    self.assertDictEqual({'firmware': 'spring_1.0.1'},
                         ParseDUTHeader('firmware=spring_1.0.1'))
    self.assertDictEqual({'ec': 'spring_ec_1.0.1'},
                         ParseDUTHeader('ec=spring_ec_1.0.1'))

  def testSingleKeyPrefixValue(self):
    self.assertDictEqual({'mac': 'aa:bb:cc:dd:ee:ff'},
                         ParseDUTHeader('mac=aa:bb:cc:dd:ee:ff'))
    self.assertDictEqual({'mac.eth0': 'aa:bb:cc:dd:ee:ff'},
                         ParseDUTHeader('mac.eth0=aa:bb:cc:dd:ee:ff'))
    self.assertDictEqual({'mac.wlan0': 'aa:bb:cc:dd:ee:ff'},
                         ParseDUTHeader('mac.wlan0=aa:bb:cc:dd:ee:ff'))

  def testMultipleValues(self):
    self.assertDictEqual(
        {'mac': 'aa:bb:cc:dd:ee:ff', 'sn': 'SN001', 'mlb_sn': 'MLB001'},
        ParseDUTHeader('mac=aa:bb:cc:dd:ee:ff; sn=SN001; mlb_sn=MLB001'))

  def testInvalidKey(self):
    with self.assertRaises(ValueError):
      ParseDUTHeader('invalid_key=value')


class SelectBundleTest(unittest.TestCase):

  def testDefault(self):
    config = yaml.load("""rulesets:
- bundle_id: 'default'
  note: 'Default bundle'
  active: true""")
    self.assertEqual('default', SelectBundle(config, 'mac:aa:bb:cc:dd:ee:ff'))

  def testScalarMatcher(self):
    config = yaml.load("""rulesets:
- bundle_id: 'sn_matcher'
  active: true
  match:
    sn: ['SN001']
- bundle_id: 'mlb_sn_matcher'
  active: true
  match:
    mlb_sn: ['MLBSN001']
- bundle_id: 'for_smt'
  active: true
  match:
    stage: ['SMT']
- bundle_id: 'for_fatp'
  active: true
  match:
    stage: ['FATP']
- bundle_id: 'default'
  active: true""")
    self.assertEqual('sn_matcher', SelectBundle(config, dict(sn='SN001')))
    self.assertEqual('mlb_sn_matcher',
                     SelectBundle(config, dict(mlb_sn='MLBSN001')))

    # Both mlb_sn and sn are matched. However, first ruleset matches first.
    self.assertEqual('sn_matcher',
                     SelectBundle(config,
                                  dict(mlb_sn='MLBSN001', sn='SN001')))

    # Match stage.
    self.assertEqual('for_smt', SelectBundle(config, dict(stage='SMT')))
    self.assertEqual('for_fatp', SelectBundle(config, dict(stage='FATP')))

    # No match. Fallback to default.
    self.assertEqual('default',
                     SelectBundle(config,
                                  dict(mlb_sn='MLBSN002', sn='SN002')))

  def testScalarPrefixMatcher(self):
    config = yaml.load("""rulesets:
- bundle_id: 'ethernet_mac_matcher'
  active: true
  match:
    mac: ['aa:bb:cc:dd:ee:ff']
- bundle_id: 'wireless_mac_matcher'
  active: true
  match:
    mac: ['00:11:22:33:44:55']
- bundle_id: 'default'
  active: true""")
    self.assertEqual('ethernet_mac_matcher',
                     SelectBundle(config, {'mac': 'aa:bb:cc:dd:ee:ff'}))
    self.assertEqual('ethernet_mac_matcher',
                     SelectBundle(config, {'mac.eth0': 'aa:bb:cc:dd:ee:ff'}))
    self.assertEqual('wireless_mac_matcher',
                     SelectBundle(config, {'mac.wlan0': '00:11:22:33:44:55'}))
    # Both ethernet MAC and wireless MAC matches, first ruleset matches first.
    self.assertEqual('ethernet_mac_matcher',
                     SelectBundle(config, {'mac.eth0': 'aa:bb:cc:dd:ee:ff',
                                           'mac.wlan0': '00:11:22:33:44:55'}))
    # Only wireless MAC matches.
    self.assertEqual(
        'wireless_mac_matcher',
        SelectBundle(config,
                     DutInfo('mac.eth0=aa:bb:cc:dd:ee:00; '
                             'mac.wlan0=00:11:22:33:44:55')))

  def testInactiveMatcher(self):
    config = yaml.load("""rulesets:
- bundle_id: 'sn_matcher'
  active: false
  match:
    sn: ['SN001']
- bundle_id: 'default'
  active: true""")
    # sn_matcher is inactive.
    self.assertEqual('default', SelectBundle(config, dict(sn='SN001')))

  def testNotMatchedScalarMatcher(self):
    config = yaml.load("""rulesets:
- bundle_id: 'sn_matcher'
  active: true
  match:
    sn: ['SN001']
- bundle_id: 'mac_matcher'
  active: true
  match:
    mac: ['aa:bb:cc:dd:ee:ff']""")
    self.assertEqual(None,
                     SelectBundle(config, dict(sn='SN002')))

  def testSnRangeMatcher(self):
    config = yaml.load("""rulesets:
- bundle_id: 'sn_range_001_005'
  active: true
  match:
    sn_range: ['SN001', 'SN005']
- bundle_id: 'sn_range_open_010'
  active: true
  match:
    sn_range: ['-', 'SN010']
- bundle_id: 'sn_range_020_open'
  active: true
  match:
    sn_range: ['SN020', '-']""")
    self.assertEqual('sn_range_001_005',
                     SelectBundle(config, dict(sn='SN001')))
    self.assertEqual('sn_range_001_005',
                     SelectBundle(config, dict(sn='SN003')))
    self.assertEqual('sn_range_001_005',
                     SelectBundle(config, dict(sn='SN004')))

    # sn_range ['-', 'SN010'] matches sn <= 'SN010'.
    self.assertEqual('sn_range_open_010',
                     SelectBundle(config, dict(sn='SN000')))
    self.assertEqual('sn_range_open_010',
                     SelectBundle(config, dict(sn='SN006')))
    self.assertEqual('sn_range_open_010',
                     SelectBundle(config, dict(sn='SN010')))
    self.assertEqual(None,
                     SelectBundle(config, dict(sn='SN011')))

    # sn_range ['SN020', '-'] matches sn >= 'SN020'.
    self.assertEqual('sn_range_020_open',
                     SelectBundle(config, dict(sn='SN020')))
    self.assertEqual('sn_range_020_open',
                     SelectBundle(config, dict(sn='SN100')))
    self.assertEqual(None,
                     SelectBundle(config, dict(sn='SN011')))

  def testMlbSnRangeMatcher(self):
    config = yaml.load("""rulesets:
- bundle_id: 'mlb_sn_range_001_005'
  active: true
  match:
    mlb_sn_range: ['MLBSN001', 'MLBSN005']
- bundle_id: 'mlb_sn_range_open_010'
  active: true
  match:
    mlb_sn_range: ['-', 'MLBSN010']
- bundle_id: 'mlb_sn_range_020_open'
  active: true
  match:
    mlb_sn_range: ['MLBSN020', '-']""")
    self.assertEqual('mlb_sn_range_001_005',
                     SelectBundle(config, dict(mlb_sn='MLBSN001')))
    self.assertEqual('mlb_sn_range_001_005',
                     SelectBundle(config, dict(mlb_sn='MLBSN003')))
    self.assertEqual('mlb_sn_range_001_005',
                     SelectBundle(config, dict(mlb_sn='MLBSN004')))

    # mlb_sn_range ['-', 'MLBSN010'] matches sn <= 'MLBSN010'.
    self.assertEqual('mlb_sn_range_open_010',
                     SelectBundle(config, dict(mlb_sn='MLBSN000')))
    self.assertEqual('mlb_sn_range_open_010',
                     SelectBundle(config, dict(mlb_sn='MLBSN006')))
    self.assertEqual('mlb_sn_range_open_010',
                     SelectBundle(config, dict(mlb_sn='MLBSN010')))
    self.assertEqual(None,
                     SelectBundle(config, dict(mlb_sn='MLBSN011')))

    # mlb_sn_range ['MLBSN020', '-'] matches sn >= 'MLBSN020'.
    self.assertEqual('mlb_sn_range_020_open',
                     SelectBundle(config, dict(mlb_sn='MLBSN020')))
    self.assertEqual('mlb_sn_range_020_open',
                     SelectBundle(config, dict(mlb_sn='MLBSN100')))
    self.assertEqual(None,
                     SelectBundle(config, dict(mlb_sn='MLBSN011')))

  def testMultipleScalarMatcher(self):
    config = yaml.load("""rulesets:
- bundle_id: 'sn_and_mac_matcher'
  active: true
  match:
    sn: ['SN001']
    mac: ['aa:bb:cc:dd:ee:ff']
- bundle_id: 'sn_matcher'
  active: true
  match:
    sn: ['SN001', 'SN002']""")
    self.assertEqual('sn_and_mac_matcher',
                     SelectBundle(config, dict(sn='SN001',
                                               mac='aa:bb:cc:dd:ee:ff')))
    # mac mismatch.
    self.assertEqual('sn_matcher',
                     SelectBundle(config, dict(sn='SN001',
                                               mac='aa:bb:cc:dd:ee:00')))
    # sn mismatch
    self.assertEqual('sn_matcher',
                     SelectBundle(config, dict(sn='SN002',
                                               mac='aa:bb:cc:dd:ee:ff')))


if __name__ == '__main__':
  unittest.main()
