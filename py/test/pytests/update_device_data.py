# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Manually updates device data (or by predefined input from test list).

This test can determine device data information (usually for VPD) without using
shopfloor backend, usually including::

 - 'serials.serial_number': The device serial number.
 - 'vpd.ro.region': Region data (RO region).
 - 'vpd.rw.ubind_attribute' and 'vpd.rw.gbind_attribute': User and group
   registration codes.
 - Or other values specified in args.manual_input_fields.

If you want to set device data, especially VPD values, using shopfloor or
pre-defined values::

 1. Use shopfloor_service method=GetDeviceInfo to retrieve vpd.{ro,rw}.*
 2. Use update_device_data to write pre-defined values to vpd.{ro,rw}.*
 3. Use write_device_data_to_vpd to flush data into firmware VPD sections.
"""


from __future__ import print_function

import re
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import device_data
from cros.factory.test import factory_task
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.l10n import regions
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg


# Known regions to be listed first.
_KNOWN_REGIONS = (
    'us', 'gb', 'de', 'fr', 'ch', 'nordic', 'latam-es-419',
)

_KNOWN_KEY_LABELS = {
    device_data.KEY_SERIAL_NUMBER: _('Device Serial Number'),
    device_data.KEY_MLB_SERIAL_NUMBER: _('Mainboard Serial Number'),
    device_data.KEY_VPD_REGION: _('VPD Region Code'),
    device_data.KEY_VPD_USER_REGCODE: _('User Registration Code'),
    device_data.KEY_VPD_GROUP_REGCODE: _('Group Registration Code'),
}

# UI elements
_DEFAULT_TEST_CSS = '.value-field {font-size: 2em;}'
_ERR_INPUT_INVALID = lambda label: i18n_test_ui.MakeI18nLabelWithClass(
    'Invalid value for {label}.', 'value-field test-error', label=label)
_ERR_NO_VALID_DATA = lambda label: i18n_test_ui.MakeI18nLabelWithClass(
    'No valid data on machine for {label}.', 'value-field test-error',
    label=label)
_MSG_HOW_TO_SELECT = i18n_test_ui.MakeI18nLabelWithClass(
    '<br>Select with ENTER', 'value-field')
_MSG_MANUAL_INPUT_PROMPT = lambda label: (
    i18n_test_ui.MakeI18nLabelWithClass(
        'Enter {label}: ', 'value-field', label=label))
_MSG_MANUAL_SELECT_PROMPT = lambda label: (
    i18n_test_ui.MakeI18nLabelWithClass(
        'Select {label}: <br>', 'value-field', label=label))
# The "ESC" is available primarily for RMA and testing process, when operator
# does not want to change existing serial number.
_MSG_ESC_TO_SKIP = i18n_test_ui.MakeI18nLabelWithClass(
    '<br>(ESC to keep current value)', 'value-field')

_HTML_MANUAL_INPUT = lambda ele_id, value: """
    <input type="text" id="%s" value="%s" style="width: 20em; font-size: 2em;"/>
    <div id="errormsg" class="value-field test-error"></div>
""" % (ele_id, value)
_EVENT_SUBTYPE_DEVICEDATA_PREFIX = 'devicedata-'
_JS_MANUAL_INPUT = lambda ele_id, event_subtype: """
    ele = document.getElementById("%s");
    window.test.sendTestEvent("%s", ele.value);
""" % (ele_id, event_subtype)

_SELECT_BOX_STYLE = 'font-size: 1.5em; background-color: white;'
_SELECTION_PER_PAGE = 10
_JS_SELECT_BOX = lambda ele_id, event_subtype: """
    ele = document.getElementById("%s");
    idx = ele.selectedIndex;
    window.test.sendTestEvent("%s", ele.options[idx].value);
