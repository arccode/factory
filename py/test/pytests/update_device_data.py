# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Updates Device Data (manually or from predefined values in test list).

Description
-----------
The Device Data (``cros.factory.test.device_data``) is a special data structure
for manipulating DUT information.  This test can determine Device Data
information (usually for VPD) without using shopfloor backend, usually
including:

- ``serials.serial_number``: The device serial number.
- ``vpd.ro.region``: Region data (RO region).
- ``vpd.rw.ubind_attribute`` and ``vpd.rw.gbind_attribute``: User and group
  registration codes.
- Or other values specified in argument ``fields`` or ``config_name``.

When argument `manual_input` is True, every values specified in ``fields`` will
be displayed on screen with an edit box before written into device data.
Note all the values will be written as string in manual mode.

The ``fields`` argument is a sequence in format
``(data_key, value, display_name, value_check)``:

================ ==============================================================
Name             Description
================ ==============================================================
``data_key``     The Device Data key name to write.
``value``        The value to be written, can be modified if ``manual_input`` is
                 True.
``display_name`` The label or name to be displayed on UI.
``value_check``  To validate the input value. Can be a regular expression,
                 list of strings, list of integers, boolean values, or
                 None.
                 When ``value_check`` is a list of strings / integers / bool, an
                 "option label" can be added to each option.  So ``value_check``
                 becomes a list of tuples: ``[ (string, string) ]`` or ``[ (int,
                 string) ]`` or ``[ (bool, string) ]``.  The first element of
                 tuple is the value, and the second element is a string to be
                 displayed.
================ ==============================================================

If you want to manually configure without default values, the sequence can be
replaced by a simple string of key name.

The ``config_name`` refers to a JSON config file loaded by
``cros.factory.py.utils.config_utils`` with single dictionary that the keys
and values will be directly sent to Device Data. This is helpful if you need to
define board-specific data.

``config_name`` and ``fields`` are both optional, but you must specify at least
one.

If you want to set device data (especially VPD values) using shopfloor or
pre-defined values:

1. Use ``shopfloor_service`` test with method=GetDeviceInfo to retrieve
   ``vpd.{ro,rw}.*``.
2. Use ``update_device_data`` test to write pre-defined or update values to
   ``vpd.{ro,rw}.*``.
3. Use ``write_device_data_to_vpd`` to flush data into firmware VPD sections.

Test Procedure
--------------
If argument ``manual_input`` is not True, this will be an automated test
without user interaction.

If argument ``manual_input`` is True, the test will go through all the fields:

1. Display the name and key of the value.
2. Display an input edit box for simple values, or a list of selection
   if the ``value_check`` is a sequence of strings or boolean values.
3. Wait for operator to select or input right value.
4. If operator presses ESC, abandon changes and keep original value.
5. If operator clicks Enter, validate the input by ``value_check`` argument.
   If failed, prompt and go back to 3.
   Otherwise, write into device data and move to next field.
6. Pass when all fields were processed.

Dependency
----------
None. This test only deals with the ``device_data`` module inside factory
software framework.

Examples
--------
To silently load device-specific data defined in board overlay
``py/config/default_device_data.json``, add this in test list::

  {
    "pytest_name": "update_device_data",
    "args": {
      "config_name": "default",
      "manual_input": false
    }
  }

To silently set a device data 'component.has_touchscreen' to True::

  {
    "pytest_name": "update_device_data",
    "args": {
      "fields": [
        [
          "component.has_touchscreen",
          true,
          "Device has touch screen",
          null
        ]
      ],
      "manual_input": false
    }
  }

For RMA process to set serial number, region, registration codes, and specify
if the device has peripherals like touchscreen::

  {
    "pytest_name": "update_device_data",
    "args": {
      "fields": [
        [
          "serials.serial_number",
          null,
          "Device Serial Number",
          "[A-Z0-9]+"
        ],
        ["vpd.ro.region", "us", "Region", null],
        ["vpd.rw.ubind_attribute", null, "User ECHO", null],
        ["vpd.rw.gbind_attribute", null, "Group ECHO", null],
        [
          "component.has_touchscreen",
          null,
          "Has touchscreen",
          [true, false]
        ]
      ]
    }
  }

