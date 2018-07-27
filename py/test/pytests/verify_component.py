# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Verify peripheral components.

Verify the number of components from probed results and from device data
are the same. And verify the status of components are supported when the
phase is PVT or PVT_DOGFOOD.
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.hwid.v3 import common
from cros.factory.test import device_data
from cros.factory.test.rules import phase
from cros.factory.test import test_case
from cros.factory.test.utils import deploy_utils
from cros.factory.test.utils import update_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import json_utils


_NUMBER_NOT_IN_DEVICE_DATA = 1


class VerifyComponentTest(test_case.TestCase):
  ARGS = [
      Arg('enable_factory_server', bool,
          'Update hwid data from factory server.',
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
    self.component_data = {}

  def tearDown(self):
    self.dut.Call(['rm', '-rf', self.tmpdir])

  def runTest(self):
    if self.args.enable_factory_server:
      update_utils.UpdateHWIDDatabase(self.dut)

    converted_statement_file = self.dut.path.join(
        self.tmpdir, 'converted_statement_file.json')
    self.factory_tools.CallOutput(
        ['hwid', 'converter', '--output-file', converted_statement_file])
    self.probed_results = json_utils.LoadStr(self.factory_tools.CallOutput(
        ['probe', 'probe', '--config-file', converted_statement_file]))
    self.component_data = {k[4:]: int(v) for k, v in
                           device_data.GetDeviceData('component').iteritems()
                           if k.startswith('has_')}

    self._VerifyNumMismatch()
    self._VerifyNotSupported()

    if self.num_mismatch or self.not_supported:
      self.ui.CallJSFunction('setFailedMessage')
      if self.num_mismatch:
        self.ui.CallJSFunction(
            'createNumMismatchResult', self.num_mismatch)

      if self.not_supported:
        self.ui.CallJSFunction(
            'createNotSupportedResult', self.not_supported)

      self.WaitTaskEnd()

  def _CheckPhase(self):
    current_phase = phase.GetPhase()
    return current_phase == phase.PVT or current_phase == phase.PVT_DOGFOOD

  def _VerifyNumMismatch(self):
    def _ExtractInfoToName(comp_info):
      return [comp['name'] for comp in comp_info]

    for comp_cls, correct_num in self.component_data.iteritems():
      comp_info = self.probed_results.get(comp_cls, [])
      actual_num = len(comp_info)
      if correct_num != actual_num:
        self.num_mismatch.append((comp_cls, correct_num,
                                  _ExtractInfoToName(comp_info)))

    # The number of component should be _NUMBER_NOT_IN_DEVICE_DATA
    # when the component is not in device data.
    for comp_cls, comp_info in self.probed_results.iteritems():
      if comp_cls not in self.component_data:
        actual_num = len(comp_info)
        if actual_num != _NUMBER_NOT_IN_DEVICE_DATA:
          self.num_mismatch.append(
              (comp_cls, _NUMBER_NOT_IN_DEVICE_DATA,
               _ExtractInfoToName(comp_info)))

  def _VerifyNotSupported(self):
    if self._CheckPhase():
      for comp_cls, comp_info in self.probed_results.iteritems():
        for comp_item in comp_info:
          status = comp_item['information']['status']
          if status != common.COMPONENT_STATUS.supported:
            self.not_supported.append((comp_cls, comp_item['name'], status))
