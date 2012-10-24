# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# DESCRIPTION :
# This is a test that verifies only expected components are installed in the
# DUT.

import logging
import unittest

import factory_common # pylint: disable=W0611
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.gooftool import Gooftool

_TEST_TITLE = test_ui.MakeLabel('Components Verification Test',
                                u'元件验证测试')
_MESSAGE_CHECKING_COMPONENTS = test_ui.MakeLabel(
    'Checking components...', u'元件验证中...', 'progress-message')

_MESSAGE_MATCHING_ANY_BOM = test_ui.MakeLabel(
    'Matching BOM from the list...', u'正在从列表匹配 BOM ...',
    'progress-message')


class CheckComponentsTask(FactoryTask):
  '''Checks the given components are in the components db.'''

  def __init__(self, test):
    super(CheckComponentsTask, self).__init__()
    self._test = test

  def Run(self):
    """Runs the test.

    The probing results will be stored in test.component_list.
    """

    self._test.template.SetState(_MESSAGE_CHECKING_COMPONENTS)
    try:
      result = self._test.gooftool.VerifyComponents(self._test.component_list)
    except ValueError, e:
      self.Fail(str(e))
      return

    logging.info("Probed components: %s", result)
    self._test.probed_results = result

    # extract all errors out
    error_msgs = []
    for class_result in result.values():
      for component_result in class_result:
        if component_result.error:
          error_msgs.append(component_result.error)
    if error_msgs:
      self.Fail("At least one component is invalid:\n%s" %
                '\n'.join(error_msgs))
    else:
      self.Pass()

class VerifyAnyBOMTask(FactoryTask):
  '''Verifies the given probed_results matches any of the given BOMs.'''

  def __init__(self, test, bom_whitelist):
    """Constructor.

    Args:
      test: The test itself which contains results from other tasks.
      bom_whitelist: The whitelist for BOMs that are allowed to match.
    """
    super(VerifyAnyBOMTask, self).__init__()
    self._test = test
    self._bom_whitelist = bom_whitelist

  def Run(self):
    """Verifies probed results against all listed BOMs.

    If a match is found for any of the BOMs, the test will pass
    """

    self._test.template.SetState(_MESSAGE_MATCHING_ANY_BOM)

    all_mismatches = {}  # tracks all mismatches for each BOM for debugging
    for bom in self._bom_whitelist:
      mismatches = self._test.gooftool.FindBOMMismatches(
          self._test.board, bom, self._test.probed_results)
      if not mismatches:
        logging.info("Components verified with BOM %r", bom)
        self.Pass()
        return
      else:
        all_mismatches[bom] = mismatches

    self.Fail("Probed components did not match any of listed BOM: %s" %
              all_mismatches)


class VerifyComponentsTest(unittest.TestCase):
  ARGS = [
    Arg('component_list', list,
        'A list of components to be verified'),
    Arg('board', str,
        'The board which includes the BOMs to whitelist.',
        optional=True),
    Arg('bom_whitelist', list,
        'A whitelist of BOMs that the component probed results must match. '
        'When specified, probed components must match at least one BOM',
        optional=True),
  ]

  def __init__(self, *args, **kwargs):
    super(VerifyComponentsTest, self).__init__(*args, **kwargs)
    self._ui = test_ui.UI()
    self._ui.AppendCSS('.progress-message {font-size: 2em;}')
    self.board = None
    self.component_list = None
    self.gooftool = Gooftool()
    self.probed_results = None
    self.template = ui_templates.OneSection(self._ui)
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):
    self.component_list = self.args.component_list
    self.board = self.args.board

    task_list = [CheckComponentsTask(self)]

    # Run VerifyAnyBOMTask if the BOM whitelist is specified.
    if self.args.bom_whitelist:
      task_list.append(VerifyAnyBOMTask(self, self.args.bom_whitelist))

    FactoryTaskManager(self._ui, task_list).Run()

