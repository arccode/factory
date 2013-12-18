# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""UI actuator module that interacts with the test UI in E2E tests."""

import logging
import re
import time

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.test import event
from cros.factory.test import test_ui
from cros.factory.test import utils


class UIActuatorError(Exception):
  """UIActuator error."""
  pass


class UIActuator(test_ui.UI):
  """UI actuator to interact with the front-end of the factory test under test.

  Attributes:
    invocation: The invocation identifier of the factory test under test.
  """
  EVENT_KEY_DOWN = 'keydown'
  EVENT_KEY_PRESS = 'keypress'
  EVENT_KEY_UP = 'keyup'

  KEY_ENTER = '\r'
  KEY_SPACE = ' '

  UI_POLL_INTERVAL_SECS = 0.1

  def __init__(self, e2e_test):
    super(UIActuator, self).__init__(setup_static_files=False)
    self.e2e_test = e2e_test
    self.initialized = False
    self._return_values = {}

    def _Run():
      self.event_client.wait(
          lambda e:
            (e.type == event.Event.Type.END_TEST and
             e.invocation == self.invocation and
             e.test == self.test))

    utils.StartDaemonThread(target=_Run)

  def Init(self):
    if not self.initialized:
      self.e2e_test.StartFactoryTest()
      self.initialized = True
      # Wait until UI completes loading.
      self.PollUI(
          'document.readyState',
          lambda rv: rv == 'complete',
          timeout_secs=5)

  def PollUI(self, js, condition, timeout_secs=5):
    """Polls the UI with the given JavaScript until the given condition is True.

    Args:
      js: The JavaScript snippet to execute.
      condition: A callable that takes one arg as the return value from polling
        and returns True or False.
      timeout_secs: Timeout in seconds.

    Returns:
      The return value polled.

    Raises:
      UIActuatorError: If the given condition is not met before time out.
    """
    if not callable(condition):
      raise UIActuatorError('"condition" must be a callable object')

    self.Init()
    event_subtype = event_log.TimedUuid()

    def _HandlePollUI(e):
      with self.lock:
        logging.debug('Poll handler %r got return value: %r', event_subtype,
                      e.data)
        self._return_values[event_subtype] = e.data

    try:
      logging.debug(
          'Set up polling for %r with event_subtype %r',
          js, event_subtype)
      self.AddEventHandler(event_subtype, _HandlePollUI)
      end_time = time.time() + timeout_secs
      while time.time() < end_time:
        if not self.e2e_test.pytest_thread.isAlive():
          raise UIActuatorError('Factory test stopped during polling.')

        self.RunJS(
            'window.test.sendTestEvent("%s", %s);' %
            (event_subtype, js))
        time.sleep(self.UI_POLL_INTERVAL_SECS)
        with self.lock:
          if (event_subtype in self._return_values and
              condition(self._return_values[event_subtype])):
            return self._return_values[event_subtype]
      raise UIActuatorError('Timeout polling UI')
    finally:
      with self.lock:
        if event_subtype in self.event_handlers:
          del self.event_handlers[event_subtype]
        if event_subtype in self._return_values:
          del self._return_values[event_subtype]

  def WaitForContent(self, element_id=None, attribute='innerHTML',
                     search_text=None, search_regexp=None, condition=None,
                     timeout_secs=5):
    """Waits for and returns the innerHTML content of a DOM element.

    Args:
      element_id: The id of the DOM element to get content from.
      attribute: The name of the attribute to get content from.
      search_text: If not None, waits until the content contains the given text.
      search_regexp: If not None, waits until the regexp pattern shows in the
        content.
      condition: If not None, waits until the condition evaluates to True.
      timeout_secs: Timeout in seconds.

    Returns:
      The content fetched from the DOM element.

    Raises:
      UIActuatorError when timeout elapses.
    """
    conditions_set = filter(None, [search_text, search_regexp, condition])
    if len(conditions_set) > 1:
      raise UIActuatorError('Only one of "search_text", "search_regexp", '
                            'or "condition" can be set')

    self.Init()
    if element_id:
      js = ('function() {'
            '  var element = document.getElementById("%s");'
            '  if (element) { return element.%s; }'
            '  return null;'
            '}()' % (element_id, attribute))
    else:
      js = 'function() { return document.body.%s; }()' % attribute

    if search_text:
      poll_condition = lambda text: text is not None and search_text in text
    elif search_regexp:
      poll_condition = lambda text: (
          text is not None and re.search(search_regexp, text))
    elif condition:
      poll_condition = condition
    else:
      poll_condition = lambda text: text is not None

    return self.PollUI(js, poll_condition, timeout_secs)

  def SetElementAttribute(self, element_id, attribute, text, timeout_secs=5):
    """Sets attribute of a DOM element.

    Args:
      element_id: The id of the DOM element to set content of.
      attribute: The attribute of the DOM element to set.
      text: The content to set.
      timeout_secs: Timeout in seconds.
    """
    self.Init()
    logging.info('Set %s.%s to %r', element_id, attribute, text)
    return self.PollUI("""
        function() {
          var element = document.getElementById("%s");
          if (element) { element.%s = "%s"; return true; }
          return false;
        }()""" % (element_id, attribute, test_ui.Escape(text)),
        lambda rv: rv, timeout_secs=timeout_secs)

  def SetElementValue(self, element_id, text, timeout_secs=5):
    """Sets "value" attribute of a DOM element.

    Args:
      element_id: The id of the DOM element to set content of.
      text: The content to set.
      timeout_secs: Timeout in seconds.
    """
    self.Init()
    self.SetElementAttribute(element_id, 'value', text, timeout_secs)

  def PressKey(self, key, event_type=None, element_id=None,
               ctrl=False, alt=False, shift=False, meta=False):
    """Triggers a keyboard event of the given key.

    Args:
      key: The key to press.
      event_type: The event type.  Must be one of:
        (None, "keydown", "keyup", "keypress").  In case of None, the method
        sends out a series of "keydown", "keypress", "keyup" events.
      element_id: The id of the DOM element to dispatch the keyboard event to.
      ctrl: Whether to press ctrl.
      alt: Whether to press alt.
      shift: Whether to press shift.
      meta: Whether to press meta.
    """
    self.Init()
    if isinstance(key, str) and len(key) == 1:
      key = key.upper()
      key_code = 'args.key.charCodeAt(0)'
    elif isinstance(key, int):
      key_code = key
    else:
      raise UIActuatorError('key must be a character or an integer')

    target = ('document.getElementById("%s")' % element_id
              if element_id else 'document.activeElement')

    def SendKeyEvent(event_type):
      if event_type not in (self.EVENT_KEY_DOWN, self.EVENT_KEY_PRESS,
                            self.EVENT_KEY_UP):
        raise UIActuatorError('Invalid keyboard event type: %r' % event_type)

      logging.debug('Send event %r for key %r '
                    '(ctrl=%r, alt=%r, shift=%r, meta=%r)',
                    event_type, key, ctrl, alt, shift, meta)
      self.RunJS("""
          var element = %(target)s;
          var event = document.createEvent("KeyboardEvent");
          Object.defineProperty(event, "keyCode", {
              get: function() { return this.keyCodeVal; }});
          Object.defineProperty(event, "which", {
              get: function() { return this.keyCodeVal; }});
          event.initKeyboardEvent(
                 "%(event_type)s", true, false, window,
                 args.ctrl, args.alt, args.shift, args.meta, 0, %(key_code)s);
          event.keyCodeVal = %(key_code)s;
          element.dispatchEvent(event);
          """ % ({'target': target, 'event_type': event_type,
                  'key_code': key_code}),
          key=key, ctrl=ctrl, alt=alt, shift=shift, meta=meta)

    if event_type:
      # An explicit event_type is given.  Send only the given event.
      SendKeyEvent(event_type)
    else:
      # Default to send keydown, keypress, and keyup.  This is the series of
      # events being triggered when a key is pressed physically.
      SendKeyEvent(self.EVENT_KEY_DOWN)
      SendKeyEvent(self.EVENT_KEY_PRESS)
      SendKeyEvent(self.EVENT_KEY_UP)
