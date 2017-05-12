# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# DESCRIPTION :
# This is a test that verifies only expected components are installed in the
# DUT.
"""Factory test to verify components."""

import json
import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import event_log
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.rules import phase
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import deploy_utils
from cros.factory.utils.arg_utils import Arg

_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Components Verification Test')
_MESSAGE_CHECKING_COMPONENTS = i18n_test_ui.MakeI18nLabelWithClass(
    'Checking components...', 'progress-message')


class VerifyComponentsTest(unittest.TestCase):
  """Factory test to verify components."""
  ARGS = [
      Arg('component_list', list,
          'A list of components to be verified'),
      Arg('fast_fw_probe', bool,
          'Whether to do a fast firmware probe. The fast firmware probe just '
          'checks the RO EC and main firmware version and does not compute'
          'firmware hashes.',
          default=True, optional=True),
      Arg('skip_shopfloor', bool,
          'Set this value to True to skip updating hwid data from shopfloor '
          'server.',
          default=False, optional=True),
      Arg('with_goofy', bool,
          'Set this value to False if the test is not running with goofy. '
          'Without goofy, test_ui and event_log will not work, thus will be '
          'disabled',
          default=True, optional=True),
      Arg('phase', str,
          'Override current phase, this is for standalone testing.',
          default=None, optional=True)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.factory_par = deploy_utils.CreateFactoryTools(self._dut)
    self._shopfloor = shopfloor
    self.probed_results = None
    self._allow_unqualified = None

    if self.args.with_goofy:
      self._ui = test_ui.UI()
      self._ui.AppendCSS('.progress-message {font-size: 2em;}')
      self.template = ui_templates.OneSection(self._ui)
      self.template.SetTitle(_TEST_TITLE)

  def tearDown(self):
    phase.OverridePhase(None)

  def runTest(self):
    if self.args.with_goofy:
      self._ui.RunInBackground(self._runTest)
      self._ui.Run()
    else:
      self._runTest()

  def _runTest(self):
    if not self.args.skip_shopfloor:
      shopfloor.update_local_hwid_data(self._dut)

    if self.args.phase:
      phase.OverridePhase(self.args.phase)

    self._allow_unqualified = phase.GetPhase() in [
        phase.PROTO, phase.EVT, phase.DVT]

    if self.args.with_goofy:
      self.template.SetState(_MESSAGE_CHECKING_COMPONENTS)

    cmd = ['hwid', 'verify-components', '--json_output']
    if not self.args.fast_fw_probe:
      cmd += ['--no-fast-fw-probe']
    cmd += ['--components', ','.join(self.args.component_list)]
    cmd += ['--phase', str(phase.GetPhase())]
    results = json.loads(self.factory_par.CheckOutput(cmd))

    logging.info('Probed components: %s', results)
    if self.args.with_goofy:
      event_log.Log('probed_components', results=results)
    self.probed_results = results

    # The format of results is
    # {
    #   component: [
    #     {
    #       'component_name': component_name,
    #       'probed_values': {
    #         value1: {
    #           'raw_value': probed string,
    #           'is_re': bool value
    #         }
    #       },
    #       'error': None or error string
    #     }
    #   ]
    # }
    # extract all errors out
    error_msgs = []
    for class_result in results.values():
      for component_result in class_result:
        if component_result['error']:
          # The format of component_result['error'] is
          # 'Component %r of %r is %s' % (comp_name, comp_cls, comp_status).
          if (self._allow_unqualified and
              component_result['error'].endswith('is unqualified')):
            continue
          error_msgs.append(component_result['error'])
    if error_msgs:
      raise factory.FactoryTestFailure(
          'At least one component is invalid:\n%s' % '\n'.join(error_msgs))
