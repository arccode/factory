# -*- mode: python; coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest


from cros.factory.event_log import Log
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg


class SelectAuxField(unittest.TestCase):
  '''Display choices for user to select.

  Choices are displayed as radio buttons and the selected value is stored in
  shopfloor aux_data with the specified aux table name, id, and col name.
  '''

  ARGS = [
    Arg('label_en', str,
        'Name of the model being selected'),
    Arg('label_zh', str,
        'Chinese name of the model being selected '
        '(defaults to the same as the English label)'),
    Arg('event_log_key', str,
        'Key to use for event log', optional=True),
    Arg('aux_table_name', str,
        'Name of the auxiliary table'),
    Arg('aux_id', str,
        'Name of the auxiliary ID'),
    Arg('col_name', str,
        'Column name to store the selected value'),
    Arg('choices', dict,
        'Dictionary consists of pairs of choice label and value to be stored.'),
  ]

  def HandleSelectValue(self, event):
    def SetError(label_en, label_zh=None):
      logging.info('Select error: %r', label_en)
      self.ui.SetHTML(test_ui.MakeLabel(label_en, label_zh),
                      id='select-error')

    select_value = event.data.strip()
    logging.debug('Selected value: %s', select_value)
    if not select_value:
      return SetError('No selection.', '未选择。')

    try:
      shopfloor.save_aux_data(
          self.args.aux_table_name, self.args.aux_id,
          {self.args.col_name: self.args.choices.get(select_value)})
    except:  # pylint: disable=W0702
      logging.exception('save_aux_data failed')
      return SetError(utils.FormatExceptionOnly())

    # Update tests according to shopfloor aux_data and test run_if setting.
    factory.get_state_instance().UpdateSkippedTests()

    if self.args.event_log_key:
      Log('select', key=self.args.event_log_key, value=select_value)

    self.ui.Pass()

  def setUp(self):
    self.ui = test_ui.UI()

  def runTest(self):
    template = ui_templates.OneSection(self.ui)

    if not self.args.label_zh:
      self.args.label_zh = self.args.label_en

    template.SetTitle(test_ui.MakeLabel(
        'Select %s' % self.args.label_en.title(),
        '选择%s' % self.args.label_zh))

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
        test_ui.MakeLabel(
            'Please select the %s and press ENTER.' % self.args.label_en,
            '请选择%s後按下 ENTER。' % (
                self.args.label_zh or self.args.label_en)) + '<br>' +
                radio_button_html + '<br>&nbsp;'
        '<p id="select-error" class="test-error">&nbsp;')

    # Handle selected value when Enter pressed.
    self.ui.BindKeyJS(
        '\r',
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
