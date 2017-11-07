# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for creating and interacting with factory test UI."""

from __future__ import print_function

import cgi
import json
import logging
import os
import Queue
import threading
import time
import traceback
import unittest
import uuid

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import goofy_proxy
from cros.factory.test import event as test_event
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils


# Key values
ENTER_KEY = 'ENTER'
ESCAPE_KEY = 'ESCAPE'
SPACE_KEY = ' '


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


PASS_KEY_LABEL = i18n_test_ui.MakeI18nLabel('Press Enter to pass.')
FAIL_KEY_LABEL = i18n_test_ui.MakeI18nLabel('Press ESC to fail.')
PASS_FAIL_KEY_LABEL = PASS_KEY_LABEL + FAIL_KEY_LABEL

# Indicate that the test should not be automatically passed when
# RunInBackground is finished.
WAIT_FRONTEND = object()

_HANDLER_WARN_TIME_LIMIT = 5
_UI_THREAD_NAME = 'TestUIThread'


class UI(object):
  """Web UI for a factory test."""

  def __init__(self, css=None, setup_static_files=True, default_html=''):
    self.event_client = test_event.BlockingEventClient(
        callback=self._HandleEvent)
    self.test = session.GetCurrentTestPath()
    self.invocation = session.GetCurrentTestInvocation()
    self.event_handlers = {}
    self.task_hook = None
    self.static_dir_path = None

    if setup_static_files:
      self._SetupStaticFiles(session.GetCurrentTestFilePath(), default_html)
      if css:
        self.AppendCSS(css)
    self.error_msgs = []

  def _SetupStaticFiles(self, py_script, default_html):
    # Get path to caller and register static files/directories.
    base = os.path.splitext(py_script)[0]

    # Directories we'll autoload .html and .js files from.
    autoload_bases = [base]

    # Find and register the static directory, if any.
    static_dirs = filter(os.path.exists,
                         [base + '_static',
                          os.path.join(os.path.dirname(py_script), 'static')])
    if len(static_dirs) > 1:
      raise type_utils.TestFailure(
          'Cannot have both of %s - delete one!' % static_dirs)
    if static_dirs:
      self.static_dir_path = static_dirs[0]
      goofy_proxy.get_rpc_proxy(url=goofy_proxy.GOOFY_SERVER_URL).RegisterPath(
          '/tests/%s' % self.test, self.static_dir_path)
      autoload_bases.append(
          os.path.join(self.static_dir_path, os.path.basename(base)))

    def GetAutoload(extension, default=''):
      autoloads = filter(os.path.exists,
                         [x + '.' + extension for x in autoload_bases])
      if not autoloads:
        return default
      if len(autoloads) > 1:
        raise type_utils.TestFailure(
            'Cannot have both of %s - delete one!' % autoloads)

      autoload_path = autoloads[0]
      goofy_proxy.get_rpc_proxy(url=goofy_proxy.GOOFY_SERVER_URL).RegisterPath(
          '/tests/%s/%s' % (self.test, os.path.basename(autoload_path)),
          autoload_path)
      return file_utils.ReadFile(autoload_path).decode('UTF-8')

    self.SetHTML(
        html='<base href="/tests/%s/">' % self.test, id='head', append=True)

    # default CSS files are set in default_test_ui.html by goofy.py, and we
    # only set the HTML of body here.
    self.SetHTML(GetAutoload('html', default_html))

    js = GetAutoload('js')
    if js:
      self.RunJS(js)

  def SetHTML(self, html, append=False, id=None):
    """Sets a HTML snippet to the UI in the test pane.

    Note that <script> tags are not allowed in SetHTML() and
    AppendHTML(), since the scripts will not be executed. Use RunJS()
    or CallJSFunction() instead.

    Also note that if id is not given, this would set or append HTML for the
    whole body of the page, so this method should not be used without id when a
    UI template is used.

    Args:
      html: The HTML snippet to set.
      append: Whether to append the HTML snippet.
      id: If given, writes html to the element identified by id.
    """
    # pylint: disable=redefined-builtin
    self.PostEvent(test_event.Event(test_event.Event.Type.SET_HTML,
                                    html=html, append=append, id=id))

  def AppendHTML(self, html, **kwargs):
    """Append to the UI in the test pane."""
    self.SetHTML(html, append=True, **kwargs)

  def AppendCSS(self, css):
    """Append CSS in the test pane."""
    self.AppendHTML('<style type="text/css">%s</style>' % css,
                    id='head')

  def AppendCSSLink(self, css_link):
    """Append CSS link in the test pane."""
    self.AppendHTML(
        '<link rel="stylesheet" type="text/css" href="%s">' % css_link,
        id='head')

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
    self.PostEvent(
        test_event.Event(test_event.Event.Type.RUN_JS, js=js, args=kwargs))

  def CallJSFunction(self, name, *args):
    """Calls a JavaScript function in the test pane.

    This is implemented by calling to RunJS, so the 'this' variable in
    JavaScript function would be 'correct'.

    For example, calling CallJSFunction('test.alert', '123') is same as calling
    RunJS('test.alert(args.arg_1)', arg_1='123'), and the 'this' when the
    'test.alert' function is running would be test instead of window.

    Args:
      name: The name of the function to execute.
      args: Arguments to the function.
    """
    keys = ['arg_%d' % i for i in range(len(args))]
    kwargs = dict(zip(keys, args))
    self.RunJS('%s(%s)' % (name, ','.join('args.%s' % key for key in keys)),
               **kwargs)

  def AddEventHandler(self, subtype, handler):
    """Adds an event handler.

    Args:
      subtype: The test-specific type of event to be handled.
      handler: The handler to invoke with a single argument (the event object).
    """
    self.event_handlers.setdefault(subtype, []).append(handler)

  def PostEvent(self, event):
    """Posts an event to the event queue.

    Adds the test and invocation properties.

    Tests should use this instead of invoking post_event directly.
    """
    event.test = self.test
    event.invocation = self.invocation
    self.event_client.post_event(event)

  def URLForFile(self, path):
    """Returns a URL that can be used to serve a local file.

    Args:
      path: path to the local file

    Returns:
      url: A (possibly relative) URL that refers to the file
    """
    return goofy_proxy.get_rpc_proxy(
        url=goofy_proxy.GOOFY_SERVER_URL).URLForFile(path)

  def GetStaticDirectoryPath(self):
    """Gets static directory os path.

    Returns:
      OS path for static directory; Return None if no static directory.
    """
    return self.static_dir_path

  def Pass(self):
    """Passes the test."""
    self.PostEvent(test_event.Event(test_event.Event.Type.END_TEST,
                                    status=state.TestState.PASSED))

  def Fail(self, error_msg):
    """Fails the test immediately."""
    self.PostEvent(test_event.Event(test_event.Event.Type.END_TEST,
                                    status=state.TestState.FAILED,
                                    error_msg=error_msg))

  def FailLater(self, error_msg):
    """Appends a error message to the error message list.

    This would cause the test to fail when Run() finished.
    """
    self.error_msgs.append(error_msg)

  def RunInBackground(self, target):
    """Run a function in background daemon thread.

    Pass the test if the function ends without exception, and fails the test if
    there's any exception raised.
    """
    def _target():
      try:
        if target() != WAIT_FRONTEND:
          self.Pass()
      except Exception:
        self.Fail(traceback.format_exc())
    process_utils.StartDaemonThread(target=_target)

  def Run(self, on_finish=None):
    """Runs the test UI, waiting until the test completes.

    Args:
      on_finish: Callback function when UI ends. This can be used to notify
          the test for necessary clean-up (e.g. terminate an event loop.)
    """
    threading.current_thread().name = _UI_THREAD_NAME

    event = self.event_client.wait(
        lambda event:
        (event.type == test_event.Event.Type.END_TEST and
         event.invocation == self.invocation and
         event.test == self.test))
    logging.info('Received end test event %r', event)
    if self.task_hook:
      # Let task have a chance to do its clean up work.
      # pylint: disable=protected-access
      self.task_hook._Finish(getattr(event, 'error_msg', ''), abort=True)
    self.event_client.close()

    try:
      if event.status == state.TestState.PASSED and not self.error_msgs:
        pass
      elif event.status == state.TestState.FAILED or self.error_msgs:
        error_msg = getattr(event, 'error_msg', '')
        if self.error_msgs:
          error_msg += '\n'.join([''] + self.error_msgs)

        raise type_utils.TestFailure(error_msg)
      else:
        raise ValueError('Unexpected status in event %r' % event)
    finally:
      if on_finish:
        on_finish()

  def BindStandardPassKeys(self):
    """Binds standard pass keys (enter, space, 'P')."""
    self.CallJSFunction('test.bindStandardPassKeys')

  def BindStandardFailKeys(self):
    """Binds standard fail keys (ESC, 'F')."""
    self.CallJSFunction('test.bindStandardFailKeys')

  def BindStandardKeys(self):
    """Binds standard pass and fail keys."""
    self.CallJSFunction('test.bindStandardKeys')

  def BindKeyJS(self, key, js, once=False, virtual_key=True):
    """Sets a JavaScript function to invoke if a key is pressed.

    Args:
      key: The key to bind.
      js: The JavaScript to execute when pressed.
      once: If true, the key would be unbinded after first key press.
      virtual_key: If true, also show a button on screen.
    """
    self.RunJS(
        'test.bindKey(args.key, (event) => { %s }, args.once, args.virtual_key)'
        % js,
        key=key, once=once, virtual_key=virtual_key)

  def BindKey(self, key, handler, args=None, once=False, virtual_key=True):
    """Sets a key binding to invoke the handler if the key is pressed.

    Args:
      key: The key to bind.
      handler: The handler to invoke with a single argument (the event
          object).
      args: The arguments to be passed to the handler in javascript,
          which would be json-serialized.
      once: If true, the key would be unbinded after first key press.
      virtual_key: If true, also show a button on screen.
    """
    uuid_str = str(uuid.uuid4())
    args = json.dumps(args) if args is not None else '{}'
    self.AddEventHandler(uuid_str, handler)
    self.BindKeyJS(key, 'test.sendTestEvent("%s", %s);' % (uuid_str, args),
                   once=once, virtual_key=virtual_key)

  def UnbindKey(self, key):
    """Removes a key binding in frontend JavaScript.

    Args:
      key: The key to unbind.
    """
    self.CallJSFunction('test.unbindKey', key)

  def UnbindAllKeys(self):
    """Removes all key bindings in frontend JavaScript."""
    self.CallJSFunction('test.unbindAllKeys')

  def _HandleEvent(self, event):
    """Handles an event sent by a test UI."""
    if (event.type == test_event.Event.Type.TEST_UI_EVENT and
        event.test == self.test and
        event.invocation == self.invocation):
      for handler in self.event_handlers.get(event.subtype, []):
        start_time = time.time()
        try:
          handler(event)
        except Exception as e:
          self.Fail(str(e))
        finally:
          used_time = time.time() - start_time
          if used_time > _HANDLER_WARN_TIME_LIMIT:
            logging.warn(
                'The handler for %s takes too long to finish (%.2f seconds)! '
                'This would make the UI unresponsible for new events, '
                'consider moving the work load to background thread instead.',
                event.subtype, used_time)

  def GetUILocale(self):
    """Returns current enabled locale in UI."""
    return state.get_shared_data('ui_locale')

  def PlayAudioFile(self, audio_file):
    """Plays an audio file in the given path.

    Args:
      audio_file: The path to the audio file.
    """
    js = """
      const audioElement = new Audio(args.path);
      audioElement.addEventListener(
          "canplaythrough", () => { audioElement.play(); });
    """
    self.RunJS(js, path=os.path.join('/sounds', audio_file))

  def SetFocus(self, element_id):
    """Set focus to the element specified by element_id.

    Args:
      element_id: The HTML DOM id of the element to be focused.
    """
    self.RunJS('document.getElementById(args.id).focus()', id=element_id)

  def SetSelected(self, element_id):
    """Set the specified element as selected.

    Args:
      element_id: The HTML DOM id of the element to be selected.
    """
    self.RunJS('document.getElementById(args.id).select()', id=element_id)

  def Alert(self, text):
    """Show an alert box.

    Args:
      text: The text to show in the alert box. Can be an i18n text.
    """
    self.CallJSFunction('test.alert', text)

  def WaitKeysOnce(self, keys, timeout=None):
    """Wait for one of the keys to be pressed.

    Note that this must NOT be called in the UI thread.

    Args:
      keys: A key or an array of keys to wait for.
      timeout: Timeout for waiting the key, None for no timeout.
    Returns:
      The key that is pressed, or None if no key is pressed before timeout.
    """
    if threading.current_thread().name == _UI_THREAD_NAME:
      raise RuntimeError(
          "Can't call WaitKeysOnce in UI thread since it would deadlock.")

    if not isinstance(keys, list):
      keys = [keys]

    key_pressed = Queue.Queue()

    for key in keys:
      self.BindKey(key,
                   (lambda k: lambda unused_event: key_pressed.put(k))(key))
    try:
      return key_pressed.get(timeout=timeout)
    except Queue.Empty:
      return None
    finally:
      for key in keys:
        self.UnbindKey(key)


