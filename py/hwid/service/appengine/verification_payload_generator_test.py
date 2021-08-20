#!/usr/bin/env python3
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

# pylint: disable=import-error, no-name-in-module
from google.protobuf import json_format
from google.protobuf import text_format
import hardware_verifier_pb2

from cros.factory.hwid.service.appengine import verification_payload_generator
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import rule as hwid_rule
from cros.factory.probe.runtime_probe import probe_config_types
from cros.factory.utils import json_utils


_vp_generator = verification_payload_generator

MissingComponentValueError = _vp_generator.MissingComponentValueError
ProbeStatementConversionError = _vp_generator.ProbeStatementConversionError

TESTDATA_DIR = os.path.join(
    os.path.dirname(__file__), 'testdata', 'verification_payload_generator')


class GenericBatteryProbeStatementGeneratorTest(unittest.TestCase):

  def testTryGenerate(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['battery'][0]

    ps = ps_gen.TryGenerate(
        'name1',
        {'manufacturer': 'foo',
         'model_name': hwid_rule.Value('bar', is_re=True),
         'technology': 'cutting-edge-tech',
         'other_value': 'z'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'battery', 'name1', {
                'eval': {
                    'generic_battery': {}
                },
                'expect': {
                    'manufacturer': [True, 'str', '!eq foo'],
                    'model_name': [True, 'str', '!re bar'],
                    'technology': [True, 'str', '!eq cutting-edge-tech']
                }
            }))

    # Should report not supported if some fields are missing.
    self.assertRaises(MissingComponentValueError, ps_gen.TryGenerate,
                      'name1', {'manufacturer': 'foo'})


class GenericStorageMMCProbeStatementGeneratorTest(unittest.TestCase):

  def testTryGenerate(self):
    comp_values = {
        'sectors': '112233',
        'name': 'ABCxyz',
        'manfid': '0x00022',
        'oemid': '0x4455',
        'prv': '0xa',
        'serial': '0x1234abcd'
    }
    comp_values_new = {
        'sectors': '112233',
        'mmc_name': 'ABCxyz',
        'mmc_manfid': '0x00022',
        'mmc_oemid': '0x4455',
        'mmc_prv': '0xa',
        'mmc_serial': '0x1234abcd'
    }
    expected = probe_config_types.ComponentProbeStatement(
        'storage', 'name1', {
            'eval': {
                'generic_storage': {}
            },
            'expect': {
                'sectors': [True, 'int', '!eq 112233'],
                'mmc_hwrev': [False, 'hex'],
                'mmc_name': [True, 'str', '!eq ABCxyz'],
                'mmc_manfid': [True, 'hex', '!eq 0x22'],
                'mmc_oemid': [True, 'hex', '!eq 0x4455'],
                'mmc_prv': [True, 'hex', '!eq 0x0A'],
                'mmc_serial': [True, 'hex', '!eq 0x1234ABCD']
            }
        })
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['storage'][0]
    ps = ps_gen.TryGenerate('name1', comp_values)
    self.assertEqual(ps, expected)
    ps = ps_gen.TryGenerate('name1', comp_values_new)
    self.assertEqual(ps, expected)

    # Should report not supported if some fields are missing.
    invalid_comp_values = dict(comp_values)
    del invalid_comp_values['manfid']
    self.assertRaises(MissingComponentValueError, ps_gen.TryGenerate, 'n1',
                      invalid_comp_values)

    # Should report not supported because `oemid` has incorrect bit length.
    invalid_comp_values = dict(comp_values, oemid='0x44556677')
    self.assertRaises(ProbeStatementConversionError, ps_gen.TryGenerate, 'n1',
                      invalid_comp_values)

    # Should report not supported because `name` should be a string of 6 bytes.
    invalid_comp_values = dict(comp_values, name='A')
    self.assertRaises(ProbeStatementConversionError, ps_gen.TryGenerate, 'n1',
                      invalid_comp_values)

    # Should report not supported because `sectors` should be an integer.
    invalid_comp_values = dict(comp_values, sectors='?')
    self.assertRaises(ProbeStatementConversionError, ps_gen.TryGenerate, 'n1',
                      invalid_comp_values)

    # Should report not supported because `manfid` is not a valid hex number.
    invalid_comp_values = dict(comp_values, manfid='0x00ZZZZ')
    self.assertRaises(ProbeStatementConversionError, ps_gen.TryGenerate, 'n1',
                      invalid_comp_values)


class GenericStorageNVMeProbeStatementGeneratorTest(unittest.TestCase):

  def testTryGenerate(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['storage'][1]
    ps = ps_gen.TryGenerate(
        'name1', {
            'sectors': '112233',
            'class': '0x123456',
            'device': '0x1234',
            'vendor': '0x5678',
        })
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'storage', 'name1', {
                'eval': {
                    'generic_storage': {}
                },
                'expect': {
                    'sectors': [True, 'int', '!eq 112233'],
                    'pci_class': [True, 'hex', '!eq 0x123456'],
                    'pci_vendor': [True, 'hex', '!eq 0x5678'],
                    'pci_device': [True, 'hex', '!eq 0x1234'],
                    'nvme_model': [False, 'str'],
                }
            }))
    ps = ps_gen.TryGenerate(
        'name1', {
            'sectors': '112233',
            'pci_class': '0x123456',
            'pci_device': '0x1234',
            'pci_vendor': '0x5678',
            'nvme_model': 'ABC1234T128G',
        })
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'storage', 'name1', {
                'eval': {
                    'generic_storage': {}
                },
                'expect': {
                    'sectors': [True, 'int', '!eq 112233'],
                    'pci_class': [True, 'hex', '!eq 0x123456'],
                    'pci_vendor': [True, 'hex', '!eq 0x5678'],
                    'pci_device': [True, 'hex', '!eq 0x1234'],
                    'nvme_model': [True, 'str', '!eq ABC1234T128G'],
                }
            }))

    # Should report not supported if some fields are missing.
    self.assertRaises(MissingComponentValueError, ps_gen.TryGenerate, 'name1',
                      {'sectors': '112233', 'class': '0x123456'})

    # Should report not supported if some fields contain incorrect format.
    self.assertRaises(ProbeStatementConversionError, ps_gen.TryGenerate, 'n1',
                      {'sectors': '112233', 'class': '12345678',
                       'vendor': '0x1234', 'device': '0x5678'})


