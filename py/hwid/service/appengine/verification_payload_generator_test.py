#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

from six import assertCountEqual

# pylint: disable=import-error, no-name-in-module
from google.protobuf import json_format
from google.protobuf import text_format
import hardware_verifier_pb2

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import verification_payload_generator
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import rule as hwid_rule
from cros.factory.utils import json_utils


TESTDATA_DIR = os.path.join(
    os.path.dirname(__file__), 'testdata', 'verification_payload_generator')


NotSuitableError = (
    verification_payload_generator.ProbeStatementGeneratorNotSuitableError)


class GenericBatteryProbeStatementGeneratorTest(unittest.TestCase):
  TARGET_CLS = (
      verification_payload_generator.GenericBatteryProbeStatementGenerator)

  def testTryGenerate(self):
    ps = self.TARGET_CLS.TryGenerate(
        {'manufacturer': 'foo',
         'model_name': hwid_rule.Value('bar', is_re=True),
         'other_value': 'z'})
    self.assertEqual(ps, {'eval': {'generic_battery': {}},
                          'expect': {'manufacturer': [True, 'str', '!eq foo'],
                                     'model_name': [True, 'str', '!re bar']}})

    # Should report not supported if some fields are missing.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'manufacturer': 'foo'})


class GenericStorageMMCProbeStatementGeneratorTest(unittest.TestCase):
  TARGET_CLS = (
      verification_payload_generator.GenericStorageMMCProbeStatementGenerator)

  def testTryGenerate(self):
    ps = self.TARGET_CLS.TryGenerate(
        {'sectors': '112233', 'name': 'ABCxyz', 'manfid': '0x001122',
         'oemid': '0x4455', 'prv': '0xa'})
    self.assertEqual(ps, {'eval': {'generic_storage': {}},
                          'expect': {'sectors': [True, 'int', '!eq 112233'],
                                     'name': [True, 'str', '!eq ABCxyz'],
                                     'manfid': [True, 'hex', '!eq 0x001122'],
                                     'oemid': [True, 'hex', '!eq 0x4455'],
                                     'prv': [True, 'hex', '!eq 0xa']}})

    # Should report not supported if some fields are missing.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '112233', 'name': 'ABCxyz', 'oemid': '0x4455',
                       'prv': '0xa'})

    # Should report not supported because `manfid` has incorrect bit length.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '112233', 'name': 'ABCxyz', 'manfid': '0xaa',
                       'oemid': '0x44556677', 'prv': '0xaabbccdd'})
    # Should report not supported because `name` should be a string of 6 bytes.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '1133', 'name': 'A', 'manfid': '0xaabbcc',
                       'oemid': '0x4455', 'prv': '0xaabbccdd'})
    # Should report not supported because `sectors` should be an integer.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '?', 'name': 'ABCxyz', 'manfid': '0xaabbcc',
                       'oemid': '0x4455', 'prv': '0xa'})
    # Should report not supported because `manfid` is not a valid hex number.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '112233', 'name': 'ABCxyz',
                       'manfid': '0x00ZZZZ', 'oemid': '0x4455', 'prv': '0xa'})


class GenericStorageATAProbeStatementGeneratorTest(unittest.TestCase):
  TARGET_CLS = (
      verification_payload_generator.GenericStorageATAProbeStatementGenerator)

  def testTryGenerate(self):
    ps = self.TARGET_CLS.TryGenerate(
        {'sectors': '112233', 'vendor': 'aabbccdd', 'model': 'this_is_model',
         'extra': '???'})
    self.assertEqual(ps, {'eval': {'generic_storage': {}},
                          'expect': {'sectors': [True, 'int', '!eq 112233'],
                                     'ata_vendor': [True, 'str',
                                                    '!eq aabbccdd'],
                                     'ata_model': [True, 'str',
                                                   '!eq this_is_model']}})

    # Should report not supported if some fields are missing.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '112233', 'vendor': 'aabbccdd', 'extra': '?'})

    # Should report not supported if some fields contain incorrect format.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '112233x', 'vendor': 'aabbccdd',
                       'model': 'this_is_model'})


class GenericStorageNVMeProbeStatementGeneratorTest(unittest.TestCase):
  TARGET_CLS = (
      verification_payload_generator.GenericStorageNVMeProbeStatementGenerator)

  def testTryGenerate(self):
    ps = self.TARGET_CLS.TryGenerate(
        {'sectors': '112233', 'class': '0x123456', 'device': '0x1234',
         'vendor': '0x5678'})
    self.assertEqual(ps, {'eval': {'generic_storage': {}},
                          'expect': {'sectors': [True, 'int', '!eq 112233'],
                                     'pci_class': [True, 'hex',
                                                   '!eq 0x123456'],
                                     'pci_vendor': [True, 'hex',
                                                    '!eq 0x5678'],
                                     'pci_device': [True, 'hex',
                                                    '!eq 0x1234']}})

    # Should report not supported if some fields are missing.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '112233', 'class': '0x123456'})

    # Should report not supported if some fields contain incorrect format.
    self.assertRaises(NotSuitableError, self.TARGET_CLS.TryGenerate,
                      {'sectors': '112233', 'class': '12345678',
                       'vendor': '0x1234', 'device': '0x5678'})


class GenerateVerificationPayloadTest(unittest.TestCase):
  def testSucc(self):
    dbs = [database.Database.LoadFile(os.path.join(TESTDATA_DIR, name),
                                      verify_checksum=False)
           for name in ('model_a_db.yaml', 'model_b_db.yaml')]
    expected_outputs = json_utils.LoadFile(
        os.path.join(TESTDATA_DIR, 'expected_model_ab_output.json'))

    files = verification_payload_generator.GenerateVerificationPayload(dbs)

    self.assertEqual(len(files), 3)
    self.assertEqual(
        json_utils.LoadStr(files['runtime_probe/model_a/probe_config.json']),
        expected_outputs['runtime_probe/model_a/probe_config.json'])
    self.assertEqual(
        json_utils.LoadStr(files['runtime_probe/model_b/probe_config.json']),
        expected_outputs['runtime_probe/model_b/probe_config.json'])
    hw_verificaiontion_spec = hardware_verifier_pb2.HwVerificationSpec()
    text_format.Parse(files['hw_verification_spec.prototxt'],
                      hw_verificaiontion_spec)
    assertCountEqual(
        self,
        json_format.MessageToDict(hw_verificaiontion_spec,
                                  including_default_value_fields=True,
                                  use_integers_for_enums=True),
        expected_outputs['hw_verification_spec.prototxt'])

  def testHasUnsupportedComps(self):
    # The database bad_model_db.yaml contains an unknown storage, which is not
    # allowed.
    dbs = [database.Database.LoadFile(os.path.join(TESTDATA_DIR, name),
                                      verify_checksum=False)
           for name in ('model_a_db.yaml', 'model_b_db.yaml',
                        'bad_model_db.yaml')]
    self.assertRaises(
        verification_payload_generator.GenerateVerificationPayloadError,
        verification_payload_generator.GenerateVerificationPayload, dbs)


if __name__ == '__main__':
  unittest.main()
