# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest


import factory_common  # pylint: disable=unused-import
from cros.factory.test import event_log
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.i18n import arg_utils as i18n_arg_utils
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import debug_utils


class SelectAuxField(unittest.TestCase):
  """Display choices for user to select.

  Choices are displayed as radio buttons and the selected value is stored in
  shopfloor aux_data with the specified aux table name, id, and col name.
  """

  ARGS = i18n_arg_utils.BackwardCompatibleI18nArgs(
      'label', 'Name of the model being selected'
  ) + [
      Arg('event_log_key', str, 'Key to use for event log', optional=True),
      Arg('aux_table_name', str, 'Name of the auxiliary table'),
      Arg('aux_id', str, 'Name of the auxiliary ID'),
      Arg('col_name', str, 'Column name to store the selected value'),
      Arg('choices', dict,
          'Dictionary consists of pairs of choice label and value to be '
          'stored.')]

  def HandleSelectValue(self, event):
    def SetError(label):
      logging.info('Select error: %r', label['en-US'])
      self.ui.SetHTML(i18n_test_ui.MakeI18nLabel(label), id='select-error')

    select_value = event.data.strip()
    logging.debug('Selected value: %s', select_value)
    if not select_value:
      return SetError(_('No selection.'))

    try:
      shopfloor.save_aux_data(
          self.args.aux_table_name, self.args.aux_id,
          {self.args.col_name: self.args.choices.get(select_value)})
    except:  # pylint: disable=bare-except
      logging.exception('save_aux_data failed')
      return SetError(i18n.NoTranslation(debug_utils.FormatExceptionOnly()))

    if self.args.event_log_key:
      event_log.Log('select', key=self.args.event_log_key, value=select_value)

    self.ui.Pass()

  def setUp(self):
    i18n_arg_utils.ParseArg(self, 'label')
    self.ui = test_ui.UI()

  def runTest(self):
    template = ui_templates.OneSection(self.ui)

    template.SetTitle(
        i18n_test_ui.MakeI18nLabel('Select {label}', label=self.args.label))

    # Display choices as radio buttons.
    radio_button_html = ''
    choices = self.args.choices.keys()
    choices.sort()
    for i in xrange(len(choices)):
      choice = choices[i]
      radio_button_html += (
          '<input name="select-value" type="radio" value="%s" id="choice_%d">' %
          (choice, i) +
          '<label for="choice_%d">%s</label><br>' % (i, choice))
    template.SetState(
        i18n_test_ui.MakeI18nLabel(
            'Please select the {label} and press ENTER.',
            label=self.args.label) + '<br>' + radio_button_html + '<br>&nbsp;'
        '<p id="select-error" class="test-error">&nbsp;')

    # Handle selected value when Enter pressed.
    self.ui.BindKeyJS(
        test_ui.ENTER_KEY,
        'window.test.sendTestEvent("select_value",'
        'function(){'
        '  choices = document.getElementsByName("select-value");'
        '  for (var i = 0; i < choices.length; ++i)'
        '    if (choices[i].checked)'
        '      return choices[i].value;'
        '  return "";'
        '}())')
    self.ui.AddEventHandler('select_value', self.HandleSelectValue)

    self.ui.Run()
