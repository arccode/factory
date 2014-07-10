# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Writes device VPD.

This test can determine VPD values in several different ways based on the
argument:

- Manually.
- Directly from shopfloor server.
- From shopfloor device data.  If this option is selected with the
  use_shopfloor_device_data arg, the following algorithm is applied:

  - Locale fields (RO initial_locale, keyboard_layout, initial_timezone)
    are set based on the 'locale' entry, which must be an item in the locale
    database in locale.py.
  - Registration codes are set based on the 'ubind_attribute' and
    'gbind_attribute' entries.
  - The RO 'serial_number' field is set based on the 'serial_number' entry.
  - If the device data dictionary contains any keys of the format
    'vpd.ro.xxx' or 'vpd.rw.xxx', the respective field in the RO/RW VPD
    is set.
"""

import logging
import re
import unittest

from cros.factory import cros_locale
from cros.factory.l10n.regions import REGIONS
from cros.factory.test import branding
from cros.factory.test import factory
from cros.factory.test import registration_codes
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.args import Arg
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.test.ui_templates import OneSection, SelectBox
from cros.factory.test.utils import Enum
from cros.factory.tools.build_board import BuildBoard
from cros.factory.utils.process_utils import CheckOutput, Spawn

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
_MSG_MANUAL_INPUT_PROMPT = lambda en, zh: test_ui.MakeLabel(
    'Enter %s: ' % en, u'输入%s: ' % zh, 'vpd-info')
_MSG_MANUAL_SELECT_PROMPT = lambda en, zh: test_ui.MakeLabel(
    'Select %s: </br>' % en, u'选择%s: </br>' % zh, 'vpd-info')
_MSG_ESC_TO_SKIP = lambda en, zh: test_ui.MakeLabel(
    '</br>(ESC to re-use current machine %s)' % en,
    u'</br>(ESC 使用目前已写入机器的%s)' % zh,
    'vpd-info')

_ERR_NO_VALID_VPD = lambda en, zh: test_ui.MakeLabel(
    'Found no valid %s on machine.' % en,
    u'机器上并无合法的%s' % zh,
    'vpd-info test-error')
_ERR_INPUT_INVALID = lambda en, zh: test_ui.MakeLabel(
    'Invalid %s value.' % en,
    u'输入的%s不合法' % zh,
    'vpd-info test-error')

_DEFAULT_VPD_TEST_CSS = '.vpd-info {font-size: 2em;}'

_HTML_MANUAL_INPUT = lambda ele_id: """
    <input type="text" id="%s" style="width: 20em; font-size: 2em;"/>
    <div id="errormsg" class="vpd-info test-error"></div>
""" % ele_id
_EVENT_SUBTYPE_VPD_PREFIX = 'VPD-'
_JS_MANUAL_INPUT = lambda ele_id, event_subtype: """
    ele = document.getElementById("%s");
    window.test.sendTestEvent("%s", ele.value);
""" % (ele_id, event_subtype)

_REGION_SELECT_BOX_ID = 'region_select'
_SELECT_BOX_STYLE = 'font-size: 1.5em; background-color: white;'
_SELECTION_PER_PAGE = 10
_EVENT_SUBTYPE_SELECT_REGION = 'VPD-region'
_JS_SELECT_BOX = lambda ele_id, event_subtype: """
    ele = document.getElementById("%s");
    idx = ele.selectedIndex;
    window.test.sendTestEvent("%s", ele.options[idx].value);