class NetworkProbeStatementGeneratorTest(unittest.TestCase):

  def testUSB(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['wireless'][1]
    ps = ps_gen.TryGenerate(
        'name1',
        {'idVendor': '1122', 'idProduct': '5566'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'wireless', 'name1', {
                'eval': {
                    'wireless_network': {}
                },
                'expect': {
                    'usb_vendor_id': [True, 'hex', '!eq 0x1122'],
                    'usb_product_id': [True, 'hex', '!eq 0x5566'],
                    'usb_bcd_device': [False, 'hex']
                }
            }))

  def testPciOrSdioSuccess(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['wireless'][0]
    ps = ps_gen.TryGenerate('name1', {
        'vendor': '0x1234',
        'device': '0x5678'
    })
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'wireless', 'name1', {
                'eval': {
                    'wireless_network': {}
                },
                'expect': [{
                    'pci_device_id': [True, 'hex', '!eq 0x5678'],
                    'pci_revision': [False, 'hex'],
                    'pci_subsystem': [False, 'hex'],
                    'pci_vendor_id': [True, 'hex', '!eq 0x1234']
                }, {
                    'sdio_device_id': [True, 'hex', '!eq 0x5678'],
                    'sdio_vendor_id': [True, 'hex', '!eq 0x1234']
                }]
            }))

    ps = ps_gen.TryGenerate('name1', {
        'vendor': '0x1234',
        'device': '0x5678',
        'subsystem_device': '0x0123'
    })
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'wireless', 'name1', {
                'eval': {
                    'wireless_network': {}
                },
                'expect': [{
                    'pci_device_id': [True, 'hex', '!eq 0x5678'],
                    'pci_revision': [False, 'hex'],
                    'pci_subsystem': [True, 'hex', '!eq 0x0123'],
                    'pci_vendor_id': [True, 'hex', '!eq 0x1234']
                }, {
                    'sdio_device_id': [True, 'hex', '!eq 0x5678'],
                    'sdio_vendor_id': [True, 'hex', '!eq 0x1234']
                }]
            }))

  def testPciOrSdioFail(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['wireless'][0]
    self.assertRaises(MissingComponentValueError, ps_gen.TryGenerate, 'name1',
                      {'device': '0x5678'})


class MemoryProbeStatementGeneratorTest(unittest.TestCase):

  def testTryGenerate(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['dram'][0]

    ps = ps_gen.TryGenerate(
        'name1', {'part': 'ABC123DEF-A1_0', 'size': '4096', 'slot': '0'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'dram', 'name1', {
                'eval': {
                    'memory': {}
                },
                'expect': {
                    'part': [True, 'str', '!eq ABC123DEF-A1_0'],
                    'size': [True, 'int', '!eq 4096'],
                    'slot': [True, 'int', '!eq 0']
                }
            }))

    ps = ps_gen.TryGenerate('name2', {'part': 'ABC123DEF-A1', 'size': '4096'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'dram', 'name2', {
                'eval': {
                    'memory': {}
                },
                'expect': {
                    'part': [True, 'str', '!eq ABC123DEF-A1'],
                    'size': [True, 'int', '!eq 4096'],
                    'slot': [False, 'int']
                }
            }))


class InputDeviceProbeStatementGeneratorTest(unittest.TestCase):

  def testStylusTryGenerate(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['stylus'][0]

    ps = ps_gen.TryGenerate(
        'name1',
        {'name': 'foo', 'product': '1122', 'vendor': '5566'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'stylus', 'name1', {
                'eval': {
                    'input_device': {}
                },
                'expect': {
                    'name': [True, 'str', '!eq foo'],
                    'product': [True, 'hex', '!eq 0x1122'],
                    'vendor': [True, 'hex', '!eq 0x5566'],
                }
            }))

  def testTouchpadTryGenerate(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['touchpad'][0]

    ps = ps_gen.TryGenerate(
        'name1',
        {'name': 'foo', 'product': '1122', 'vendor': '5566'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'touchpad', 'name1', {
                'eval': {
                    'input_device': {}
                },
                'expect': {
                    'name': [True, 'str', '!eq foo'],
                    'product': [True, 'hex', '!eq 0x1122'],
                    'vendor': [True, 'hex', '!eq 0x5566'],
                }
            }))

  def testTouchscreenNormal(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['touchscreen'][0]

    ps = ps_gen.TryGenerate(
        'name1', {
            'name': 'foo',
            'product': '0x11223344',
            'vendor': '5566',
        })
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'touchscreen', 'name1', {
                'eval': {
                    'input_device': {}
                },
                'expect': {
                    'name': [True, 'str', '!eq foo'],
                    'product': [True, 'hex', '!eq 0x11223344'],
                    'vendor': [True, 'hex', '!eq 0x5566'],
                }
            }))

  def testTouchscreenAlternativeHwidField(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['touchscreen'][0]

    ps = ps_gen.TryGenerate('name1', {
        'name': 'foo',
        'hw_version': '1122',
        'fw_version': '1.1'
    })
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'touchscreen', 'name1', {
                'eval': {
                    'input_device': {}
                },
                'expect': {
                    'name': [True, 'str', '!eq foo'],
                    'product': [True, 'hex', '!eq 0x1122'],
                    'vendor': [False, 'hex'],
                }
            }))

  def testTouchscreenComponentValueRepetition(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['touchscreen'][0]

    # Same values between `hw_version` and `product`.
    ps = ps_gen.TryGenerate('name1', {
        'name': 'foo',
        'hw_version': '1122',
        'product': '1122',
        'fw_version': '1.1'
    })
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'touchscreen', 'name1', {
                'eval': {
                    'input_device': {}
                },
                'expect': {
                    'name': [True, 'str', '!eq foo'],
                    'product': [True, 'hex', '!eq 0x1122'],
                    'vendor': [False, 'hex'],
                }
            }))

  def testTouchscreenComponentValueInconsistent(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['touchscreen'][0]

    # Inconsistent values between `hw_version` and `product`.
    self.assertRaises(ProbeStatementConversionError, ps_gen.TryGenerate,
                      'name1', {
                          'name': 'foo',
                          'hw_version': '1122',
                          'product': '3344',
                          'fw_version': '1.1'
                      })


class EdidProbeStatementGeneratorTest(unittest.TestCase):

  def testTryGenerate(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['display_panel'][0]

    ps = ps_gen.TryGenerate(
        'name1',
        {'height': '1080', 'product_id': '1a2b', 'vendor': 'FOO',
         'width': '1920'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'display_panel', 'name1', {
                'eval': {
                    'edid': {}
                },
                'expect': {
                    'height': [True, 'int', '!eq 1080'],
                    'product_id': [True, 'hex', '!eq 0x1A2B'],
                    'vendor': [True, 'str', '!eq FOO'],
                    'width': [True, 'int', '!eq 1920']
                }
            }))


class GenerateVerificationPayloadTest(unittest.TestCase):

  def testSucc(self):
    dbs = [(database.Database.LoadFile(
        os.path.join(TESTDATA_DIR, name), verify_checksum=False), [])
           for name in ('model_a_db.yaml', 'model_b_db.yaml', 'model_c_db.yaml',
                        'model_d_db.yaml', 'model_e_db.yaml')]
    expected_outputs = json_utils.LoadFile(
        os.path.join(TESTDATA_DIR, 'expected_model_ab_output.json'))

    files = _vp_generator.GenerateVerificationPayload(
        dbs).generated_file_contents

    # files should include hw_verification_spec.prototxt.
    self.assertEqual(len(files), len(dbs) + 1)
    self.assertEqual(
        json_utils.LoadStr(files['runtime_probe/model_a/probe_config.json']),
        expected_outputs['runtime_probe/model_a/probe_config.json'])
    self.assertEqual(
        json_utils.LoadStr(files['runtime_probe/model_b/probe_config.json']),
        expected_outputs['runtime_probe/model_b/probe_config.json'])
    self.assertEqual(
        json_utils.LoadStr(files['runtime_probe/model_c/probe_config.json']),
        expected_outputs['runtime_probe/model_c/probe_config.json'])
    self.assertEqual(
        json_utils.LoadStr(files['runtime_probe/model_d/probe_config.json']),
        expected_outputs['runtime_probe/model_d/probe_config.json'])
    self.assertEqual(
        json_utils.LoadStr(files['runtime_probe/model_e/probe_config.json']),
        expected_outputs['runtime_probe/model_e/probe_config.json'])
    hw_verificaiontion_spec = hardware_verifier_pb2.HwVerificationSpec()
    text_format.Parse(files['hw_verification_spec.prototxt'],
                      hw_verificaiontion_spec)
    self.assertEqual(
        json_utils.DumpStr(
            json_format.MessageToDict(hw_verificaiontion_spec), sort_keys=True),
        json_utils.DumpStr(expected_outputs['hw_verification_spec.prototxt'],
                           sort_keys=True))

  def testHasUnsupportedComps(self):
    # The database bad_model_db.yaml contains an unknown storage, which is not
    # allowed.
    dbs = [(database.Database.LoadFile(os.path.join(TESTDATA_DIR, name),
                                       verify_checksum=False), [])
           for name in ('model_a_db.yaml', 'model_b_db.yaml',
                        'bad_model_db.yaml')]
    report = _vp_generator.GenerateVerificationPayload(dbs)
    self.assertEqual(len(report.error_msgs), 1)


class GenerateProbeStatementWithInformation(unittest.TestCase):

  def testWithComponent(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['storage'][1]
    ps = ps_gen.TryGenerate(
        'name1',
        {'sectors': '112233', 'class': '0x123456', 'device': '0x1234',
         'vendor': '0x5678'}, {'comp_group': 'name2'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'storage', 'name1', {
                'eval': {
                    'generic_storage': {}
                },
                'expect': {
                    'sectors': [True, 'int', '!eq 112233'],
                    'pci_class': [True, 'hex', '!eq 0x123456'],
                    'pci_vendor': [True, 'hex', '!eq 0x5678'],
                    'pci_device': [True, 'hex', '!eq 0x1234'],
                    'nvme_model': [False, 'str']
                },
                'information': {
                    'comp_group': 'name2'
                },
            }))


class USBCameraProbeStatementGeneratorTest(unittest.TestCase):

  def testTryGenerate(self):
    ps_gen = _vp_generator.GetAllProbeStatementGenerators()['video'][0]
    ps = ps_gen.TryGenerate(
        'name1',
        {'idVendor': '1234', 'idProduct': '5678', 'bcdDevice': '90AB',
         'bus_type': 'usb'})
    self.assertEqual(
        ps,
        probe_config_types.ComponentProbeStatement(
            'camera', 'name1', {
                'eval': {
                    'usb_camera': {}
                },
                'expect': {
                    'usb_vendor_id': [True, 'hex', '!eq 0x1234'],
                    'usb_product_id': [True, 'hex', '!eq 0x5678'],
                    'usb_bcd_device': [True, 'hex', '!eq 0x90AB']
                }
            }))

    # Should report not supported if some fields are missing.
    self.assertRaises(MissingComponentValueError, ps_gen.TryGenerate, 'name1',
                      {'idVendor': '1234', 'bcdDevice': '90AB'})

    # Should report not supported if some fields contain incorrect format.
    self.assertRaises(ProbeStatementConversionError, ps_gen.TryGenerate, 'n1',
                      {'idVendor': 'this-is-invalid', 'idProduct': '2147',
                       'bcdDevice': '4836'})


if __name__ == '__main__':
  unittest.main()