""" % (ele_id, event_subtype)


class DataEntry(object):
  """Quick access to an entry in DeviceData."""

  def __init__(self, key, value=None, display_name=None, value_check=None):
    device_data.CheckValidDeviceDataKey(key)
    self.value = device_data.GetDeviceData(key, value)
    if display_name is None and key in _KNOWN_KEY_LABELS:
      display_name = _KNOWN_KEY_LABELS[key]

    self.display_name = display_name
    self.label = (i18n.StringFormat('{name} ({key})', name=display_name,
                                    key=key) if display_name else key)
    self.re_chcker = None
    self.value_check = None

    if isinstance(value_check, basestring):
      self.re_chcker = re.compile(value_check)
    elif isinstance(value_check, (list, tuple)):
      self.value_check = value_check
    elif value_check is not None:
      raise TypeError('value_check (%r) for %s must be either None, '
                      'list of strings, or regex.' % (value_check, key))
    elif key == device_data.KEY_VPD_REGION:
      self.value_check = regions.REGIONS.keys()
    else:
      self.value_check = value_check

    # Re-order value_check for regions.
    if key == device_data.KEY_VPD_REGION:
      ordered_values = [v for v in _KNOWN_REGIONS if v in self.value_check]
      other_values = list(set(self.value_check) - set(ordered_values))
      other_values.sort()
      self.value_check = ordered_values + other_values

  def IsValidValue(self, value):
    if self.re_chcker:
      return self.re_chcker.match(value)
    if self.value_check is None:
      return True
    return value in self.value_check


class InputTask(factory_task.FactoryTask):
  """Factory task to let user manually enter value for the given data.

  Args:
    test: The main TestCase object.
    entry: A DataEntry object.
  """

  def __init__(self, test, entry):
    super(InputTask, self).__init__()
    self.test = test
    self.entry = entry

  def OnComplete(self, value):
    if value is not None:
      device_data.UpdateDeviceData({self.entry.key: value})
    self.Pass()

  def OnEnterPressed(self, event):
    value = event.data
    if not self.entry.IsValidValue(value):
      self.test.ui.SetHTML(_ERR_INPUT_INVALID(self.entry.label), id='errormsg')
      self.test.ui.SetSelected(self.entry.key)
      return
    self.OnComplete(value)

  def OnESCPressed(self):
    if self.entry.value is None:
      self.test.ui.SetHTML(_ERR_NO_VALID_DATA(self.entry.label), id='errormsg')
    else:
      self.OnComplete(None)

  def Run(self):
    if isinstance(self.entry.value_check, (list, tuple)):
      # Renders a select box to list all the possible values.
      self.RenderSelectBox()
    else:
      self.RenderInputBox()

  def _AppendState(self, html):
    self.test.template.SetState(html, append=True)

  def RenderSelectBox(self):
    event_subtype = _EVENT_SUBTYPE_DEVICEDATA_PREFIX + self.entry.key
    self.test.template.SetState(_MSG_MANUAL_SELECT_PROMPT(self.entry.label))
    select_box = ui_templates.SelectBox(self.entry.key, _SELECTION_PER_PAGE,
                                        _SELECT_BOX_STYLE)
    # Special hack for region.
    if self.entry.key == device_data.KEY_VPD_REGION:
      for index, value in enumerate(self.entry.value_check):
        select_box.InsertOption(
            value, '%s - %s; %s' % (
                index, value, regions.REGIONS[value].description))
    else:
      for index, value in enumerate(self.entry.value_check):
        select_box.InsertOption(value, '%s - %s' % (index, value))
    index = self.entry.value_check.index(self.entry.value)
    select_box.SetSelectedIndex(index if index >= 0 else 0)
    self._AppendState(select_box.GenerateHTML())
    self._AppendState(_MSG_HOW_TO_SELECT)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_SELECT_BOX(
        self.entry.key, event_subtype))
    self.test.ui.AddEventHandler(event_subtype, self.OnEnterPressed)
    self.test.ui.SetFocus(self.entry.key)

  def RenderInputBox(self):
    event_subtype = _EVENT_SUBTYPE_DEVICEDATA_PREFIX + self.entry.key
    self.test.template.SetState(_MSG_MANUAL_INPUT_PROMPT(self.entry.label))
    self._AppendState(_HTML_MANUAL_INPUT(
        self.entry.key, self.entry.value or ''))
    if self.entry.value:
      self._AppendState(_MSG_ESC_TO_SKIP)
    self.test.ui.BindKeyJS(test_ui.ENTER_KEY, _JS_MANUAL_INPUT(
        self.entry.key, event_subtype))
    self.test.ui.AddEventHandler(event_subtype, self.OnEnterPressed)
    self.test.ui.BindKey(test_ui.ESCAPE_KEY, lambda _: self.OnESCPressed())
    self.test.ui.SetSelected(self.entry.key)
    self.test.ui.SetFocus(self.entry.key)

  def Cleanup(self):
    self.test.ui.UnbindKey(test_ui.ENTER_KEY)
    self.test.ui.UnbindKey(test_ui.ESCAPE_KEY)


class UpdateDeviceData(unittest.TestCase):
  ARGS = [
      Arg('manual_input', bool,
          'Set to False to silently updating all values. Otherwise each value '
          'will be prompted before set into Device Data.',
          default=True, optional=True),
      Arg('fields', (list, tuple),
          'A list of tuples in (data_key, value, display_name, value_check) '
          'indicating the Device Data field by data_key must be updated to '
          'specified value.\n'
          'value_check can be a list of strings, a regexp string, or None. ')]

  def setUp(self):
    self.ui = None
    # Syntax sugar: If the tuple was replaced by a simple string, consider that
    # as data_key only.
    entries = [DataEntry(args) if isinstance(args, basestring) else
               DataEntry(*args) for args in self.args.fields]
    if not self.args.manual_input:
      self.entries = entries
      return

    # Setup UI and update accordingly.
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_DEFAULT_TEST_CSS)
    self.tasks = [InputTask(self, entry) for entry in entries]

  def runTest(self):
    if self.args.manual_input:
      factory_task.FactoryTaskManager(self.ui, self.tasks).Run()
    else:
      results = dict((entry.key, entry.value) for entry in self.entries)
      device_data.UpdateDeviceData(results)
