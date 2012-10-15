# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

from cros.factory import locale
from cros.factory.test import factory
from cros.factory.test import registration_codes
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.test.ui_templates import OneSection, SelectBox
from cros.factory.test.utils import Enum
from cros.factory.utils.process_utils import Spawn

_MSG_FETCH_FROM_SHOP_FLOOR = test_ui.MakeLabel(
    'Fetching VPD from shop floor server...',
    u'从 Shop Floor 服务器抓取 VPD 中...',
    'vpd-info')
_MSG_WRITING = test_ui.MakeLabel(
    'Writing VPD:</br>',
    u'写入 VPD:</br>',
    'vpd-info')
_MSG_SELECT_REGION = test_ui.MakeLabel(
    'Select region:</br>', u'选择区域代码:</br>', 'vpd-info')
_MSG_HOW_TO_SELECT = test_ui.MakeLabel(
    '</br>Select with ENTER', u'</br>按 ENTER 选择', 'vpd-info')
# The "ESC" is available primarily for RMA and testing process, when operator
# does not want to change existing serial number.
_MSG_SERIAL_NUMBER_PROMPT = test_ui.MakeLabel(
    'Enter Serial Number: ', u'输入序号: ', 'vpd-info')
_MSG_ESC_TO_SKIP = test_ui.MakeLabel(
    '</br>(ESC to re-use current machine serial number)',
    u'</br>(ESC 使用目前已写入机器的序号)',
    'vpd-info')

_ERR_NO_VALID_SERIAL_NUMBER = test_ui.MakeLabel(
    'Found no valid serial number on machine.',
    u'机器上并无合法的序号',
    'vpd-info test-error')

_DEFAULT_VPD_TEST_CSS = '.vpd-info {font-size: 2em;}'

_SERIAL_INPUT_ID = 'serial'
_HTML_SERIAL_NUMBER = """
    <input type="text" id="%s" style="width: 20em; font-size: 2em;"/>
    <div id="errormsg" class="vpd-info test-error"></div>
""" % _SERIAL_INPUT_ID
_EVENT_SUBTYPE_VPD_SERIAL = 'VPD-serial'
_JS_SERIAL_NUMBER = """
    ele = document.getElementById("%s");
    window.test.sendTestEvent("%s", ele.value);
""" % (_SERIAL_INPUT_ID, _EVENT_SUBTYPE_VPD_SERIAL)

_SELECT_BOX_ID = 'region_select'
_SELECT_BOX_STYLE = 'font-size: 1.5em; background-color: white;'
_SELECTION_PER_PAGE = 10
_EVENT_SUBTYPE_SELECT_REGION = 'VPD-region'
_JS_SELECT_REGION = """
    ele = document.getElementById("%s");
    idx = ele.selectedIndex;
    window.test.sendTestEvent("%s", ele.options[idx].value);
""" % (_SELECT_BOX_ID, _EVENT_SUBTYPE_SELECT_REGION)


class WriteVPDTask(FactoryTask):
  def __init__(self, vpd_test):
    super(WriteVPDTask, self).__init__()
    self.test = vpd_test

  def FormatVPDParameter(self, vpd_dict):
    """Formats a key-value dictionary into command line VPD syntax."""
    # Writes in sorted ordering so the VPD structure will be more
    # deterministic.
    ret = []
    for key in sorted(vpd_dict):
      ret += ['-s', '%s=%s' % (key, vpd_dict[key])]
    return ret

  def Run(self):
    # Flatten key-values in VPD dictionary.
    vpd = self.test.vpd
    vpd_list = []

    for vpd_type in ('ro', 'rw'):
      vpd_list += ['%s: %s = %s' % (vpd_type, key, vpd[vpd_type][key])
                   for key in sorted(vpd[vpd_type])]
    if self.test.registration_code_map:
      vpd_list += ['rw: registration codes']

    self.test.template.SetState(_MSG_WRITING)
    self.test.template.SetState('<div class="vpd-info">%s</div>' % (
                                '</br>'.join(vpd_list)), append=True)

    VPD_SECTIONS = (('RO_VPD', 'ro'), ('RW_VPD', 'rw'))
    for (section, vpd_type) in VPD_SECTIONS:
      if not self.test.vpd.get(vpd_type, None):
        continue
      vpds = self.FormatVPDParameter(self.test.vpd[vpd_type])
      Spawn(['vpd', '-i', '%s' % section] + vpds, log=True, check_call=True)

    if self.test.registration_code_map is not None:
      # Check registration codes (fail test if invalid).
      for k in ['user', 'group']:
        if k not in self.test.registration_code_map:
          raise factory.FactoryTestFailure('Missing %s registration code' % k)
        registration_codes.CheckRegistrationCode(
            self.test.registration_code_map[k])

      # Add registration codes, being careful not to log the command.
      logging.info('Storing registration codes.')
      Spawn(['vpd', '-i', '%s' % 'RW_VPD'] + self.FormatVPDParameter(
            # See <http://src.chromium.org/svn/trunk/src/chrome/
            # browser/chromeos/extensions/echo_private_api.cc>.
            {'ubind_attribute': self.test.registration_code_map['user'],
             'gbind_attribute': self.test.registration_code_map['group']}),
            log=False, check_call=True)
    self.Pass()