class DummyUI(object):
  """Dummy UI for offline test."""

  def __init__(self, test):
    self.test = test

  def Run(self):
    pass

  def Pass(self):
    logging.info('ui.Pass called. Wait for the test finishes by itself.')

  def Fail(self, msg):
    self.test.fail(msg)

  def BindKeyJS(self, _key, _js):
    logging.info('Ignore setting JS in dummy UI')

  def AddEventHandler(self, _event, _func):
    logging.info('Ignore setting Event Handler in dummy UI')


class JavaScriptTemplateProxy(object):
  """Proxy that forward all calls to JavaScript window.template."""

  def __init__(self, ui):
    self.ui = ui

  def __getattr__(self, name):
    if not name[0].isupper():
      raise AttributeError
    # Change naming convension between Python and JavaScript.
    # SetState (Python) -> setState (JavaScript).
    js_name = name[0].lower() + name[1:]
    def _Proxy(*args):
      self.ui.CallJSFunction('window.template.%s' % js_name, *args)
    setattr(self, name, _Proxy)
    return _Proxy


class TestCaseWithUI(unittest.TestCase):
  """A unittest.TestCase with UI.

  Test should override runTest to do testing in background.
  """

  template_classes = ''

  def __init__(self, methodName):
    super(TestCaseWithUI, self).__init__(methodName='_RunTestWithUI')
    self._method_name = methodName
    self.ui = None
    self.template = None

  def run(self, result=None):
    # We override TestCase.run and do initialize of ui objects here, since the
    # session.GetCurrentTestFilePath() used by UI is not set when __init__ is
    # called (It's set by invocation after the TestCase instance is created),
    # and initialize using setUp() means that all pytest inheriting this need
    # to remember calling super(..., self).setUp(), which is a lot of
    # boilerplate code and easy to forget.
    extra_attrs = ''
    if self.template_classes:
      extra_attrs = ' class="%s"' % self.template_classes
    default_html = '<test-template{extra_attrs}></test-template>'.format(
        extra_attrs=extra_attrs)
    self.ui = UI(default_html=default_html)
    self.template = JavaScriptTemplateProxy(self.ui)

    super(TestCaseWithUI, self).run(result=result)

  def _RunTestWithUI(self):
    self.ui.RunInBackground(getattr(self, self._method_name))
    self.ui.Run()