If you don't need default values, there's an alternative to list only key
names::

  {
    "pytest_name": "update_device_data",
    "args": {
      "fields": [
        "serials.serial_number",
        "vpd.ro.region",
        "vpd.rw.ubind_attribute",
        "vpd.rw.gbind_attribute"
      ]
    }
  }
"""

import logging
import queue
import re

from cros.factory.test import device_data
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.l10n import regions
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sync_utils


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

_SELECTION_PER_PAGE = 10


class DataEntry:
  """Quick access to an entry in DeviceData.

  Properties:
    key: A string as Device Data key.
    value: Default value to be set.
    label: A I18N label to display on UI.
    value_check: A regular expression string or list of values or None for
      validation of new value.
    re_checker: The compiled regular expression to validate input value.
    codes: A list of string for UI to use as reference to selected values.
    options: A list of strings for UI to display as option to select from.
  """

  def __init__(self, key, value=None, display_name=None, value_check=None):
    device_data.CheckValidDeviceDataKey(key)
    self.key = key
    self.value = device_data.GetDeviceData(key) if value is None else value
    if display_name is None and key in _KNOWN_KEY_LABELS:
      display_name = _KNOWN_KEY_LABELS[key]
    self.label = (i18n.StringFormat('{name} ({key})', name=display_name,
                                    key=key) if display_name else key)

    self.re_checker = None
    self.value_check = None
    self.codes = None
    self.options = None

    if isinstance(value, bool) and value_check is None:
      value_check = [True, False]

    if isinstance(value_check, str):
      self.re_checker = re.compile(value_check)
    elif value_check is None:
      self.value_check = value_check
    else:
      raise TypeError('value_check (%r) for %s must be either regex, sequence, '
                      'or None.' % (value_check, key))

    # Region should be processed differently.
    if key == device_data.KEY_VPD_REGION:
      all_regions = list(regions.REGIONS)
      if not value_check:
        ordered_values = [v for v in _KNOWN_REGIONS if v in all_regions]
        other_values = sorted(set(all_regions) - set(ordered_values))
        value_check = ordered_values + other_values

      if not isinstance(value_check, list):
        raise ValueError(f'`value_check` for {key} must be a list of strings')
      if not set(value_check).issubset(set(all_regions)):
        raise ValueError(f'`value_check` for {key} must be '
                         'a subset of known regions')
      self.value_check = value_check
      self.codes = value_check
      self.options = [
          '%d - %s; %s' % (i + 1, v, regions.REGIONS[v].description)
          for i, v in enumerate(self.codes)]
      return

    # When value_check is a list, UI will render a list of options.
    if isinstance(value_check, list):
      value_check = self._NormalizeListValueCheck(value_check)
      self.value_check = []
      self.codes = []
      self.options = []

      for v, option in value_check:
        self.value_check.append(v)
        self.codes.append(str(v))
        self.options.append(option)

  @staticmethod
  def _NormalizeListValueCheck(value_check):
    """Normalize `value_check` to list of (value, option) tuples."""
    assert isinstance(value_check, list)

    for i, e in enumerate(value_check):
      if isinstance(e, (str, int, bool)):
        value_check[i] = (e, f'{i + 1} - {e}')
        continue
      if isinstance(e, list):
        if len(e) == 0:
          raise ValueError(
              'Each element of `value_check` must not be an empty list')
        if len(e) == 1:
          e = e[0]
          value_check[i] = (e, f'{i + 1} - {e}')
        elif len(e) == 2:
          value_check[i] = (e[0], f'{i + 1} - {e[1]}')
        else:
          logging.warning('Each element of value_check is either a single '
                          'value or a two value tuple. Extra values will be '
                          'truncated.')
          value_check[i] = (e[0], f'{i + 1} - {e[1]}')
    return value_check

  def GetInputList(self):
    """Returns the list of allowed input, or None for raw input."""
    return self.codes

  def GetOptionList(self):
    """Returns the options to display if the allowed input is a list."""
    return self.options

  def GetValueIndex(self):
    """Returns the index of current value in input list.

    Raises:
      ValueError if current value is not in known list.
    """
    return self.value_check.index(self.value)

  def IsValidInput(self, input_data):
    """Checks if input data is valid.

    The input data may be a real string or one of the value in self.codes.
    """
    if self.re_checker:
      logging.info('trying re_checker')
      return self.re_checker.match(input_data)
    if self.value_check is None:
      return True
    if self.codes:
      return input_data in self.codes
    raise ValueError('Unknown value_check: %r' % self.value_check)

  def GetValue(self, input_data):
    """Returns the real value from input data."""
    if self.codes:
      return self.value_check[self.codes.index(input_data)]
    return input_data


class UpdateDeviceData(test_case.TestCase):
  ARGS = [
      Arg('manual_input', bool,
          'Set to False to silently updating all values. Otherwise each value '
          'will be prompted before set into Device Data.',
          default=True),
      Arg('config_name', str,
          'A JSON config name to load representing the device data to update.',
          default=None),
      Arg('fields', list,
          ('A list of [data_key, value, display_name, value_check] '
           'indicating the Device Data field by data_key must be updated to '
           'specified value.'),
          default=None),
  ]

  def setUp(self):
    # Either config_name or fields must be specified.
    if self.args.config_name is None and self.args.fields is None:
      raise ValueError('Either config_name or fields must be specified.')

    fields = []

    if self.args.config_name:
      fields += [(k, v, None, None) for k, v in
                 device_data.LoadConfig(self.args.config_name).items()]

    if self.args.fields:
      fields += self.args.fields

    # Syntax sugar: If the sequence was replaced by a simple string, consider
    # that as data_key only.
    self.entries = [
        DataEntry(args) if isinstance(args, str) else DataEntry(*args)
        for args in fields
    ]

    # Setup UI and update accordingly.
    self.ui.ToggleTemplateClass('font-large', True)

  def runTest(self):
    if self.args.manual_input:
      for entry in self.entries:
        self.ManualInput(entry)
    else:
      results = {entry.key: entry.value for entry in self.entries}
      device_data.UpdateDeviceData(results)

  def ManualInput(self, entry):
    event_subtype = 'devicedata-' + entry.key
    event_queue = queue.Queue()

    if entry.GetInputList():
      self._RenderSelectBox(entry)
      self.ui.BindKeyJS(test_ui.ENTER_KEY, 'window.sendSelectValue(%r, %r)' %
                        (entry.key, event_subtype))
    else:
      self._RenderInputBox(entry)
      self.ui.BindKey(
          test_ui.ESCAPE_KEY, lambda unused_event: event_queue.put(None))
      self.ui.BindKeyJS(test_ui.ENTER_KEY, 'window.sendInputValue(%r, %r)' % (
          entry.key, event_subtype))

    self.event_loop.AddEventHandler(event_subtype, event_queue.put)

    while True:
      event = sync_utils.QueueGet(event_queue)
      if event is None:
        # ESC pressed.
        if entry.value is not None:
          break
        self._SetErrorMsg(
            _('No valid data on machine for {label}.', label=entry.label))
      else:
        data = event.data
        if entry.IsValidInput(data):
          value = entry.GetValue(data)
          if value is not None:
            device_data.UpdateDeviceData({entry.key: value})
          break
        self._SetErrorMsg(_('Invalid value for {label}.', label=entry.label))

    self.ui.UnbindAllKeys()
    self.event_loop.ClearHandlers()

  def _SetErrorMsg(self, msg):
    self.ui.SetHTML(
        ['<span class="test-error">', msg, '</span>'], id='errormsg')

  def _RenderSelectBox(self, entry):
    # Renders a select box to list all the possible values.
    select_box = ui_templates.SelectBox(entry.key, _SELECTION_PER_PAGE)
    for value, option in zip(entry.GetInputList(),
                             entry.GetOptionList()):
      select_box.AppendOption(value, option)

    try:
      select_box.SetSelectedIndex(entry.GetValueIndex())
    except ValueError:
      pass

    html = [
        _('Select {label}:', label=entry.label),
        select_box.GenerateHTML(),
        _('Select with ENTER')
    ]

    self.ui.SetState(html)
    self.ui.SetFocus(entry.key)

  def _RenderInputBox(self, entry):
    html = [
        _('Enter {label}: ', label=entry.label),
        '<input type="text" id="%s" value="%s" style="width: 20em;">'
        '<div id="errormsg" class="test-error"></div>' % (entry.key,
                                                          entry.value or '')
    ]

    if entry.value:
      # The "ESC" is available primarily for RMA and testing process, when
      # operator does not want to change existing serial number.
      html.append(_('(ESC to keep current value)'))

    self.ui.SetState(html)
    self.ui.SetSelected(entry.key)
    self.ui.SetFocus(entry.key)
