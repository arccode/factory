# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""UI to prompt operator to flip into tablet mode or notebook mode."""

import os
import time

import factory_common  # pylint: disable=unused-import

from cros.factory.test import test_ui
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test.ui_templates import OneSection


_FLASH_STATUS_TIME = 1

_MSG_PROMPT_FLIP_TABLET = i18n_test_ui.MakeI18nLabel(
    'Flip the lid into tablet mode')
_MSG_PROMPT_FLIP_NOTEBOOK = i18n_test_ui.MakeI18nLabel(
    'Open the lid back to notebook mode')
_MSG_CONFIRM_TABLET_MODE = i18n_test_ui.MakeI18nLabel('Confirm tablet mode')
_MSG_CONFIRM_NOTEBOOK_MODE = i18n_test_ui.MakeI18nLabel(
    'Press SPACE to confirm notebook mode')
_MSG_STATUS_SUCCESS = i18n_test_ui.MakeI18nLabel('Success!')
_MSG_STATUS_FAILURE = i18n_test_ui.MakeI18nLabel('Failure')

_ID_PROMPT = 'lid-test-prompt'
_ID_CONFIRM_BUTTON = 'confirm-button'
_ID_STATUS = 'status'

_CLASS_IMAGE_FLIP_TABLET = 'notebook-to-tablet'
_CLASS_IMAGE_FLIP_NOTEBOOK = 'tablet-to-notebook'

_EVENT_CONFIRM_TABLET_MODE = 'confirm_tablet_mode'

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
    # pylint: disable=protected-access
    self.ui._SetupStaticFiles(os.path.realpath(__file__), '')

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
    self.ui.SetHTML(_MSG_CONFIRM_NOTEBOOK_MODE,
                    id=_ID_CONFIRM_BUTTON)
    self.ui.SetHTML(_HTML_EMPTY, id=_ID_STATUS)
    # Ask OP to press space to verify the dut is in notebook mode.
    # Set virtual_key to False since the event callback should be triggered
    # from a real key press, not from a button on screen.
    self.ui.BindKey(test_ui.SPACE_KEY, event_callback, virtual_key=False)
    self.ui.RunJS('document.getElementById("%s").focus()' % _ID_CONFIRM_BUTTON)

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
