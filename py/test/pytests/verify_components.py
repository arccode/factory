# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# DESCRIPTION :
# This is a test that verifies only expected components are installed in the
# DUT.
"""Factory test to verify components."""

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.test import phase
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.event_log import Log
from cros.factory.test.factory import FactoryTestFailure

_TEST_TITLE = test_ui.MakeLabel('Components Verification Test',
                                u'元件验证测试')
_MESSAGE_CHECKING_COMPONENTS = test_ui.MakeLabel(
    'Checking components...', u'元件验证中...', 'progress-message')


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
          default=False, optional=True)
  ]

  def setUp(self):
    self._shopfloor = shopfloor
    self._ui = test_ui.UI()
    self._ui.AppendCSS('.progress-message {font-size: 2em;}')

    # Don't initialize yet; let update_local_hwid_data run first.
    self.hwid_db = None

    self.probed_results = None
    self._allow_unqualified = None
    self.template = ui_templates.OneSection(self._ui)
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):
    if not self.args.skip_shopfloor:
      shopfloor.update_local_hwid_data()
    self.hwid_db = database.Database.Load()

    self._allow_unqualified = phase.GetPhase() in [
        phase.PROTO, phase.EVT, phase.DVT]

    self.template.SetState(_MESSAGE_CHECKING_COMPONENTS)
    probed_results = hwid_utils.GetProbedResults(
        fast_fw_probe=self.args.fast_fw_probe)
    results = hwid_utils.VerifyComponents(
        self.hwid_db, probed_results, self.args.component_list)

    logging.info('Probed components: %s', results)
    Log('probed_components', results=results)
    self.probed_results = results

    # extract all errors out
    error_msgs = []
    for class_result in results.values():
      for component_result in class_result:
        if component_result.error:
          # The format of component_result.error is
          # 'Component %r of %r is %s' % (comp_name, comp_cls, comp_status).
          if (self._allow_unqualified and
              component_result.error.endswith('is unqualified')):
            continue
          error_msgs.append(component_result.error)
    if error_msgs:
      raise FactoryTestFailure('At least one component is invalid:\n%s' %
                               '\n'.join(error_msgs))
