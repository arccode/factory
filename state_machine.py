# -*- coding: utf-8 -*-
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# DESCRIPTION :
#
# This module provides a framework for factory test which procedure can be
# described as a state machine, ex: factory AB panel test.


import gtk
import re

from autotest_lib.client.bin import test
from autotest_lib.client.cros.factory import task
from autotest_lib.client.cros.factory import ui as ful


_LABEL_SIZE = (300, 30)
COLOR_MAGENTA = gtk.gdk.color_parse('magenta1')

class FactoryStateMachine(test.test):
    '''Simplified state machine for factory AB panel test.

    Many factory AB panel tests shares similar procedure. This class provides
    a framework to avoid duplicating codes. The simplified state machine is
    designed for repeating a sequence of state without branches. Class
    inherited this class have to implement their own run_once function and
    have its states information ready before they call start_state_machine.

    Attributes:
        current_state: The identifier of the state.
    '''

    def __init__(self, *args, **kwargs):
        super(FactoryStateMachine, self).__init__(*args, **kwargs)
        self.current_state = None
        self._states = dict()
        self._last_widget = None
        self._status_rows = list()
        self._results_to_check = list()

    def advance_state(self, new_state=None):
        '''Advances state according to the states information.

        A callback function will be scheduled for execution after UI is
        updated.

        Args:
          new_state: Given a non-None value set the current state to new_state.
        '''
        if new_state is None:
            self.current_state = self._states[self.current_state]['next_state']
        else:
            self.current_state = new_state
        assert self.current_state in self._states, (
            'State %s is not found' % self.current_state)

        # Update the UI.
        state_info = self._states[self.current_state]
        self._switch_widget(state_info['widget'])
        # Create an event to invoke function after UI is updated.
        if state_info['callback']:
            task.schedule(state_info['callback'],
                          *state_info['callback_parameters'])

    def _switch_widget(self, widget_to_display):
        '''Switches current displayed widget to a new one'''
        if widget_to_display is not self._last_widget:
            if self._last_widget:
                self._last_widget.hide()
                self.test_widget.remove(self._last_widget)
            self._last_widget = widget_to_display
            self.test_widget.add(widget_to_display)
            self.test_widget.show_all()
        else:
            return

    def _key_action_mapping_callback(self, widget, event, key_action_mapping):
        if event.keyval in key_action_mapping:
            callback, callback_parameters = key_action_mapping[event.keyval]
            callback(*callback_parameters)
            return True

    def make_decision_widget(self,
                             message,
                             key_action_mapping,
                             fg_color=ful.LIGHT_GREEN):
        '''Returns a widget that display the message and bind proper functions.

        Args:
          message: Message to display on the widget.
          key_action_mapping: A dict of tuples indicates functions and keys
              in the format {gtk_keyval: (function, function_parameters)}

        Returns:
          A widget binds with proper functions.
        '''
        widget = gtk.VBox()
        widget.add(ful.make_label(message, fg=fg_color))
        widget.key_callback = (
            lambda w, e: self._key_action_mapping_callback(
                w, e, key_action_mapping))
        return widget

    def make_result_widget(self,
                           message,
                           key_action_mapping,
                           fg_color=ful.LIGHT_GREEN):
        '''Returns a result widget and bind proper functions.

        This function generate a result widget from _status_names and
        _status_labels. Caller have to update the states information manually.

        Args:
          message: Message to display on the widget.
          key_action_mapping: A dict of tuples indicates functions and keys
              in the format {gtk_keyval: (function, function_parameters)}

        Returns:
          A widget binds with proper functions.
        '''
        self._status_rows.append(('result', 'Final result', True))

        widget = gtk.VBox()
        widget.add(ful.make_label(message, fg=fg_color))

        self.display_dict = {}
        for name, label, is_standard_status in self._status_rows:
            if is_standard_status:
                _dict, _widget = ful.make_status_row(
                    label, ful.UNTESTED, _LABEL_SIZE)
            else:
                _dict, _widget = ful.make_status_row(
                    label, '', _LABEL_SIZE, is_standard_status)
            self.display_dict[name] = _dict
            widget.add(_widget)

        widget.key_callback = (
            lambda w, e: self._key_action_mapping_callback(
                w, e, key_action_mapping))
        return widget

    def make_serial_number_widget(self,
                                  message,
                                  on_complete,
                                  default_validate_regex=None,
                                  on_validate=None,
                                  on_keypress=None,
                                  generate_status_row=True):
        '''Returns a serial number input widget.

        Args:
          on_complete: A callback function when completed.
          default_validate_regex: Regular expression to validate serial number.
          on_validate: A callback function to check the SN when ENTER pressed.
                       If not setted, will use default_validate_regex.
          on_keypress: A callback function when key pressed.
          generate_status_row: Whether to generate status row.
        '''
        def default_validator(serial_number):
            '''Checks SN format matches regular expression.'''
            assert default_validate_regex, 'Regular expression is not set'
            if re.search(default_validate_regex, serial_number):
                return True
            return False

        if generate_status_row:
            # Add a status row
            self._status_rows.append(('sn', 'Serial Number', False))

        if on_validate is None:
            on_validate = default_validator

        widget = ful.make_input_window(
            prompt=message,
            on_validate=on_validate,
            on_keypress=on_keypress,
            on_complete=on_complete)
        # Make sure the entry in widget will have focus.
        widget.connect(
            'show',
            lambda *x : widget.get_entry().grab_focus())
        return widget

    def register_state(self, widget,
                       index=None,
                       callback=None,
                       next_state=None,
                       callback_parameters=None):
        '''Registers a state to transition table.

        Args:
          index: An index number for this state. If the index is not given,
                 default to the largest index + 1.
          widget: The widget belongs to this state.
          callback: The callback function after UI is updated.
          next_state: The index number of the succeeding state.
                      If the next_state is not given, default to the
                      index + 1.
          callback_parameters: Extra parameters need to pass to callback.

        Returns:
          An index number of this registered state.
        '''
        if index is None:
            # Auto enumerate an index.
            if self._states:
                index = max(self._states.keys()) + 1
            else:
                index = 0
        assert isinstance(index, int), 'index is not a number'

        if next_state is None:
            next_state = index + 1
        assert isinstance(next_state, int), 'next_state is not a number'

        if callback_parameters is None:
            callback_parameters = []
        state = {'next_state': next_state,
                 'widget': widget,
                 'callback': callback,
                 'callback_parameters': callback_parameters}

        self._states[index] = state
        return index

    def _register_callbacks(self, window):
        def key_press_callback(widget, event):
            if self._last_widget is not None:
                if hasattr(self._last_widget, 'key_callback'):
                    return self._last_widget.key_callback(widget, event)
            return False
        window.connect('key-press-event', key_press_callback)
        window.add_events(gtk.gdk.KEY_PRESS_MASK)

    def update_status(self, row_name, new_status):
        '''Updates status in display_dict.'''
        if self.display_dict[row_name]['is_standard_status']:
            result_map = {
                True: ful.PASSED,
                False: ful.FAILED,
                None: ful.UNTESTED
            }
            assert new_status in result_map, 'Unknown result'
            self.display_dict[row_name]['status'] = result_map[new_status]
        else:
            self.display_dict[row_name]['status'] = str(new_status)

    def generate_final_result(self):
        '''Generates the result from _results_to_check.'''
        self._result = all(
           ful.PASSED == self.display_dict[var]['status']
           for var in self._results_to_check)
        self.update_status('result', self._result)

    def reset_status_rows(self):
        '''Resets status row.'''
        for name, _, _ in self._status_rows:
            self.update_status(name, None)

    def start_state_machine(self, start_state):
        # Setup the initial display.
        self.test_widget = gtk.VBox()
        # Call advance_state to switch to start_state.
        self.advance_state(new_state=start_state)

        ful.run_test_widget(
                self.job,
                self.test_widget,
                window_registration_callback=self._register_callbacks)

    def run_once(self):
        raise NotImplementedError