class ShopFloorVPDTask(FactoryTask):
  """A task to fetch VPD from shop floor server."""
  def __init__(self, vpd_test):
    super(ShopFloorVPDTask, self).__init__()
    self.test = vpd_test

  def Run(self):
    self.test.template.SetState(_MSG_FETCH_FROM_SHOP_FLOOR)
    self.test.vpd.update(shopfloor.get_vpd())
    if self.test.registration_code_map is not None:
      self.test.registration_code_map.update(
        shopfloor.get_registration_code_map())
    factory.console.info(self.test.vpd)
    self.Pass()


class SerialNumberTask(FactoryTask):
  """Factory task to select an unique serial number for VPD.

  Partners should fill this in with the correct serial number
  printed on the box and physical device."""
  def __init__(self, vpd_test):
    super(SerialNumberTask, self).__init__()
    self.test = vpd_test

  def OnComplete(self, serial_number):
    if serial_number:
      self.test.vpd['ro']['serial_number'] = serial_number.strip()
    self.Pass()

  def OnEnterPressed(self, event):
    sn = event.data
    if sn:
      self.OnComplete(sn)

  def OnESCPressed(self):
    vpd_sn = Spawn(['vpd', '-g', 'serial_number'],
                   check_output=True).stdout_data.strip()
    if not vpd_sn:
      self.test.ui.SetHTML(_ERR_NO_VALID_SERIAL_NUMBER, id='errormsg')
    else:
      self.OnComplete(None)

  def Run(self):
    self.test.template.SetState(_MSG_SERIAL_NUMBER_PROMPT)
    self.test.template.SetState(_HTML_SERIAL_NUMBER, append=True)
    self.test.template.SetState(_MSG_ESC_TO_SKIP, append=True)
    self.test.ui.SetFocus(_SERIAL_INPUT_ID)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_SERIAL_NUMBER)
    self.test.ui.AddEventHandler(_EVENT_SUBTYPE_VPD_SERIAL, self.OnEnterPressed)
    self.test.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnESCPressed())

  def Cleanup(self):
    self.test.ui.UnbindKey(test_ui.ENTER_KEY)
    self.test.ui.UnbindKey(test_ui.ESCAPE_KEY)


class SelectRegionTask(FactoryTask):
  """Factory task to select region info (locale, keyboard layout, timezone)."""
  def __init__(self, vpd_test, regions=None):
    super(SelectRegionTask, self).__init__()
    self.test = vpd_test
    self.regions = regions
    self.region_list = None

  def SaveVPD(self, event):
    index = int(event.data)
    (initial_locale, keyboard_layout, initial_timezone, _) = (
        self.region_list[index])
    if initial_locale and keyboard_layout != 'Skip' and initial_timezone:
      self.test.vpd['ro']['initial_locale'] = initial_locale
      self.test.vpd['ro']['keyboard_layout'] = keyboard_layout
      self.test.vpd['ro']['initial_timezone'] = initial_timezone
    self.Pass()

  def RenderPage(self):
    self.test.template.SetState(_MSG_SELECT_REGION)
    select_box = SelectBox(_SELECT_BOX_ID, _SELECTION_PER_PAGE,
                           _SELECT_BOX_STYLE)
    for index, region in enumerate(self.region_list):
      select_box.InsertOption(index, '%s - (%s %s %s)' % (
                                     (region[3],) + region[:3]))
    select_box.SetSelectedIndex(0)
    self.test.template.SetState(select_box.GenerateHTML(), append=True)
    self.test.template.SetState(_MSG_HOW_TO_SELECT, append=True)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_SELECT_REGION)
    self.test.ui.AddEventHandler(_EVENT_SUBTYPE_SELECT_REGION, self.SaveVPD)
    self.test.ui.SetFocus(_SELECT_BOX_ID)

  def Run(self):
    if self.regions is None:
      self.regions = locale.DEFAULT_REGION_LIST
    self.region_list = [locale.BuildRegionInformation(entry) if entry[0]
                        else ('', 'Skip', '', 'None')
                        for entry in self.regions]
    self.RenderPage()


class VPDTest(unittest.TestCase):
  VPDTasks = Enum(['serial', 'region'])

  ARGS = [
    Arg('override_vpd', dict,
        'A dict of override VPDs. This is for development purpose and is '
        'useable only in engineering mode. The dict should be of the format: '
        '{"ro": { RO_VPD key-value pairs }, "rw": { RW_VPD key-value pairs }}',
        default=None, optional=True),
    Arg('store_registration_codes', bool,
        'Whether to store registration codes onto the machine.', default=False,
        optional=True),
    Arg('task_list', list, 'A list of tasks to execute.',
        default=[VPDTasks.serial, VPDTasks.region], optional=True)
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_DEFAULT_VPD_TEST_CSS)
    self.tasks = []
    self.registration_code_map = (
        {} if self.args.store_registration_codes else None)
    self.vpd = {'ro': {}, 'rw': {}}
    if self.args.override_vpd:
      if self.ui.IsEngineeringMode():
        self.vpd = self.args.override_vpd
      else:
        self.ui.Fail('override_vpd is allowed only in engineering mode.')
        return

    if not (self.args.override_vpd and self.ui.IsEngineeringMode()):
      if shopfloor.is_enabled():
        self.tasks += [ShopFloorVPDTask(self)]
      else:
        if self.VPDTasks.serial in self.args.task_list:
          self.tasks += [SerialNumberTask(self)]
        if self.VPDTasks.region in self.args.task_list:
          self.tasks += [SelectRegionTask(self)]
    self.tasks += [WriteVPDTask(self)]

  def runTest(self):
    FactoryTaskManager(self.ui, self.tasks).Run()
