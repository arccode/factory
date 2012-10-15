#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.test import factory
from cros.factory.test import test_ui

_UI_TEMPLATE_PATH = '/ui_templates'

class BaseTemplate(object):
  '''Base class for test UI template.'''
  def __init__(self, ui, template_name):
    self._ui = ui

    template_base = os.path.join(factory.FACTORY_PACKAGE_PATH,
                                 'goofy/static/ui_templates')
    html_file = os.path.join(template_base, template_name + '.html')
    assert os.path.exists(html_file), \
           'Template %s does not exist.' % template_name

    # Load template HTML
    self._ui.SetHTML(open(html_file).read())

    # Load template JS if it exists
    js_file = os.path.join(template_base, template_name + '.js')
    if os.path.exists(js_file):
      self._ui.RunJS(open(js_file).read())

    metadata = factory.get_current_test_metadata()
    self.SetTitle(test_ui.MakeLabel(metadata.get('label_en', ''),
                                    metadata.get('label_zh', '')))

  def SetTitle(self, html):
    '''Sets the title of the test UI.

    Args:
      html: The html content to write.'''
    self._ui.SetHTML(html, id='title')

  def BindStandardKeys(self, bind_pass_key=True, bind_fail_key=True):
    '''Binds standard pass and/or fail keys.

    Also shows prompt at the bottom of the test area.

    Args:
      bind_pass_key: True to bind keys to pass the test.
      bind_fail_key: True to bind keys to fail the test.
    '''
    self._ui.SetHTML(
      test_ui.MakePassFailKeyLabel(pass_key=bind_pass_key,
                                   fail_key=bind_fail_key),
      id='prompt-pass-fail-keys')
    self._ui.BindStandardKeys(bind_pass_keys=bind_pass_key,
                              bind_fail_keys=bind_fail_key)


class OneSection(BaseTemplate):
  '''A simple template that has only one big section.

  This is a simple template which is suitable for tests that do not
  require showing much information.

  This template provides the following sections:
    - SetTitle:
        For the title of the test.
    - SetState:
        For displaying the state of the test or instructions to
        operator.
  '''
  def __init__(self, ui): # pylint: disable=W0231
    super(OneSection, self).__init__(ui, 'template_one_section')

  def SetState(self, html, append=False):
    '''Sets the state section in the test UI.

    Args:
      html: The html to write.'''
    self._ui.SetHTML(html, append=append, id='state')


class OneScrollableSection(BaseTemplate):
  '''Like OneSection, but is used to show more info.

  Instead of central-aligned state window, it shows state in a scrollable
  element and state is left-aligned.

  This template provides the following sections:
    - SetTitle:
        For the title of the test.
    - SetState:
        For displaying the state of the test.
  '''
  def __init__(self, ui): # pylint: disable=W0231
    super(OneScrollableSection, self).__init__(
      ui, 'template_one_scrollable_section')

  def SetState(self, html, append=False):
    '''Sets the state section in the test UI.

    Args:
      html: The html to write.'''
    self._ui.SetHTML(html, append=append, id='state')


class TwoSections(BaseTemplate):
  '''A template that consists of two sections.

  The upper sections is for showing instructions to operators, and
  has a progress bar that is hidden by default. The lower section
  is for showing information regarding test state, like instructional
  pictures, or texts that indicate the progress of the test.

  This template provides the following methods:
    - SetTitle:
        For the title of the test.
    - SetInstruction:
        For displaying instructions to the operator.
    - SetState:
        For visually displaying the test progress.
    - DrawProgressBar, SetProgressBarValue:
        For showing information regarding the progress or state of the
        test. The progress bar is hidden by default.
  '''
  def __init__(self, ui): # pylint: disable=W0231
    super(TwoSections, self).__init__(ui, 'template_two_sections')

  def SetInstruction(self, html, append=False):
    '''Sets the instruction to operator.

    Args:
      html: The html content to write.'''
    self._ui.SetHTML(html, append=append, id='instruction')


  def SetState(self, html, append=False):
    '''Sets the state section in the test UI.

    Args:
      html: The html to write.'''
    self._ui.SetHTML(html, append=append, id='state')

  def DrawProgressBar(self):
    '''Draw the progress bar and set it visible on the Chrome test UI.

    Best practice is that if the operator needs to wait more than 5 seconds,
    we should show the progress bar to indicate test progress.
    '''
    self._ui.CallJSFunction('DrawProgressBar')

  def SetProgressBarValue(self, value):
    '''Set the value of the progress bar.

    Args:
      value: A value between 0 and 100 to indicate test progress.
    '''
    self._ui.CallJSFunction('SetProgressBarValue', value)
