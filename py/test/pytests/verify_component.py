# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Verify peripheral components.

Verify the number of components from probed results and from device data
are the same. And verify the status of components are supported when the
phase is PVT or PVT_DOGFOOD.
"""


import hashlib

from cros.factory.device import device_utils
from cros.factory.hwid.v3 import common
from cros.factory.test import device_data
from cros.factory.test.rules import phase
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test.utils import deploy_utils
from cros.factory.test.utils import update_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import json_utils


_NUMBER_NOT_IN_DEVICE_DATA = 1


class VerifyComponentTest(test_case.TestCase):
  ARGS = [
      Arg('approx_match', bool,
          'Enable apporximate matching results.',
          default=True),
      Arg('enable_factory_server', bool,
          'Update hwid data from factory server.',
          default=True),
      Arg('max_mismatch', int,
          'The number of mismatched rules at most.',
          default=1),
      Arg('verify_checksum', bool,
          'Enable converted statements checksum verification.',
          default=True)
  ]

  def setUp(self):
    self.ui.SetupStaticFiles()
    self.dut = device_utils.CreateDUTInterface()
    self.factory_tools = deploy_utils.CreateFactoryTools(self.dut)
    self.tmpdir = self.dut.temp.mktemp(is_dir=True, prefix='verify_component')
    self.num_mismatch = []
    self.not_supported = []
    self.probed_results = {}
    self.perfect_match_results = {}
    self.component_data = {}
    self.converted_statement_file = self.dut.path.join(
        self.tmpdir, 'converted_statement_file.json')

  def tearDown(self):
    self.dut.Call(['rm', '-rf', self.tmpdir])

  def runTest(self):
    converted_statement, converted_checksum = self._GetConvertedStatement()

    if self.args.verify_checksum:
      expected_checksum = hashlib.sha1(
          converted_statement.encode('utf-8')).hexdigest()
      if expected_checksum != converted_checksum:
        self.FailTask('Checksum failed.')
      else:
        session.console.info('Checksum passed.')

    self.probed_results = json_utils.LoadStr(self.factory_tools.CheckOutput(
        ['probe', 'probe', '--config-file', self.converted_statement_file,
         '--approx-match', '--max-mismatch',
         '{}'.format(self.args.max_mismatch)]))
    self.perfect_match_results = self._GetPerfectMatchProbeResult()
    self.component_data = {k[4:]: int(v) for k, v in
                           device_data.GetDeviceData('component').items()
                           if k.startswith('has_')}

    self._VerifyNumMismatch()
    self._VerifyNotSupported()

    if self.num_mismatch or self.not_supported:
      self.ui.CallJSFunction('setFailedMessage')
      if self.num_mismatch:
        self.ui.CallJSFunction(
            'createNumMismatchResult', self.num_mismatch,
            self.args.approx_match, self.probed_results)

      if self.not_supported:
        self.ui.CallJSFunction(
            'createNotSupportedResult', self.not_supported)

      self.WaitTaskEnd()

  def _CheckPhase(self):
    current_phase = phase.GetPhase()
    return current_phase in (phase.PVT, phase.PVT_DOGFOOD)

  def _VerifyNumMismatch(self):
    def _ExtractInfoToName(comp_info):
      return [comp['name'] for comp in comp_info]

    for comp_cls, correct_num in self.component_data.items():
      comp_info = self.perfect_match_results.get(comp_cls, [])
      actual_num = len(comp_info)
      if correct_num != actual_num:
        self.num_mismatch.append((comp_cls, correct_num,
                                  _ExtractInfoToName(comp_info)))

    # The number of component should be _NUMBER_NOT_IN_DEVICE_DATA
    # when the component is not in device data.
    for comp_cls, comp_info in self.perfect_match_results.items():
      if comp_cls not in self.component_data:
        actual_num = len(comp_info)
        if actual_num != _NUMBER_NOT_IN_DEVICE_DATA:
          self.num_mismatch.append(
              (comp_cls, _NUMBER_NOT_IN_DEVICE_DATA,
               _ExtractInfoToName(comp_info)))

  def _VerifyNotSupported(self):
    if self._CheckPhase():
      for comp_cls, comp_info in self.perfect_match_results.items():
        for comp_item in comp_info:
          status = comp_item['information']['status']
          if status != common.COMPONENT_STATUS.supported:
            self.not_supported.append((comp_cls, comp_item['name'], status))

  def _GetConvertedStatement(self):
    if self.args.enable_factory_server:
      update_utils.UpdateHWIDDatabase(self.dut)

    converted_checksum_file = self.dut.path.join(
        self.tmpdir, 'converted_checksum')
    self.factory_tools.CallOutput(
        ['hwid', 'converter', '--output-file', self.converted_statement_file,
         '--output-checksum-file', converted_checksum_file])
    converted_statement = self.dut.ReadFile(self.converted_statement_file)
    converted_checksum = self.dut.ReadFile(converted_checksum_file)
    return converted_statement, converted_checksum

  def _GetPerfectMatchProbeResult(self):
    res = {}
    for comp_cls, comp_info in self.probed_results.items():
      res[comp_cls] = [item for item in comp_info if item['perfect_match']]

    return res
