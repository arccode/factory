# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Prompts operator to select components, and updates device_data."""


import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import string_utils

_MESSAGE_SELECT = i18n_test_ui.MakeI18nLabelWithClass('Select Components:',
                                                      'msg-font-size')

_TEST_DEFAULT_CSS = '.msg-font-size {font-size: 2em;}'
_SELECT_BOX_STYLE = ('font-size: 1.5em; background-color: white; '
                     'min-width: 150px;')

_SELECT_BOX_ID = lambda x: 'Select-' + x
_SELECTION_PER_PAGE = 10
_EVENT_SUBTYPE_SELECT_COMP = 'Select-Components'

_TEST_TITLE = i18n_test_ui.MakeI18nLabel('Select Components')


class SelectComponentTest(unittest.TestCase):
  """The main class for this pytest."""
  ARGS = [
      Arg('comps', dict,
          ('A dict from components to (device_data_field, choices). If '
           'component\ncan be found in hwid database, the default choices will'
           ' be available\ncomponents in hwid database. If choices is not '
           'None, user selects\nvalue from choices. That value will be stored '
           'as device_data_field\nin device_data. E.g.::\n\n  comps={\n    '
           '"comp_a": ("component.comp_a", ["choice_a1", "choice_a2"]),\n    '
           '"comp_b": ("component.comp_b", None),\n    "comp_c": '
           '("component.comp_c", ["choice_c1", "choice_c2"]),\n    }\n\nwhere '
           'comp_a is in hwid database, but we set the available '
           'choices.\ncomp_b is in hwid database, and we use the choices in '
           'database.\ncomp_c is not in hwid database, so we provide the '
           'choices.\n'),
          optional=False),
  ]

  def setUp(self):
    self.ui = test_ui.UI()
    self.template = ui_templates.OneSection(self.ui)
    self.ui.AppendCSS(_TEST_DEFAULT_CSS)
    self.template.SetTitle(_TEST_TITLE)
    self.device_data = shopfloor.GetDeviceData()
    # The component names.
    self.fields = self.args.comps.keys()
    self.component_device_data = dict((k, self.args.comps[k][0])
                                      for k in self.fields)
    self.component_choices = dict((k, self.args.comps[k][1])
                                  for k in self.fields)

  def SelectComponent(self, event):
    """Handle component selection RPC call from Javascript.

    The passed in 'event' is a list of tuples, containing selected component
    for each field. For example,
      [(0, 'inpaq'), (1, 'gce'), (2, 'us_darfon')]
    The first item of each tuple is the index of the field as specified in
    the test argument. The second item is the selected component.
    """
    logging.info('Component selection: %r', event.data)
    for comp in event.data:
      key_name = self.component_device_data[self.fields[comp[0]]]
      value = string_utils.ParseString(comp[1])
      self.device_data[key_name] = value
      factory.console.info('Update device data %r: %r', key_name, value)
    shopfloor.UpdateDeviceData(self.device_data)

  def runTest(self):
    table = ui_templates.Table(element_id=None, rows=2, cols=len(self.fields))
    db = database.Database.Load()
    fields_in_db = [x for x in self.fields
                    if x in db.components.GetRequiredComponents()]
    logging.info('Fields in database are %r', fields_in_db)
    # Checks those fields not in hwid database have choices from test list.
    for field in set(self.fields) - set(fields_in_db):
      self.assertTrue(self.component_choices[field],
                      'Field %r is not in hwid database, user should provide'
                      ' choices' % field)
    comp_values = hwid_utils.ListComponents(db, fields_in_db)
    # Updates comp_values with choices from test list.
    comp_values.update(dict(
        (field, self.component_choices[field])
        for field in self.fields
        if self.component_choices[field]))

    for field_index, field in enumerate(self.fields):
      self.ui.RunJS('addComponentField("%s");' % field)

      table.SetContent(0, field_index, field)
      select_box = ui_templates.SelectBox(
          _SELECT_BOX_ID(field), _SELECTION_PER_PAGE, _SELECT_BOX_STYLE)
      selected = None
      for index, comp_value in enumerate(comp_values[field]):
        select_box.InsertOption(comp_value, comp_value)
        # Let user choose component even if device data field is not present
        # in device_data.
        if comp_value == self.device_data.get(
            self.component_device_data[field], None):
          selected = index
      if selected is not None:
        select_box.SetSelectedIndex(selected)
      table.SetContent(1, field_index, select_box.GenerateHTML())
    html = [_MESSAGE_SELECT, '<center>', table.GenerateHTML(), '</center>']

    self.ui.AddEventHandler(_EVENT_SUBTYPE_SELECT_COMP, self.SelectComponent)

    html.append('<input type="button" value="OK" '
                'onClick="SelectComponents();"/>')
    self.ui.BindKeyJS(13, 'SelectComponents();')

    self.template.SetState(''.join(html))
    self.ui.Run()
    return
