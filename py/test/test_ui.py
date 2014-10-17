#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for creating and interacting with factory test UI."""

import cgi
import logging
import os
import threading
import traceback
import uuid

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import utils
from cros.factory.test.event import Event, EventClient
from cros.factory.test.factory import TestState


# For compatibility; moved to factory.
FactoryTestFailure = factory.FactoryTestFailure

# Keycodes
ENTER_KEY = 13
ESCAPE_KEY = 27

# A list of tuple (exception-source, exception-desc):
#   exception-source: Source of exception. For example, 'ui-thread' if the
#     exception comes from UI thread.
#   exception-desc: Exception message.
exception_list = []

# HTML for spinner icon.
SPINNER_HTML_16x16 = '<img src="/images/active.gif" width=16 height=16>'

def Escape(text, preserve_line_breaks=True):
  """Escapes HTML.

  Args:
    text: The text to escape.
    preserve_line_breaks: True to preserve line breaks.
  """
  html = cgi.escape(text)
  if preserve_line_breaks:
    html = html.replace('\n', '<br>')
  return html


def MakeLabel(en, zh=None, css_class=None):
  """Returns a label which will appear in the active language.

  For optional zh, if it is None or empty, the Chinese label will fallback to
  use English version

  Args:
      en: The English-language label.
      zh: The Chinese-language label (or None if unspecified).
      css_class: The CSS class to decorate the label (or None if unspecified).
  """
  return ('<span class="goofy-label-en %s">%s</span>'
          '<span class="goofy-label-zh %s">%s</span>' %
          ('' if css_class is None else css_class, en,
           '' if css_class is None else css_class, zh if zh else en))


def MakeTestLabel(test):
  """Returns label for a test name in the active language.

  Args:
     test: A test object from the test list.
  """
  return MakeLabel(Escape(test.label_en), Escape(test.label_zh))


def MakePassFailKeyLabel(pass_key=True, fail_key=True):
  """Returns label for an instruction of pressing pass key in the active
  language.
  """
  if not pass_key and not fail_key:
    return ''
  en, zh = '', ''
  if pass_key:
    en += 'Press Enter to pass. '
    zh += u'通過請按ENTER鍵  '
  if fail_key:
    en += 'Press ESC to fail.'
    zh += u'失敗請按ESC鍵'
  return MakeLabel(en, zh)


def MakeStatusLabel(status):
  """Returns label for a test status in the active language.

  Args:
      status: One of [PASSED, FAILED, ACTIVE, UNTESTED]
  """
  STATUS_ZH = {
    TestState.PASSED: u'良好',
    TestState.FAILED: u'不良',
    TestState.ACTIVE: u'正在测',
    TestState.UNTESTED: u'未测'
  }
  return MakeLabel(status.lower(),
                   STATUS_ZH.get(status, status))