""" % (ele_id, event_subtype)

_VPD_SECTIONS = {'ro': 'RO_VPD', 'rw': 'RW_VPD'}

_REGEX_TYPE = type(re.compile(''))

# String to indicate that rlz_brand_code and customization_id should
# come from device data.
FROM_DEVICE_DATA = 'FROM_DEVICE_DATA'

class WriteVPDTask(FactoryTask):
  """A task to write VPD.

  Args:
    vpd_test: The main VPD TestCase object."""
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

    for (vpd_type, section) in _VPD_SECTIONS.items():
      if not self.test.vpd.get(vpd_type, None):
        continue
      vpds = self.FormatVPDParameter(self.test.vpd[vpd_type])
      Spawn(['vpd', '-i', '%s' % section] + vpds, log=True, check_call=True)

    if self.test.registration_code_map:
      # Check registration codes (fail test if invalid).
      for k in ['user', 'group']:
        if k not in self.test.registration_code_map:
          raise factory.FactoryTestFailure('Missing %s registration code' % k)
        try:
          code_type = {
            'user': registration_codes.RegistrationCode.Type.UNIQUE_CODE,
            'group': registration_codes.RegistrationCode.Type.GROUP_CODE}[k]
          registration_codes.CheckRegistrationCode(
              self.test.registration_code_map[k],
              code_type, BuildBoard().short_name)
        except ValueError as e:
          self.Fail(str(e))

      # Add registration codes, being careful not to log the command.
      logging.info('Storing registration codes.')
      Spawn(['vpd', '-i', 'RW_VPD'] + self.FormatVPDParameter(
            # See <http://src.chromium.org/svn/trunk/src/chrome/
            # browser/chromeos/extensions/echo_private_api.cc>.
            {'ubind_attribute': self.test.registration_code_map['user'],
             'gbind_attribute': self.test.registration_code_map['group']}),
            log=False, check_call=True)
    self.Pass()


class ShopFloorVPDTask(FactoryTask):
  """A task to fetch VPD from shop floor server.

  Args:
    vpd_test: The main VPD TestCase object."""
  def __init__(self, vpd_test):
    super(ShopFloorVPDTask, self).__init__()
    self.test = vpd_test

  def Run(self):
    self.test.template.SetState(_MSG_FETCH_FROM_SHOP_FLOOR)
    self.test.vpd.update(shopfloor.get_vpd())
    if self.test.registration_code_map:
      self.test.registration_code_map.update(
        shopfloor.get_registration_code_map())
    self.Pass()


class VPDInfo(object):
  """A class for checking all the manual input VPD fields."""
  def __init__(self, region, key, label_en, label_zh, value_check):
    if region not in ['ro', 'rw']:
      raise ValueError('VPD region must be either \'ro\' or \'rw\'.')
    self.region = region
    if not isinstance(key, str):
      raise TypeError('VPD id must be a string.')
    self.key = key
    if not isinstance(label_en, (str, unicode)):
      raise TypeError('VPD English label must be a string or unicode string.')
    self.label_en = label_en
    if not isinstance(label_zh, (str, unicode)):
      raise TypeError('VPD Chinese label must be a string or unicode string.')
    self.label_zh = label_zh
    if not isinstance(value_check, (list, str, type(None))):
      raise TypeError('VPD possible values must be a list of strings, '
                      'a regexp string, no None.')
    if isinstance(value_check, list):
      for v in value_check:
        if not isinstance(v, (str, unicode)):
          raise TypeError('VPD possible value needs to be a string.')
      self.value_check = value_check
    elif isinstance(value_check, str):
      self.value_check = re.compile(value_check)
    else: # value_check is None
      self.value_check = value_check


class ManualInputTask(FactoryTask):
  """Factory task to let user manually enter value for the given VPD.

  Partners should fill this in with the correct serial number
  printed on the box and physical device.

  Args:
    vpd_test: The main VPD TestCase object.
    vpd_info: The VPD info field that requires to be manually entered."""
  def __init__(self, vpd_test, vpd_info):
    super(ManualInputTask, self).__init__()
    self.test = vpd_test
    self.vpd_info = vpd_info

  def OnComplete(self, vpd_value):
    if vpd_value:
      # Special handling for registration codes. We need to be careful not to
      # log them.
      if self.vpd_info.key == 'ubind_attribute':
        self.test.registration_code_map['user'] = vpd_value
      elif self.vpd_info.key == 'gbind_attribute':
        self.test.registration_code_map['group'] = vpd_value
      else:
        self.test.vpd[self.vpd_info.region][self.vpd_info.key] = vpd_value
    self.Pass()

  def OnEnterPressed(self, event):
    vpd_value = event.data
    if vpd_value:
      if (isinstance(self.vpd_info.value_check, _REGEX_TYPE)) and (
          not self.vpd_info.value_check.match(vpd_value)):
        self.test.ui.SetHTML(_ERR_INPUT_INVALID(
            self.vpd_info.label_en, self.vpd_info.label_zh), id='errormsg')
        self.test.ui.SetSelected(self.vpd_info.key)
        return
      self.OnComplete(vpd_value)

  def OnESCPressed(self):
    vpd_value = CheckOutput(['vpd', '-i', _VPD_SECTIONS[self.vpd_info.region],
                            '-g', self.vpd_info.key]).strip()
    if not vpd_value:
      self.test.ui.SetHTML(_ERR_NO_VALID_VPD(
          self.vpd_info.label_en, self.vpd_info.label_zh), id='errormsg')
    else:
      self.OnComplete(None)

  def Run(self):
    if isinstance(self.vpd_info.value_check, list):
      # Renders a select box to list all the possible values.
      self.RenderSelectBox()
    else:
      self.RenderInputBox()

  def _AppendState(self, html):
    self.test.template.SetState(html, append=True)

  def RenderSelectBox(self):
    vpd_event_subtype = _EVENT_SUBTYPE_VPD_PREFIX + self.vpd_info.key
    self.test.template.SetState(_MSG_MANUAL_SELECT_PROMPT(
        self.vpd_info.label_en, self.vpd_info.label_zh))
    select_box = SelectBox(self.vpd_info.key, _SELECTION_PER_PAGE,
                           _SELECT_BOX_STYLE)
    for index, value in enumerate(self.vpd_info.value_check):
      select_box.InsertOption(value, '%s - %s' % (index, value))
    select_box.SetSelectedIndex(0)
    self._AppendState(select_box.GenerateHTML())
    self._AppendState(_MSG_HOW_TO_SELECT)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_SELECT_BOX(
        self.vpd_info.key, vpd_event_subtype))
    self.test.ui.AddEventHandler(vpd_event_subtype, self.OnEnterPressed)
    self.test.ui.SetFocus(self.vpd_info.key)

  def RenderInputBox(self):
    vpd_event_subtype = _EVENT_SUBTYPE_VPD_PREFIX + self.vpd_info.key
    self.test.template.SetState(_MSG_MANUAL_INPUT_PROMPT(
        self.vpd_info.label_en, self.vpd_info.label_zh))
    self._AppendState(_HTML_MANUAL_INPUT(self.vpd_info.key))
    self._AppendState(_MSG_ESC_TO_SKIP(self.vpd_info.label_en,
                                       self.vpd_info.label_zh))
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_MANUAL_INPUT(
        self.vpd_info.key, vpd_event_subtype))
    self.test.ui.AddEventHandler(vpd_event_subtype, self.OnEnterPressed)
    self.test.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnESCPressed())
    self.test.ui.SetFocus(self.vpd_info.key)

  def Cleanup(self):
    self.test.ui.UnbindKey(test_ui.ENTER_KEY)
    self.test.ui.UnbindKey(test_ui.ESCAPE_KEY)


class SelectRegionTask(FactoryTask):
  """Factory task to select region info (locale, keyboard layout, timezone).

  Args:
    vpd_test: The main VPD TestCase object."""
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
    select_box = SelectBox(_REGION_SELECT_BOX_ID, _SELECTION_PER_PAGE,
                           _SELECT_BOX_STYLE)
    for index, region in enumerate(self.region_list):
      select_box.InsertOption(index, '%s - (%s %s %s)' % (
                                     (region[3],) + region[:3]))
    select_box.SetSelectedIndex(0)
    self.test.template.SetState(select_box.GenerateHTML(), append=True)
    self.test.template.SetState(_MSG_HOW_TO_SELECT, append=True)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_SELECT_BOX(
        _REGION_SELECT_BOX_ID, _EVENT_SUBTYPE_SELECT_REGION))
    self.test.ui.AddEventHandler(_EVENT_SUBTYPE_SELECT_REGION, self.SaveVPD)
    self.test.ui.SetFocus(_REGION_SELECT_BOX_ID)

  def Run(self):
    if self.regions is None:
      self.regions = cros_locale.DEFAULT_REGION_LIST
    self.region_list = [cros_locale.BuildRegionInformation(entry) if entry[0]
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
    Arg('override_vpd_entries', dict,
        'A dict of override VPD entries. Unlike override_vpd, it only '
        'overrides some key-value pairs instead of the whole VPD section.'
        'It does not require engineering mode. The dict should be of the '
        'format: {"ro": { RO_VPD key-value pairs }, "rw": { RW_VPD key-value '
        'pairs }}',
        default=None, optional=True),
    Arg('store_registration_codes', bool,
        'Whether to store registration codes onto the machine.', default=False),
    Arg('task_list', list, 'A list of tasks to execute.',
        default=[VPDTasks.serial, VPDTasks.region]),
    Arg('use_shopfloor_device_data', bool,
        'If shopfloor is enabled, use accumulated data in shopfloor device '
        'data dictionary instead of contacting shopfloor server again. '
        'See file-level docs in vpd.py for more information.',
        default=False),
    Arg('extra_device_data_fields', list,
        'Extra fields to write to VPD from shopfloor device_data.  Each item '
        'is a tuple of the form ("ro", key) or ("rw", key) meaning that the '
        'value from key should be added to the ro or rw VPD.  This option '
        'only applies if use_shopfloor_device_data is True.',
        default=[]),
    Arg('manual_input_fields', list, 'A list of tuples (vpd_region, key, '
        'en_display_name, zh_display_name, VALUE_CHECK) indicating the VPD '
        'fields that need to be manually entered.\n'
        'VALUE_CHECK can be a list of strings, a regexp string, or None. '
        'If VALUE_CHECK is None or a regexp string then a text input box will '
        'show up to let user input value. The entered value will be validated '
        'if VALUE_CHECK is a regexp string. Otherwise a select box containing '
        'all the possible values will be used to let user select a value from '
        'it.', default=[], optional=True),
    Arg('allow_multiple_l10n', bool, 'True to allow multiple locales and '
        'keyboards.  Fully supported only in M35+ FSIs, so this is disabled '
        'by default', default=False, optional=True),
    Arg('rlz_brand_code', str,
        'RLZ brand code to write to RO VPD.  This may be any of:\n'
        '\n'
        '- A fixed string\n'
        '- None, to not set any value at all\n'
        '- The string `"FROM_DEVICE_DATA"`, to use a value obtained from\n'
        '  device data.',
        default=None, optional=True),
    Arg('customization_id', str,
        'Customization ID to write to RO VPD.  This may be any of:\n'
        '\n'
        '- A fixed string\n'
        '- None, to not set any value at all\n'
        '- The string `"FROM_DEVICE_DATA"`, to use a value obtained from\n'
        '  device data.',
        default=None, optional=True),
  ]

  def _ReadShopFloorDeviceData(self):
    device_data = shopfloor.GetDeviceData()
    required_keys = set(['serial_number', 'region',
                         'ubind_attribute', 'gbind_attribute'] +
                        [x[1] for x in self.args.extra_device_data_fields])
    missing_keys = required_keys - set(device_data.keys())
    if missing_keys:
      self.fail('Missing keys in shopfloor device data: %r' %
                sorted(missing_keys))

    self.vpd['ro']['serial_number'] = device_data['serial_number']

    self.assertIn(device_data['region'], REGIONS)
    region = REGIONS[device_data['region']]

    self.vpd['ro'].update(region.GetVPDSettings(self.args.allow_multiple_l10n))

    for ro_or_rw, key in self.args.extra_device_data_fields:
      self.vpd[ro_or_rw][key] = device_data[key]

    for k, v in device_data.iteritems():
      match = re.match(r'$vpd\.(ro|rw)\.(.+)^', k)
      if match:
        self.vpd[match.group(1)][match.group(2)] = v

    self.registration_code_map = {
        'user': device_data['ubind_attribute'],
        'group': device_data['gbind_attribute'],
        }

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = OneSection(self.ui)
    self.ui.AppendCSS(_DEFAULT_VPD_TEST_CSS)
    self.tasks = []
    self.registration_code_map = {}
    self.vpd = {'ro': {}, 'rw': {}}
    if self.args.override_vpd:
      if self.ui.InEngineeringMode():
        self.vpd = self.args.override_vpd
      else:
        self.ui.Fail('override_vpd is allowed only in engineering mode.')
        return

    if self.args.override_vpd and self.args.override_vpd_entries:
      self.ui.Fail(
          'override_vpd and override_vpd_entries cannot be enabled at the '
          'same time.')
      return

    # Check format of extra_device_data_fields parameter.
    for i in self.args.extra_device_data_fields:
      self.assertTrue(isinstance(i, tuple), i)
      self.assertEquals(2, len(i))
      self.assertIn(i[0], ['ro', 'rw'])

    if not (self.args.override_vpd and self.ui.InEngineeringMode()):
      if shopfloor.is_enabled():
        # Grab from ShopFloor, then input manual fields (if any).
        if self.args.use_shopfloor_device_data:
          self._ReadShopFloorDeviceData()
        else:
          self.tasks += [ShopFloorVPDTask(self)]
        for v in self.args.manual_input_fields:
          self.tasks += [ManualInputTask(
              self, VPDInfo(v[0], v[1], v[2], v[3], v[4]))]
      else:
        if self.VPDTasks.serial in self.args.task_list:
          self.args.manual_input_fields.insert(
              0, ('ro', 'serial_number', 'Serial Number', u'序号', None))
        for v in self.args.manual_input_fields:
          self.tasks += [ManualInputTask(
              self, VPDInfo(v[0], v[1], v[2], v[3], v[4]))]
        if self.VPDTasks.region in self.args.task_list:
          self.tasks += [SelectRegionTask(self)]
      if self.args.override_vpd_entries:
        for vpd_section, key_value_dict in (
            self.args.override_vpd_entries.iteritems()):
          self.vpd[vpd_section].update(key_value_dict)

    self.ReadBrandingFields()

    self.tasks += [WriteVPDTask(self)]

  def ReadBrandingFields(self):
    cached_device_data = None

    for attr, regexp in (
      ('rlz_brand_code', branding.RLZ_BRAND_CODE_REGEXP),
      ('customization_id', branding.CUSTOMIZATION_ID_REGEXP)):
      arg_value = getattr(self.args, attr)

      if arg_value is None:
        continue

      if arg_value == FROM_DEVICE_DATA:
        if cached_device_data is None:
          cached_device_data = shopfloor.GetDeviceData()
        value = cached_device_data.get(attr)
        if value is None:
          raise ValueError('%s not present in device data' % attr)
      else:
        # Fixed string; just use the value directly.
        value = arg_value

      # Check the format.
      if not regexp.match(value):
        raise ValueError('Bad format for %s %r '
                         '(expected it to match regexp %r)' % (
            attr, value, regexp.pattern))

      # We're good to go!
      self.vpd['ro'][attr] = value

  def runTest(self):
    FactoryTaskManager(self.ui, self.tasks).Run()
