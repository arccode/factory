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

  - Region data (RO region) is set based on 'region' entry, which must be an
    item in the region database from region.py.
  - Registration codes are set based on the 'ubind_attribute' and
    'gbind_attribute' entries.
  - The RO 'serial_number' field is set based on the 'serial_number' entry.
  - If the device data dictionary contains any keys of the format
    'vpd.ro.xxx' or 'vpd.rw.xxx', the respective field in the RO/RW VPD
    is set.
"""

from __future__ import print_function

import logging
import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import factory
from cros.factory.test import factory_task
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.l10n import regions
from cros.factory.test.rules import branding
from cros.factory.test.rules import registration_codes
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.tools import build_board
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils

_MSG_FETCH_FROM_SHOP_FLOOR = i18n_test_ui.MakeI18nLabelWithClass(
    'Fetching VPD from shop floor server...', 'vpd-info')
_MSG_WRITING = i18n_test_ui.MakeI18nLabelWithClass(
    'Writing VPD:<br>', 'vpd-info')
_MSG_SELECT_REGION = i18n_test_ui.MakeI18nLabelWithClass(
    'Select region:<br>', 'vpd-info')
_MSG_HOW_TO_SELECT = i18n_test_ui.MakeI18nLabelWithClass(
    '<br>Select with ENTER', 'vpd-info')
_MSG_MANUAL_INPUT_PROMPT = lambda vpd_label: (
    i18n_test_ui.MakeI18nLabelWithClass(
        'Enter {vpd_label}: ', 'vpd-info', vpd_label=vpd_label))
_MSG_MANUAL_SELECT_PROMPT = lambda vpd_label: (
    i18n_test_ui.MakeI18nLabelWithClass(
        'Select {vpd_label}: <br>', 'vpd-info', vpd_label=vpd_label))
# The "ESC" is available primarily for RMA and testing process, when operator
# does not want to change existing serial number.
_MSG_ESC_TO_SKIP = lambda vpd_label: i18n_test_ui.MakeI18nLabelWithClass(
    '<br>(ESC to re-use current machine {vpd_label})',
    'vpd-info', vpd_label=vpd_label)

_ERR_NO_VALID_VPD = lambda vpd_label: i18n_test_ui.MakeI18nLabelWithClass(
    'Found no valid {vpd_label} on machine.',
    'vpd-info test-error', vpd_label=vpd_label)
_ERR_INPUT_INVALID = lambda vpd_label: i18n_test_ui.MakeI18nLabelWithClass(
    'Invalid {vpd_label} value.', 'vpd-info test-error', vpd_label=vpd_label)

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

_VPD_SECTIONS = ['ro', 'rw']

_REGEX_TYPE = type(re.compile(''))

# String to indicate that rlz_brand_code and customization_id should
# come from device data.
FROM_DEVICE_DATA = 'FROM_DEVICE_DATA'


class WriteVPDTask(factory_task.FactoryTask):
  """A task to write VPD.

  Args:
    vpd_test: The main VPD TestCase object.
  """

  def __init__(self, vpd_test):
    super(WriteVPDTask, self).__init__()
    self.test = vpd_test

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
        '<br>'.join(vpd_list)), append=True)

    for vpd_type in self.test.vpd:
      partition = self.test.dut.vpd.GetPartition(vpd_type)
      partition.Update(self.test.vpd[vpd_type])

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
              self.test.registration_code_map[k], code_type,
              self.test.args.override_registration_codes_device or
              build_board.BuildBoard().short_name)
        except ValueError as e:
          self.Fail(str(e))

      # For legacy registration code, it was found that some devices were
      # assigned with same user/group values. So add a simple assertion here.
      # with same user/group values and that should be apparently wrong value.
      if (self.test.registration_code_map['user'] ==
          self.test.registration_code_map['group']):
        raise factory.FactoryTestFailure(
            'user code and group code should not be the same')

      # Add registration codes, being careful not to log the command.
      logging.info('Storing registration codes.')
      # See <http://src.chromium.org/svn/trunk/src/chrome/
      # browser/chromeos/extensions/echo_private_api.cc>.
      data = {'ubind_attribute': self.test.registration_code_map['user'],
              'gbind_attribute': self.test.registration_code_map['group']}
      self.test.dut.vpd.rw.Update(data)
    self.Pass()


class ShopFloorVPDTask(factory_task.FactoryTask):
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

  def __init__(self, region, key, label, value_check):
    if region not in ['ro', 'rw']:
      raise ValueError("VPD region must be either 'ro' or 'rw'.")
    self.region = region
    if not isinstance(key, str):
      raise TypeError('VPD id must be a string.')
    self.key = key
    self.label = label
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
    else:  # value_check is None
      self.value_check = value_check


class ManualInputTask(factory_task.FactoryTask):
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
        self.test.ui.SetHTML(_ERR_INPUT_INVALID(self.vpd_info.label),
                             id='errormsg')
        self.test.ui.SetSelected(self.vpd_info.key)
        return
      self.OnComplete(vpd_value)

  def OnESCPressed(self):
    vpd_value = self.test.dut.vpd.GetPartition(
        self.vpd_info.region).get(self.vpd_info.key).strip()
    if not vpd_value:
      self.test.ui.SetHTML(_ERR_NO_VALID_VPD(self.vpd_info.label),
                           id='errormsg')
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
    self.test.template.SetState(_MSG_MANUAL_SELECT_PROMPT(self.vpd_info.label))
    select_box = ui_templates.SelectBox(self.vpd_info.key, _SELECTION_PER_PAGE,
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
    self.test.template.SetState(_MSG_MANUAL_INPUT_PROMPT(self.vpd_info.label))
    self._AppendState(_HTML_MANUAL_INPUT(self.vpd_info.key))
    self._AppendState(_MSG_ESC_TO_SKIP(self.vpd_info.label))
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_MANUAL_INPUT(
        self.vpd_info.key, vpd_event_subtype))
    self.test.ui.AddEventHandler(vpd_event_subtype, self.OnEnterPressed)
    self.test.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnESCPressed())
    self.test.ui.SetFocus(self.vpd_info.key)

  def Cleanup(self):
    self.test.ui.UnbindKey(test_ui.ENTER_KEY)
    self.test.ui.UnbindKey(test_ui.ESCAPE_KEY)


class SelectRegionTask(factory_task.FactoryTask):
  """Factory task to select region info (locale, keyboard layout, timezone).

  Args:
    vpd_test: The main VPD TestCase object.
  """

  def __init__(self, vpd_test):
    super(SelectRegionTask, self).__init__()
    self.region_list = sorted(regions.REGIONS)
    self.test = vpd_test

  def SaveVPD(self, event):
    index = int(event.data)
    region = regions.REGIONS[self.region_list[index]]
    self.test.vpd['ro']['region'] = region.region_code
    self.Pass()

  def RenderPage(self):
    def short_label(value, limit=16):
      text = '%s' % (','.join(value) if type(value) is list else value)
      if len(text) >= limit:
        text = text[:limit] + '...'
      return text

    self.test.template.SetState(_MSG_SELECT_REGION)
    select_box = ui_templates.SelectBox(
        _REGION_SELECT_BOX_ID, _SELECTION_PER_PAGE, _SELECT_BOX_STYLE)
    for index, region in enumerate(self.region_list):
      region = regions.REGIONS[region]
      select_box.InsertOption(index, '%s - [%s], [%s], [%s], [%s]' % (
          short_label(region.description),
          region.region_code,
          short_label(region.language_codes),
          short_label(region.keyboards),
          short_label(region.time_zone)))
    select_box.SetSelectedIndex(0)
    self.test.template.SetState(select_box.GenerateHTML(), append=True)
    self.test.template.SetState(_MSG_HOW_TO_SELECT, append=True)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_SELECT_BOX(
        _REGION_SELECT_BOX_ID, _EVENT_SUBTYPE_SELECT_REGION))
    self.test.ui.AddEventHandler(_EVENT_SUBTYPE_SELECT_REGION, self.SaveVPD)
    self.test.ui.SetFocus(_REGION_SELECT_BOX_ID)

  def Run(self):
    self.RenderPage()


class SelectBrandingTask(factory_task.FactoryTask):
  """Factory task to select the value for a branding field.

  Args:
    vpd_test: The main VPD TestCase object.
    key: the key of the branding field in RO VPD. Currently it is either
        'rlz_brand_code' or 'customization_id'.
    desc_value_dict: a dict of the format: {'description': 'value'}.
        Description is a helpful string and key=value will be written into
        RO VPD after selection.
    regexp: regular expression of the value.
  """

  def __init__(self, vpd_test, key, desc_value_dict, regexp):
    super(SelectBrandingTask, self).__init__()
    self.branding_list = sorted(desc_value_dict)
    self.test = vpd_test
    self.key = key
    self.desc_value_dict = desc_value_dict
    self.regexp = regexp

  def SaveVPD(self, event):
    index = int(event.data)
    desc = self.branding_list[index]
    value = self.desc_value_dict[desc]
    # Check the format.
    if not self.regexp.match(value):
      self.test.template.SetState(
          _ERR_INPUT_INVALID(i18n.NoTranslation(self.key)))
      self.Fail('Bad format for %s %r (expected it to match regexp %r)' % (
          self.key, value, self.regexp.pattern))
    else:
      self.test.vpd['ro'][self.key] = value
      self.Pass()

  def RenderPage(self):
    vpd_event_subtype = _EVENT_SUBTYPE_VPD_PREFIX + self.key
    self.test.template.SetState(
        _MSG_MANUAL_SELECT_PROMPT(i18n.NoTranslation(self.key)))
    select_box = ui_templates.SelectBox(
        self.key, _SELECTION_PER_PAGE, _SELECT_BOX_STYLE)
    for index, description in enumerate(self.branding_list):
      select_box.InsertOption(index, '%s: %s' % (
          description, self.desc_value_dict[description]))
    select_box.SetSelectedIndex(0)
    self.test.template.SetState(select_box.GenerateHTML(), append=True)
    self.test.template.SetState(_MSG_HOW_TO_SELECT, append=True)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_SELECT_BOX(
        self.key, vpd_event_subtype))
    self.test.ui.AddEventHandler(vpd_event_subtype, self.SaveVPD)
    self.test.ui.SetFocus(self.key)

  def Run(self):
    self.RenderPage()


class VPDTest(unittest.TestCase):
  VPDTasks = type_utils.Enum(['serial', 'region'])

  ARGS = [
      Arg('override_vpd', dict,
          'A dict of override VPDs. This is for development purpose and is '
          'useable only in engineering mode. The dict should be of the format: '
          '{"ro": { RO_VPD key-value pairs }, "rw": { RW_VPD key-value pairs '
          '}}',
          default=None, optional=True),
      Arg('override_vpd_entries', dict,
          'A dict of override VPD entries. Unlike override_vpd, it only '
          'overrides some key-value pairs instead of the whole VPD section.'
          'It does not require engineering mode. The dict should be of the '
          'format: {"ro": { RO_VPD key-value pairs }, "rw": { RW_VPD key-value '
          'pairs }}', default=None, optional=True),
      Arg('override_registration_codes_device', str,
          'A string to override the device in registration codes. If None, '
          'use the board name in /etc/lsb-release.',
          default=None, optional=True),
      Arg('store_registration_codes', bool,
          'Whether to store registration codes onto the machine.',
          default=False),
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
          'only applies if use_shopfloor_device_data is True.', default=[]),
      Arg('manual_input_fields', list,
          'A list of tuples (vpd_region, key, display_name, VALUE_CHECK) or '
          '(vpd_region, key, en_display_name, zh_display_name, VALUE_CHECK) '
          'indicating the VPD fields that need to be manually entered.\n'
          'VALUE_CHECK can be a list of strings, a regexp string, or None. '
          'If VALUE_CHECK is None or a regexp string then a text input box '
          'will show up to let user input value. The entered value will be '
          'validated if VALUE_CHECK is a regexp string. Otherwise a select box '
          'containing all the possible values will be used to let user select '
          'a value from it.',
          default=[], optional=True),
      Arg('rlz_brand_code', (str, dict),
          'RLZ brand code to write to RO VPD.  This may be any of:\n'
          '\n'
          '- A fixed string\n'
          '- None, to not set any value at all\n'
          '- The string `"FROM_DEVICE_DATA"`, to use a value obtained from\n'
          '  device data.\n'
          '- A dict of possible values to select. This is used for a shared\n'
          '  RMA shim for multiple local OEM partners. The dict should be\n'
          '  of the format: {"LOEM1 description": "LOEM1_brand_code",\n'
          '  "LOEM2_description": "LOEM2_brand_code"}. The description is a\n'
          '  helpful string and only the brand_code will be written into VPD.',
          default=None, optional=True),
      Arg('customization_id', (str, dict),
          'Customization ID to write to RO VPD.  This may be any of:\n'
          '\n'
          '- A fixed string\n'
          '- None, to not set any value at all\n'
          '- The string `"FROM_DEVICE_DATA"`, to use a value obtained from\n'
          '  device data.\n'
          '- A dict of possible values to select. This is used for a shared\n'
          '  RMA shim for multiple local OEM partners. The dict should be\n'
          '  of the format: {"LOEM1 description": "LOEM1_customization_id",\n'
          '  "LOEM2_description": "LOEM2_customization_id"}. The description\n'
          '  is a helpful string and only the customization_id will be\n'
          '  written into VPD.', default=None, optional=True)]

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

    region = regions.REGIONS[device_data['region']]
    self.vpd['ro']['region'] = region.region_code

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
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_DEFAULT_VPD_TEST_CSS)
    self.tasks = []
    self.registration_code_map = {}
    self.vpd = {'ro': {}, 'rw': {}}
    self.dut = device_utils.CreateDUTInterface()
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
      manual_input_fields = []
      for v in self.args.manual_input_fields:
        if len(v) == 5:
          # TODO(pihsun): This is to maintain backward compatibility. Should be
          #               removed after test lists are migrated to new format.
          v = (v[0], v[1], {'en-US': v[2], 'zh-CN': v[3]}, v[4])
        v = (v[0], v[1], i18n.Translated(v[2], translate=False), v[3])
        manual_input_fields.append(v)
      if shopfloor.is_enabled():
        # Grab from ShopFloor, then input manual fields (if any).
        if self.args.use_shopfloor_device_data:
          self._ReadShopFloorDeviceData()
        else:
          self.tasks += [ShopFloorVPDTask(self)]
        for v in manual_input_fields:
          self.tasks += [ManualInputTask(self, VPDInfo(*v))]
      else:
        if self.VPDTasks.serial in self.args.task_list:
          manual_input_fields.insert(
              0, ('ro', 'serial_number', _('Serial Number'), None))
        for v in manual_input_fields:
          self.tasks += [ManualInputTask(self, VPDInfo(*v))]
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
      elif isinstance(arg_value, dict):
        # Manually select the branding field.
        self.tasks += [SelectBrandingTask(self, attr, arg_value, regexp)]
        continue
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
    factory_task.FactoryTaskManager(self.ui, self.tasks).Run()