class UI(object):
  """Web UI for a factory test."""
  def __init__(self, css=None, setup_static_files=True):
    self.lock = threading.RLock()
    self.event_client = EventClient(callback=self._HandleEvent,
                                    event_loop=EventClient.EVENT_LOOP_WAIT)
    self.test = os.environ['CROS_FACTORY_TEST_PATH']
    self.invocation = os.environ['CROS_FACTORY_TEST_INVOCATION']
    try:
      self.parent_invocation = os.environ['CROS_FACTORY_TEST_PARENT_INVOCATION']
    except KeyError as e:
      # Parent invocation UUID is set upon the process of each test case is
      # spawned. If we can't find the parent invocation UUID here, most likely
      # the UI object was created in cstor instead of setUp in the TestCase
      # sub-class, which caused the top-level invocation to create the UI object
      # while it was loading the test cases. This is tricky so make the error
      # message more verbose here.
      raise KeyError(
          ('%s. Note that UI object must not be created in unittest.TestCase '
           'cstor; create the UI object in setUp instead') % e)
    self.event_handlers = {}
    self.task_hook = None
    self.static_dir_path = None

    if setup_static_files:
      self._SetupStaticFiles(os.path.realpath(traceback.extract_stack()[-2][0]))
      if css:
        self.AppendCSS(css)
    self.error_msgs = []

  def _SetupStaticFiles(self, py_script):
    # Get path to caller and register static files/directories.
    base = os.path.splitext(py_script)[0]

    # Directories we'll autoload .html and .js files from.
    autoload_bases = [base]

    # Find and register the static directory, if any.
    static_dirs = filter(os.path.exists,
                         [base + '_static',
                          os.path.join(os.path.dirname(py_script), 'static')
                         ])
    if len(static_dirs) > 1:
      raise FactoryTestFailure('Cannot have both of %s - delete one!' %
                               static_dirs)
    if static_dirs:
      factory.get_state_instance().register_path(
          '/tests/%s' % self.test, static_dirs[0])
      autoload_bases.append(
          os.path.join(static_dirs[0], os.path.basename(base)))
      self.static_dir_path = static_dirs[0]

    def GetAutoload(extension):
      autoload = filter(os.path.exists,
                        [x + '.' + extension
                         for x in autoload_bases])
      if not autoload:
        return ''
      if len(autoload) > 1:
        raise FactoryTestFailure(
            'Cannot have both of %s - delete one!' %
            autoload)

      factory.get_state_instance().register_path(
        '/tests/%s/%s' % (self.test, os.path.basename(autoload[0])),
        autoload[0])
      return open(autoload[0]).read()

    html = '\n'.join(
      ['<head id="head">',
       '<base href="/tests/%s/">' % self.test,
       '<link rel="stylesheet" type="text/css" href="/goofy.css">',
       '<link rel="stylesheet" type="text/css" href="/test.css">',
       GetAutoload('html')])
    self.PostEvent(Event(Event.Type.INIT_TEST_UI, html=html))

    js = GetAutoload('js')
    if js:
      self.RunJS(js)

  def SetHTML(self, html, append=False, id=None):  # pylint: disable=W0622
    """Sets a HTML snippet to the UI in the test pane.

    Note that <script> tags are not allowed in SetHTML() and
    AppendHTML(), since the scripts will not be executed. Use RunJS()
    or CallJSFunction() instead.

    Args:
      html: The HTML snippet to set.
      append: Whether to append the HTML snippet.
      id: If given, writes html to the element identified by id.
    """
    self.PostEvent(Event(Event.Type.SET_HTML, html=html, append=append, id=id))

  def AppendHTML(self, html, **kwargs):
    """Append to the UI in the test pane."""
    self.SetHTML(html, True, **kwargs)

  def AppendCSS(self, css):
    """Append CSS in the test pane."""
    self.AppendHTML('<style type="text/css">%s</style>' % css,
                    id="head")

  def RunJS(self, js, **kwargs):
    """Runs JavaScript code in the UI.

    Args:
      js: The JavaScript code to execute.
      kwargs: Arguments to pass to the code; they will be
        available in an "args" dict within the evaluation
        context.

    Example:
      ui.RunJS('alert(args.msg)', msg='The British are coming')
    """
    self.PostEvent(Event(Event.Type.RUN_JS, js=js, args=kwargs))

  def CallJSFunction(self, name, *args):
    """Calls a JavaScript function in the test pane.

    This will be run within window scope (i.e., 'this' will be the
    test pane window).

    Args:
      name: The name of the function to execute.
      args: Arguments to the function.
    """
    self.PostEvent(Event(Event.Type.CALL_JS_FUNCTION, name=name, args=args))

  def AddEventHandler(self, subtype, handler):
    """Adds an event handler.

    Args:
      subtype: The test-specific type of event to be handled.
      handler: The handler to invoke with a single argument (the event
        object).
    """
    self.event_handlers.setdefault(subtype, []).append(handler)

  def PostEvent(self, event):
    """Posts an event to the event queue.

    Adds the test and invocation properties.

    Tests should use this instead of invoking post_event directly.
    """
    event.test = self.test
    event.invocation = self.invocation
    event.parent_invocation = self.parent_invocation
    self.event_client.post_event(event)

  def URLForFile(self, path):
    """Returns a URL that can be used to serve a local file.

    Args:
      path: path to the local file

    Returns:
      url: A (possibly relative) URL that refers to the file
    """
    return factory.get_state_instance().URLForFile(path)

  def URLForData(self, mime_type, data, expiration=None):
    """Returns a URL that can be used to serve a static collection
    of bytes.

    Args:
      mime_type: MIME type for the data
      data: Data to serve
      expiration: If not None, the number of seconds in which the data will
        expire.
    """
    return factory.get_state_instance().URLForData(
        mime_type, data, expiration)

  def GetStaticDirectoryPath(self):
    """Gets static directory os path.

    Returns:
      OS path for static directory; Return None if no static directory.
    """
    return self.static_dir_path

  def Pass(self):
    """Passes the test."""
    self.PostEvent(Event(Event.Type.END_TEST, status=TestState.PASSED))

  def Fail(self, error_msg):
    """Fails the test immediately."""
    self.PostEvent(Event(Event.Type.END_TEST, status=TestState.FAILED,
                         error_msg=error_msg))

  def FailLater(self, error_msg):
    """Appends a error message to the error message list, which causes
    the test to fail later.
    """
    self.error_msgs.append(error_msg)

  def EnablePassFailKeys(self):
    """Allows space/enter to pass the test, and escape to fail it."""
    self.BindStandardKeys()

  def Run(self, blocking=True, on_finish=None):
    """Runs the test UI, waiting until the test completes.

    Args:
      blocking: True if running UI in the same thread. False if creating a
        dedicated UI thread. Test UI must not be non-blocking if used in
        autotest.
      on_finish: Callback function when UI ends. This can be used to notify
        the test for necessary clean-up (e.g. terminate an event loop.)
    """
    def _RunImpl(self, blocking, on_finish):
      event = self.event_client.wait(
          lambda event:
            (event.type == Event.Type.END_TEST and
             event.invocation == self.invocation and
             event.test == self.test))
      logging.info('Received end test event %r', event)
      if self.task_hook:
        # Let factory task have a chance to do its clean up work.
        # pylint: disable=W0212
        self.task_hook._Finish(getattr(event, 'error_msg', ''))
      self.event_client.close()

      try:
        if event.status == TestState.PASSED and not self.error_msgs:
          pass
        elif event.status == TestState.FAILED or self.error_msgs:
          error_msg = getattr(event, 'error_msg', '')
          if self.error_msgs:
            error_msg += ('\n'.join([''] + self.error_msgs))

          if blocking:
            raise FactoryTestFailure(error_msg)
          else:
            # Save exception if UI is not run in the main thread
            exception_list.append(('ui-thread',
                                   'Failed from UI\n%s' % error_msg))
        else:
          raise ValueError('Unexpected status in event %r' % event)
      finally:
        if on_finish:
          on_finish()

    if not blocking:
      return utils.StartDaemonThread(
          target=lambda: _RunImpl(self, blocking=False, on_finish=on_finish))
    else:
      _RunImpl(self, blocking=True, on_finish=on_finish)

  def BindStandardKeys(self, bind_pass_keys=True, bind_fail_keys=True):
    """Binds standard pass and/or fail keys.

    Args:
      bind_pass_keys: True if binding pass keys, including enter, space,
        'p', and 'P'.
      bind_fail_keys: True if binding fail keys, including ESC, 'f', and 'F'.
    """
    items = []
    if bind_pass_keys:
      items.extend([(key, 'window.test.pass()') for key in '\r pP'])
    if bind_fail_keys:
      items.extend([(key, 'window.test.fail()') for key in 'fF\x1b'])
    self.BindKeysJS(items)

  def BindKeysJS(self, items):
    """Binds keys to JavaScript code.

    Args:
      items: A list of tuples (key, js), where
        key: The key to bind (if a string), or an integer character code.
        js: The JavaScript to execute when pressed.
    """
    js_list = []
    for key, js in items:
      key_code = key if isinstance(key, int) else ord(key)
      js_list.append('window.test.bindKey(%d, function() { %s });' %
                     (key_code, js))
    self.RunJS(''.join(js_list))

  def BindKeyJS(self, key, js):
    """Sets a JavaScript function to invoke if a key is pressed.

    Args:
      key: The key to bind (if a string), or an integer character code.
      js: The JavaScript to execute when pressed.
    """
    self.BindKeysJS([(key, js)])

  def BindKey(self, key, handler):
    """Sets a key binding to invoke the handler if the key is pressed.

    Args:
      key: The key to bind.
      handler: The handler to invoke with a single argument (the event
          object).
    """
    uuid_str = str(uuid.uuid4())
    self.BindKeyJS(key, 'test.sendTestEvent("%s", {});' % uuid_str)
    self.AddEventHandler(uuid_str, handler)

  def UnbindKey(self, key):
    """Removes a key binding in frontend Javascript.

    Args:
      key: The key to unbind.
    """
    key_code = key if isinstance(key, int) else ord(key)
    self.RunJS('window.test.unbindKey(%d);' % key_code)

  def InEngineeringMode(self):
    """Returns True if in engineering mode."""
    return factory.get_shared_data('engineering_mode')

  def _HandleEvent(self, event):
    """Handles an event sent by a test UI."""
    if (event.type == Event.Type.TEST_UI_EVENT and
        event.test == self.test and
        event.invocation == self.invocation):
      with self.lock:
        for handler in self.event_handlers.get(event.subtype, []):
          handler(event)

  def GetUILanguage(self):
    """Returns current enabled language in UI."""
    return factory.get_shared_data('ui_lang')

  def PlayAudioFile(self, audio_file):
    """Plays an audio file in the given path."""
    js = """
        var audio_element = new Audio("%s");
        audio_element.addEventListener(
            "canplaythrough",
            function () {
              audio_element.play();
            });
    """ % os.path.join('/sounds', audio_file)
    self.RunJS(js)

  def SetFocus(self, element_id):
    """Set focus to the element specified by element_id"""
    self.RunJS('$("%s").focus()' % element_id)

  def SetSelected(self, element_id):
    """Set the specified element as selected"""
    self.RunJS('$("%s").select()' % element_id)

  def HideTooltips(self):
    """Hides tooltips."""
    self.PostEvent(Event(Event.Type.HIDE_TOOLTIPS))
