# -*- coding: utf-8 -*-
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""UI to prompt operator to flip into tablet mode or notebook mode."""

import os
import time

import factory_common  # pylint: disable=W0611

from cros.factory.test import test_ui
from cros.factory.test.ui_templates import OneSection


_FLASH_STATUS_TIME = 1

_MSG_PROMPT_FLIP_TABLET = test_ui.MakeLabel(
    'Flip the lid into tablet mode', u'把上盖掀开一圈直到贴合下盖')
_MSG_PROMPT_FLIP_NOTEBOOK = test_ui.MakeLabel(
    'Open the lid back to notebook mode', u'把上盖掀开直到正常笔电模式')
_MSG_CONFIRM_TABLET_MODE = test_ui.MakeLabel(
    'Confirm tablet mode', u'确认平板模式')
_MSG_CONFIRM_NOTEBOOK_MODE = test_ui.MakeLabel(
    'Confirm notebook mode', u'确认笔电模式')
_MSG_STATUS_SUCCESS = test_ui.MakeLabel(
    'Success!', u'成功！')
_MSG_STATUS_FAILURE = test_ui.MakeLabel(
    'Failure', u'失败')

_ID_PROMPT = 'lid-test-prompt'
_ID_CONFIRM_BUTTON = 'confirm-button'
_ID_STATUS = 'status'

_CLASS_IMAGE_FLIP_TABLET = 'notebook-to-tablet'
_CLASS_IMAGE_FLIP_NOTEBOOK = 'tablet-to-notebook'

_EVENT_CONFIRM_TABLET_MODE = 'confirm_tablet_mode'
_EVENT_CONFIRM_NOTEBOOK_MODE = 'confirm_notebook_mode'

_HTML_EMPTY = ''
_HTML_BUILD_CONFIRM_BUTTON = lambda button_text, test_event: (
    '<button class="confirm-button" '
    'onclick="test.sendTestEvent(\'%s\')">%s</button>' %
    (test_event, button_text))
_HTML_STATUS_SUCCESS = '<div class="success">%s</div>' % _MSG_STATUS_SUCCESS
_HTML_STATUS_FAILURE = '<div class="failure">%s</div>' % _MSG_STATUS_FAILURE
_HTML_BUILD_TEMPLATE = lambda image_class='': """
<link rel="stylesheet" type="text/css"
  href="tablet_mode_ui.css">
<div class="cont %s">
  <div id="%s" class="status"></div>
  <div class="right">
    <div id="%s" class="prompt"></div>
    <div id="%s" class="button-cont"></div>
  </div>
</div>
""" % (image_class, _ID_STATUS, _ID_PROMPT,
       _ID_CONFIRM_BUTTON)


class TabletModeUI(object):
  def __init__(self, ui, extra_html='', extra_css=''):
    self.ui = ui
    self.extra_html = extra_html
    self.extra_css = extra_css
    # TODO(kitching): Perhaps there should be a better way for a 'UI library'
    #                 to have access to its own static file directory.
    # pylint: disable=W0212
    self.ui._SetupStaticFiles(
        os.path.realpath(__file__))
    # pylint: enable=W0212

  def AskForTabletMode(self, event_callback):
    template = OneSection(self.ui)
    template.SetState(_HTML_BUILD_TEMPLATE(_CLASS_IMAGE_FLIP_TABLET)
                      + self.extra_html)
    self.ui.AppendCSS(self.extra_css)
    self.ui.SetHTML(_MSG_PROMPT_FLIP_TABLET, id=_ID_PROMPT)
    self.ui.SetHTML(_HTML_BUILD_CONFIRM_BUTTON(_MSG_CONFIRM_TABLET_MODE,
                                               _EVENT_CONFIRM_TABLET_MODE),
                    id=_ID_CONFIRM_BUTTON)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_STATUS)
    self.ui.AddEventHandler(_EVENT_CONFIRM_TABLET_MODE,
                            event_callback)

  def AskForNotebookMode(self, event_callback):
    template = OneSection(self.ui)
    template.SetState(_HTML_BUILD_TEMPLATE(_CLASS_IMAGE_FLIP_NOTEBOOK)
                      + self.extra_html)
    self.ui.AppendCSS(self.extra_css)
    self.ui.SetHTML(_MSG_PROMPT_FLIP_NOTEBOOK, id=_ID_PROMPT)
    self.ui.SetHTML(_HTML_BUILD_CONFIRM_BUTTON(_MSG_CONFIRM_NOTEBOOK_MODE,
                                               _EVENT_CONFIRM_NOTEBOOK_MODE),
                    id=_ID_CONFIRM_BUTTON)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_STATUS)
    self.ui.AddEventHandler(_EVENT_CONFIRM_NOTEBOOK_MODE,
                            event_callback)

  def _FlashStatus(self, status_label):
    template = OneSection(self.ui)
    template.SetState(_HTML_BUILD_TEMPLATE() + self.extra_html)
    self.ui.AppendCSS(self.extra_css)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_PROMPT)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_CONFIRM_BUTTON)
    self.ui.SetHTML(status_label, id=_ID_STATUS)
    time.sleep(_FLASH_STATUS_TIME)

  def FlashSuccess(self):
    self._FlashStatus(_HTML_STATUS_SUCCESS)

  def FlashFailure(self):
    self._FlashStatus(_HTML_STATUS_FAILURE)
