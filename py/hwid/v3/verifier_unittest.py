#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3.bom import ProbedComponentResult
from cros.factory.hwid.v3 import common
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
      bom = BOM(project='CHROMEBOOK',
                encoding_pattern_index=0,
                image_id=0,
                components={
                    'cpu': [ProbedComponentResult('cpu_%s' % status, {}, None)],
                    'ram': [ProbedComponentResult('ram_supported', {}, None)]},
                encoded_fields=None)
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

  def testDeprecatedInNormalMode(self):
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
    self.possible_names = self.database.components.components_dict[
        'firmware_keys']['items'].keys()

  @staticmethod
  def _CreateBOM(image_id, firmware_key_name=None):
    components = {}
    if firmware_key_name:
      components['firmware_keys'] = [
          ProbedComponentResult(firmware_key_name, {}, None)]
    return BOM(project='CHROMEBOOK', encoding_pattern_index=0,
               image_id=image_id, components=components, encoded_fields=None)

  def testNoKeyComponent(self):
    for image_id in [0, 1, 2]:
      bom = self._CreateBOM(image_id)
      verifier.VerifyPhase(
          self.database, bom, current_phase=self.database.image_id[image_id])

    bom = self._CreateBOM(image_id=3)
    self.assertRaises(common.HWIDException, verifier.VerifyPhase,
                      self.database, bom,
                      current_phase=self.database.image_id[3])

  def testEarlyBuild(self):
    for image_id in [0, 1, 2]:
      for component_name in self.possible_names:
        bom = self._CreateBOM(image_id, component_name)
        verifier.VerifyPhase(
            self.database, bom, current_phase=self.database.image_id[image_id])

  def testPVTBuild(self):
    for component_name in self.possible_names:
      bom = self._CreateBOM(3, component_name)
      if 'A' in component_name:
        verifier.VerifyPhase(self.database, bom,
                             current_phase=self.database.image_id[3])
      else:
        self.assertRaises(common.HWIDException, verifier.VerifyPhase,
                          self.database, bom,
                          current_phase=self.database.image_id[3])

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
        project='CHROMEBOOK', encoding_pattern_index=0, image_id=0,
        components={
            'cpu': [ProbedComponentResult('cpu_supported', {}, None),
                    ProbedComponentResult('cpu_unqualified', {}, None)],
            'ram': [],
            'firmware_keys': [
                ProbedComponentResult('firmware_keys_dev', {}, None)]},
        encoded_fields=None)

  def testPass(self):
    probed_bom = BOM(
        project='CHROMEBOOK', encoding_pattern_index=0, image_id=0,
        components={
            'cpu': [ProbedComponentResult('cpu_unqualified', {}, None),
                    ProbedComponentResult('cpu_supported', {}, None)],
            'ram': [],
            'firmware_keys': [
                ProbedComponentResult('firmware_keys_dev', {}, None)]},
        encoded_fields=None)

    verifier.VerifyBOM(self.database, self.decoded_bom, probed_bom)

  def testHasExtraComponents(self):
    probed_bom = BOM(
        project='CHROMEBOOK', encoding_pattern_index=0, image_id=0,
        components={
            'cpu': [ProbedComponentResult('cpu_unqualified', {}, None),
                    ProbedComponentResult('cpu_supported', {}, None)],
            'ram': [ProbedComponentResult('ram_supported', {}, None)],
            'firmware_keys': [
                ProbedComponentResult('firmware_keys_dev', {}, None)]},
        encoded_fields=None)

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)

    probed_bom = BOM(
        project='CHROMEBOOK', encoding_pattern_index=0, image_id=0,
        components={
            'cpu': [ProbedComponentResult('cpu_unqualified', {}, None),
                    ProbedComponentResult('cpu_supported', {}, None),
                    ProbedComponentResult('cpu_deprecated', {}, None)],
            'ram': [],
            'firmware_keys': [
                ProbedComponentResult('firmware_keys_dev', {}, None)]},
        encoded_fields=None)

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)

  def testIsMissingComponents(self):
    probed_bom = BOM(
        project='CHROMEBOOK', encoding_pattern_index=0, image_id=0,
        components={
            'cpu': [ProbedComponentResult('cpu_unqualified', {}, None)],
            'ram': [],
            'firmware_keys': [
                ProbedComponentResult('firmware_keys_dev', {}, None)]},
        encoded_fields=None)

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)

  def testMisMatch(self):
    probed_bom = BOM(
        project='CHROMEBOOK', encoding_pattern_index=0, image_id=0,
        components={
            'cpu': [ProbedComponentResult('cpu_unqualified', {}, None),
                    ProbedComponentResult('cpu_deprecated', {}, None)],
            'ram': [],
            'firmware_keys': [
                ProbedComponentResult('firmware_keys_dev', {}, None)]},
        encoded_fields=None)

    self.assertRaises(common.HWIDException, verifier.VerifyBOM,
                      self.database, self.decoded_bom, probed_bom)


if __name__ == '__main__':
  unittest.main()
