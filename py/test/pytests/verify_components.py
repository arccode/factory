# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# DESCRIPTION :
# This is a test that verifies only expected components are installed to the
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

class CheckComponentsTask(FactoryTask):
  '''Checks the given components are in the components db.'''

  def __init__(self, test):
    super(CheckComponentsTask, self).__init__()
    self._test = test

  def Run(self):
    '''Runs the test.

    The probing results will be stored in test.component_list.
    '''

    self._test.template.SetState(_MESSAGE_CHECKING_COMPONENTS)
    try:
      result = self._test.gooftool.VerifyComponents(self._test.component_list)
    except ValueError, e:
      self.Fail(str(e))
      return

    logging.info("Probed components: %s", result)

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

class VerifyComponentsTest(unittest.TestCase):
  ARGS = [
    Arg('component_list', list,
        'A list of components to be verified'),
  ]

  def __init__(self, *args, **kwargs):
    super(VerifyComponentsTest, self).__init__(*args, **kwargs)
    self._ui = test_ui.UI()
    self._ui.AppendCSS('.progress-message {font-size: 2em;}')
    self.component_list = None
    self.gooftool = None
    self.template = ui_templates.OneSection(self._ui)
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):
    self.component_list = self.args.component_list
    self.gooftool = Gooftool()

    FactoryTaskManager(self._ui, [CheckComponentsTask(self)]).Run()

