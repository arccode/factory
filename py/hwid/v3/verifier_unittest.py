#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3.database import Database
from cros.factory.hwid.v3 import verifier
from cros.factory.test.rules import phase


_TEST_DATABASE_PATH = os.path.join(
    os.path.dirname(__file__), 'testdata', 'test_verifier_db.yaml')


class VerifyComponentStatusTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH,
                                      verify_checksum=False)
    self.boms = {}
    for status in common.COMPONENT_STATUS:
      bom = BOM(encoding_pattern_index=0,
                image_id=0,
                components={'cpu': ['cpu_%s' % status],
                            'ram': ['ram_supported']})
      self.boms[status] = bom

  def testSupported(self):
    # Should always pass.
    for mode in common.OPERATION_MODE:
      for ph in phase.PHASE_NAMES:
        verifier.VerifyComponentStatus(
            self.database, self.boms[common.COMPONENT_STATUS.supported],
            mode=mode, current_phase=ph)

  def testUnqualified(self):
    # Should pass the verification only if the phase is before PVT.
    for mode in common.OPERATION_MODE:
      for ph in ['PROTO', 'EVT', 'DVT']:
        verifier.VerifyComponentStatus(
            self.database, self.boms[common.COMPONENT_STATUS.unqualified],
            mode=mode, current_phase=ph)

      for ph in ['PVT', 'PVT_DOGFOOD']:
        self.assertRaises(common.HWIDException, verifier.VerifyComponentStatus,
                          self.database,
                          self.boms[common.COMPONENT_STATUS.unqualified],
                          mode=mode, current_phase=ph)

  def testDeprecated(self):
    # Should pass the verification only in rma mode.
    for ph in phase.PHASE_NAMES:
      verifier.VerifyComponentStatus(
          self.database, self.boms[common.COMPONENT_STATUS.deprecated],
          mode=common.OPERATION_MODE.rma, current_phase=ph)

      self.assertRaises(common.HWIDException, verifier.VerifyComponentStatus,
                        self.database,
                        self.boms[common.COMPONENT_STATUS.deprecated],
                        mode=common.OPERATION_MODE.normal, current_phase=ph)

  def testUnsupported(self):
    # Should always fail the verification.
    for mode in common.OPERATION_MODE:
      for ph in phase.PHASE_NAMES:
        self.assertRaises(common.HWIDException, verifier.VerifyComponentStatus,
                          self.database,
                          self.boms[common.COMPONENT_STATUS.unsupported],
                          mode=mode, current_phase=ph)


class VerifyPhaseTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH,
                                      verify_checksum=False)
    self.possible_names = self.database.GetComponents('firmware_keys').keys()

  @staticmethod
  def _CreateBOM(image_id, firmware_key_name=None):
    components = {}
    if firmware_key_name:
      components['firmware_keys'] = [firmware_key_name]
    return BOM(0, image_id, components)

  def testNoKeyComponent(self):
    for image_id in [0, 1, 2]:
      bom = self._CreateBOM(image_id)
      verifier.VerifyPhase(
          self.database, bom,
          current_phase=self.database.GetImageName(image_id))

    bom = self._CreateBOM(image_id=3)
    self.assertRaises(common.HWIDException, verifier.VerifyPhase,
                      self.database, bom,
                      current_phase=self.database.GetImageName(3))

  def testEarlyBuild(self):
    for image_id in [0, 1, 2]:
      for component_name in self.possible_names:
        bom = self._CreateBOM(image_id, component_name)
        verifier.VerifyPhase(
            self.database, bom,
            current_phase=self.database.GetImageName(image_id))

  def testPVTBuild(self):
    for component_name in self.possible_names:
      bom = self._CreateBOM(3, component_name)
      if 'A' in component_name:
        verifier.VerifyPhase(self.database, bom,
                             current_phase=self.database.GetImageName(3))
      else:
        self.assertRaises(common.HWIDException, verifier.VerifyPhase,
                          self.database, bom,
                          current_phase=self.database.GetImageName(3))

  def testRMABuild(self):
    # Encode with RMA_IMAGE_ID
    bom = self._CreateBOM(image_id=database.ImageId.RMA_IMAGE_ID,
                          firmware_key_name='firmware_keys_A_mp')
    # In RMA mode, if RMA image ID is used, we don't care about current phase
    verifier.VerifyPhase(
        self.database, bom, current_phase=phase.PVT, rma_mode=True)
    verifier.VerifyPhase(
        self.database, bom, current_phase=phase.DVT, rma_mode=True)

    # If factory choose to not use RMA image ID, the image ID must match current
    # phase.
    bom = self._CreateBOM(image_id=3, firmware_key_name='firmware_keys_A_mp')
    verifier.VerifyPhase(
        self.database, bom, current_phase=phase.PVT, rma_mode=True)
    with self.assertRaises(common.HWIDException):
      verifier.VerifyPhase(
          self.database, bom, current_phase=phase.DVT, rma_mode=True)

  def testImageNameMisMatch(self):
    for image_id, ph in enumerate(['DVT', 'PVT']):
      bom = self._CreateBOM(image_id)
      self.assertRaises(common.HWIDException, verifier.VerifyPhase,
                        self.database, bom, current_phase=ph)



class VerifyBOMTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH,
                                      verify_checksum=False)
    self.decoded_bom = BOM(
        encoding_pattern_index=0, image_id=0, components={
            'cpu': ['cpu_supported', 'cpu_unqualified'],
            'ram': [],
            'firmware_keys': ['firmware_keys_dev']})

  def testPass(self):
    probed_bom = BOM(
        encoding_pattern_index=0, image_id=0, components={
            'cpu': ['cpu_unqualified', 'cpu_supported'],
            'ram': [],
            'firmware_keys': ['firmware_keys_dev']})

    verifier.VerifyBOM(self.database, self.decoded_bom, probed_bom)

  def testHasExtraComponents(self):
    probed_bom = BOM(
        encoding_pattern_index=0, image_id=0, components={
            'cpu': ['cpu_unqualified', 'cpu_supported'],
            'ram': ['ram_supported'],
            'firmware_keys': ['firmware_keys_dev']})

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)

    probed_bom = BOM(
        encoding_pattern_index=0, image_id=0, components={
            'cpu': ['cpu_unqualified', 'cpu_supported', 'cpu_deprecated'],
            'ram': [],
            'firmware_keys': ['firmware_keys_dev']})

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)

  def testIsMissingComponents(self):
    probed_bom = BOM(encoding_pattern_index=0, image_id=0, components={
        'cpu': ['cpu_unqualified'],
        'ram': [],
        'firmware_keys': ['firmware_keys_dev']})

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)

  def testMisMatch(self):
    probed_bom = BOM(encoding_pattern_index=0, image_id=0, components={
        'cpu': ['cpu_unqualified', 'cpu_deprecated'],
        'ram': [],
        'firmware_keys': ['firmware_keys_dev']})

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)


class VerifyConfiglessTest(unittest.TestCase):
  def setUp(self):
    self.database = Database.LoadFile(_TEST_DATABASE_PATH,
                                      verify_checksum=False)
    self.probed_bom = BOM(
        encoding_pattern_index=0, image_id=0, components={
            'storage': ['KLMCG2KCTA-B041_0200000000000000'],
            'dram': ['K4E6E304EC-EGCF_4096mb_0', 'K4E6E304EC-EGCF_4096mb_1']})

    self.device_info = {
        'component': {
            'has_touchscreen': True
        }
    }

  def testPass(self):
    decoded_configless = {
        'version': 0,
        'memory': 8,
        'storage': 58,
        'feature_list': {
            'has_touchscreen': 1,
            'has_touchpad': 0,
            'has_stylus': 0,
            'has_front_camera': 0,
            'has_rear_camera': 0,
            'has_fingerprint': 0,
            'is_convertible': 0,
            'is_rma_device': 0
        }
    }
    verifier.VerifyConfigless(self.database, decoded_configless,
                              self.probed_bom, self.device_info, False)

  def testLacksVersionField(self):
    decoded_configless = {
        'memory': 8,
        'storage': 58,
        'feature_list': {
            'has_touchscreen': 1,
            'has_touchpad': 0,
            'has_stylus': 0,
            'has_front_camera': 0,
            'has_rear_camera': 0,
            'has_fingerprint': 0,
            'is_convertible': 0,
            'is_rma_device': 0
        }
    }
    self.assertRaises(common.HWIDException, verifier.VerifyConfigless,
                      self.database, decoded_configless, self.probed_bom,
                      self.device_info, False)

  def testHasExtraComponents(self):
    decoded_configless = {
        'version': 0,
        'memory': 8,
        'storage': 58,
        'feature_list': {
            'has_touchscreen': 1,
            'has_touchpad': 0,
            'has_stylus': 0,
            'has_front_camera': 0,
            'has_rear_camera': 0,
            'has_fingerprint': 0,
            'is_convertible': 0,
            'is_rma_device': 0,
            'is_detachable': 0
        }
    }
    self.assertRaises(common.HWIDException, verifier.VerifyConfigless,
                      self.database, decoded_configless, self.probed_bom,
                      self.device_info, False)

  def testIsMissingComponents(self):
    decoded_configless = {
        'version': 0,
        'memory': 8,
        'storage': 58,
        'feature_list': {
            'has_touchpad': 0,
            'has_stylus': 0,
            'has_front_camera': 0,
            'has_rear_camera': 0,
            'has_fingerprint': 0,
            'is_convertible': 0,
            'is_rma_device': 0
        }
    }
    self.assertRaises(common.HWIDException, verifier.VerifyConfigless,
                      self.database, decoded_configless, self.probed_bom,
                      self.device_info, False)

  def testMisMatch(self):
    decoded_configless = {
        'version': 0,
        'memory': 4,
        'storage': 64,
        'feature_list': {
            'has_touchscreen': 0,
            'has_touchpad': 0,
            'has_stylus': 0,
            'has_front_camera': 0,
            'has_rear_camera': 0,
            'has_fingerprint': 1,
            'is_convertible': 0,
            'is_rma_device': 0
        }
    }
    self.assertRaises(common.HWIDException, verifier.VerifyConfigless,
                      self.database, decoded_configless, self.probed_bom,
                      self.device_info, False)


if __name__ == '__main__':
  unittest.main()
