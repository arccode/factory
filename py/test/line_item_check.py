# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
#
# There are test situations that we want to execute certain commands and
# check whether the commands run correctly by human judgement. This is a
# base class provides a generic framework to itemize tests in this category.

import gtk

from autotest_lib.client.bin import test
from cros.factory.test import factory
from autotest_lib.client.common_lib import error
from autotest_lib.client.common_lib import utils
from cros.factory.test import task
from cros.factory.test import ui as ful


def _make_decision_widget(message, key_action_mapping):
    '''Returns a widget that display the message and bind proper functions.

    @param message: Message to display on the widget.
    @param key_release_callback:
        A dict of tuples indicates functions and keys
        in the format {gtk_keyval: (function, function_parameters)}
    @return A widget binds with proper functions.
    '''
    widget = gtk.VBox()
    widget.add(ful.make_label(message))
    def key_release_callback(_, event):
        if event.keyval in key_action_mapping:
            callback, callback_parameters = key_action_mapping[event.keyval]
            callback(*callback_parameters)
            return True

    widget.key_callback = key_release_callback
    return widget


class FactoryLineItemCheckBase(test.test):
    version = 1

    def run_once(self):
        raise NotImplementedError

    def _next_item(self):
        self._item = self._item + 1
        if self._item < len(self._items):
            # Update the UI.
            widget, cmd_line = self._items[self._item]
            self._switch_widget(widget)
            # Execute command after UI is updated.
            if cmd_line:
                task.schedule(self._run_cmd, cmd_line)
        else:
            # No more item.
            gtk.main_quit()

    def _switch_widget(self, widget_to_display):
        if widget_to_display is not self.last_widget:
            if self.last_widget:
                self.last_widget.hide()
                self.test_widget.remove(self.last_widget)
            self.last_widget = widget_to_display
            self.test_widget.add(widget_to_display)
            self.test_widget.show_all()
        else:
            return

    def _register_callbacks(self, window):
        def key_press_callback(widget, event):
            if hasattr(self.last_widget, 'key_callback'):
                return self.last_widget.key_callback(widget, event)
            return False
        window.connect('key-press-event', key_press_callback)
        window.add_events(gtk.gdk.KEY_PRESS_MASK)

    def _run_cmd(self, cmd):
        factory.log('Running command [%s]' % cmd)
        ret = utils.system_output(cmd)
        factory.log('Command returns [%s]' % ret)

    def _fail_test(self, cmd):
        raise error.TestFail('Failed with command [%s]' % cmd)

    def _check_line_items(self, item_tuples):
        factory.log('%s run_once' % self.__class__)
        # Initialize variables.
        self.last_widget = None
        self.item_tuples = item_tuples

        # Line item in (widget, command) format.
        self._items = []

        # Set up the widgets.
        # There are two types of widgets, one gives instructions without
        # judgement, the other decides whether the result matches expectations.
        self.widgets = []
        for idx, _tuple in enumerate(self.item_tuples):
            judge, cmd_line, prompt_message = _tuple
            if judge:
                # Widget involves human judgement.
                key_action_mapping = {
                    gtk.keysyms.Return: (self._next_item, []),
                    gtk.keysyms.Tab: (self._fail_test, [cmd_line])}
                self.widgets.append(_make_decision_widget(
                    prompt_message + ful.USER_PASS_FAIL_SELECT_STR,
                    key_action_mapping))
                self._items.append(
                    (self.widgets[idx], cmd_line))
            else:
                key_action_mapping = {
                    gtk.keysyms.space: (self._next_item, [])}
                self.widgets.append(_make_decision_widget(
                    prompt_message,
                    key_action_mapping))
                self._items.append((self.widgets[idx], cmd_line))

            factory.log('Item %d: %s' % (idx, cmd_line))

        self.test_widget = gtk.VBox()
        self._item = -1
        self._next_item()

        ful.run_test_widget(
                self.job,
                self.test_widget,
                window_registration_callback=self._register_callbacks)
