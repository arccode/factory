#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.test import factory

_UI_TEMPLATE_PATH = '/ui_templates'

class BaseTemplate(object):
  '''Base class for test UI template.'''
  def _LoadTemplate(self, ui, template_name):
    '''Load HTML and JS files of the template.'''
    template_base = os.path.join(factory.FACTORY_PACKAGE_PATH,
                                 'goofy/static/ui_templates')
    html_file = os.path.join(template_base, template_name + '.html')
    assert os.path.exists(html_file), \
           'Template %s does not exist.' % template_name

    # Load template HTML
    ui.SetHTML(open(html_file).read())

    # Load template JS if it exists
    js_file = os.path.join(template_base, template_name + '.js')
    if os.path.exists(js_file):
      ui.RunJS(open(js_file).read())


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
    self._ui = ui
    self._LoadTemplate(self._ui, 'template_one_section')

  def SetTitle(self, html):
    '''Sets the title of the test UI.

    Args:
      html: The html content to write.'''
    self._ui.SetHTML(html, id='title')

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
    self._ui = ui
    self._LoadTemplate(self._ui, 'template_two_sections')

  def SetTitle(self, html):
    '''Sets the title of the test UI.

    Args:
      html: The html content to write.'''
    self._ui.SetHTML(html, id='title')

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
