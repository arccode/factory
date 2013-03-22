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
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.factory import FactoryTestFailure
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.gooftool import Gooftool

_TEST_TITLE = test_ui.MakeLabel('Components Verification Test',
                                u'元件验证测试')
_MESSAGE_CHECKING_COMPONENTS = test_ui.MakeLabel(
    'Checking components...', u'元件验证中...', 'progress-message')

_MESSAGE_MATCHING_ANY_BOM = test_ui.MakeLabel(
    'Matching BOM from the list...', u'正在从列表匹配 BOM ...',
    'progress-message')
_MSG_NO_SHOP_FLOOR_SERVER_URL = test_ui.MakeLabel(
    'Shopfloor server URL is not specified!', u'未指定 Shopfloor 服务器位址!')


class CheckComponentsTask(FactoryTask):
  '''Checks the given components are in the components db.'''

  def __init__(self, test, allow_missing=False):
    super(CheckComponentsTask, self).__init__()
    self._test = test
    self._allow_missing = allow_missing

  def Run(self):
    """Runs the test.

    The probing results will be stored in test.component_list.
    """

    self._test.template.SetState(_MESSAGE_CHECKING_COMPONENTS)
    try:
      if self._test.args.hwid_version == 2:
        result = self._test.gooftool.VerifyComponents(self._test.component_list)
      elif self._test.args.hwid_version == 3:
        result = self._test.gooftool.VerifyComponentsV3(
            self._test.component_list)
    except ValueError, e:
      self.Fail(str(e))
      return

    logging.info("Probed components: %s", result)
    self._test.probed_results = result

    # extract all errors out
    error_msgs = []
    for class_result in result.values():
      for component_result in class_result:
        # If the component is missing, but it is allowed, ignore the error.
        if not component_result.probed_string and self._allow_missing:
          continue
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
    logging.info("Verifying BOMs: %r", self._bom_whitelist)

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

def LookupBOMList(shopfloor_wrapper, aux_table, aux_field, bom_mapping):
  """Looks up the BOMs from a mapping table and return the list.

  Args:
    shopfloor_wrapper: A shopfloor wrapper for accessing the aux data.
    aux_table_name: The name of the aux table that will be used for lookup.
    aux_field: The name of the aux field that will be used for lookup.
    bom_mapping: The mapping from the aux field value to a list of BOM names.
        e.g. {True: ['BLUE', 'RED'], False: ['YELLOW']}

  Returns:
    A list of BOMs that is found in bom_mapping based on the value of
    aux_field column in the aux_table.

  Raises:
    ValueError: If the value is not found in aux_table.aux_field.
  """

  if not shopfloor_wrapper.get_server_url():
    raise ValueError("Shopfloor URL is missing")

  value = None
  try:
    aux = shopfloor_wrapper.get_selected_aux_data(aux_table)
    value = aux.get(aux_field)
    if value is None:
      raise ValueError("Retrieved None value from %s.%s" % (
          aux_table, aux_field))
  except ValueError, e:
    raise ValueError("Unable to obtain the aux value for %s.%s: %s" % (
        aux_table, aux_field, e))

  if value not in bom_mapping:
    raise ValueError("Unable to lookup %r from the mapping table %s" % (
        value, bom_mapping))

  return bom_mapping[value]


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
    Arg('aux_table', str,
        'The name of the aux lookup table used for bom_mapping',
        optional=True),
    Arg('aux_field', str,
        'The name of the field for looking up the BOM list to verify.',
        optional=True),
    Arg('bom_mapping', dict,
        'A mapping from the values of aux_field to BOM lists. The probed '
        'result must match at least one BOM from the according list when '
        'specified. The matching is triggered only when a mapping if found. '
        'If no mapping is found, an error will be raised. e.g. '
        '{True: ["APPLE", "MELON"], False: ["ORANGE"]}',
        optional=True),
    Arg('hwid_version', int,
        'The version of HWID functions to call. This should be set to "3" if '
        'the DUT is using HWIDv3.',
        default=2, optional=True)
  ]
  def setUp(self):
    self._shopfloor = shopfloor
    self._ui = test_ui.UI()
    self._ui.AppendCSS('.progress-message {font-size: 2em;}')
    self.board = None
    self.component_list = None
    if self.args.hwid_version not in [2, 3]:
      raise FactoryTestFailure(
          'Invalid HWID version: %r' % self.args.hwid_version)
    self.gooftool = Gooftool(hwid_version=self.args.hwid_version)
    self.probed_results = None
    self.template = ui_templates.OneSection(self._ui)
    self.template.SetTitle(_TEST_TITLE)

  def runTest(self):
    shopfloor.update_local_hwid_data()
    self.component_list = self.args.component_list
    self.board = self.args.board

    allow_missing = (self.args.bom_whitelist != None)
    task_list = [CheckComponentsTask(self, allow_missing)]

    # TODO(jcliang): Remove this after we support BOM verification in HWIDv3.
    if ((self.args.hwid_version == 3) and
        (self.args.bom_whitelist or self.args.bom_mapping)):
      raise FactoryTestFailure('BOM verifications is not supported in HWIDv3')

    # Run VerifyAnyBOMTask if the BOM whitelist is specified.
    if self.args.bom_whitelist:
      task_list.append(VerifyAnyBOMTask(self, self.args.bom_whitelist))

    # Run VerifyAnyBOMTask for the BOM list found from the BOM mapping
    # if bom_mapping is specified.
    if self.args.bom_mapping:
      task_list.append(VerifyAnyBOMTask(
          self,
          LookupBOMList(self._shopfloor, self.args.aux_table,
                        self.args.aux_field, self.args.bom_mapping)))

    FactoryTaskManager(self._ui, task_list).Run()

