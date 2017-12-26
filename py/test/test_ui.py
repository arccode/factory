# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for creating and interacting with factory test UI."""

from __future__ import print_function

import cgi
import collections
import functools
import json
import logging
import os
import Queue
import subprocess
import sys
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
from cros.factory.utils import sync_utils
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

_HANDLER_WARN_TIME_LIMIT = 5
_EVENT_LOOP_THREAD_NAME = 'TestEventLoopThread'


class BaseEventLoop(object):
  """Base event loop."""

  def __init__(self):
    self.test = session.GetCurrentTestPath()
    self.invocation = session.GetCurrentTestInvocation()
    self.event_client = test_event.BlockingEventClient(
        callback=self._HandleEvent)
    self.event_handlers = {}

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

  def PostNewEvent(self, event_type, *args, **kwargs):
    """Constructs an event from given type and parameters, and post it."""
    return self.PostEvent(test_event.Event(event_type, *args, **kwargs))

  def _HandleEvent(self, event):
    del event  # Unused.
    raise NotImplementedError()

  def ClearHandlers(self):
    """Clear all event handlers."""
    self.event_handlers.clear()


class EventLoop(BaseEventLoop):
  """Old event loop for UI."""

  def __init__(self):
    super(EventLoop, self).__init__()
    self.task_hook = None
    self.error_msgs = []

  def Run(self, on_finish=None):
    """Runs the test event loop, waiting until the test completes.

    Args:
      on_finish: Callback function when event loop ends. This can be used to
          notify the test for necessary clean-up (e.g. terminate an event loop.)
    """
    threading.current_thread().name = _EVENT_LOOP_THREAD_NAME

    def _IsEndEvent(event):
      return (event.type in [
          test_event.Event.Type.END_TEST, test_event.Event.Type.END_EVENT_LOOP
      ] and event.invocation == self.invocation and event.test == self.test)

    event = self.event_client.wait(_IsEndEvent)
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

  def Pass(self):
    """Passes the test."""
    self.PostNewEvent(
        test_event.Event.Type.END_TEST, status=state.TestState.PASSED)

  def Fail(self, error_msg):
    """Fails the test immediately."""
    self.PostNewEvent(
        test_event.Event.Type.END_TEST,
        status=state.TestState.FAILED,
        error_msg=error_msg)

  def FailLater(self, error_msg):
    """Appends a error message to the error message list.

    This would cause the test to fail when Run() finished.
    """
    self.error_msgs.append(error_msg)


class JavaScriptProxy(object):
  """Proxy that forward all calls to JavaScript object on window."""

  def __init__(self, ui, var_name):
    self._ui = ui
    self._var_name = var_name

  def __getattr__(self, name):
    if not name[0].isupper():
      raise AttributeError
    # Change naming convension between Python and JavaScript.
    # SetState (Python) -> setState (JavaScript).
    js_name = name[0].lower() + name[1:]
    def _Proxy(*args):
      self._ui.CallJSFunction('window.%s.%s' % (self._var_name, js_name), *args)
    setattr(self, name, _Proxy)
    return _Proxy


class UI(object):
  """Web UI for a factory test."""

  default_html = ''

  def __init__(self,
               event_loop=None,
               css=None,
               setup_static_files=True):
    self._event_loop = event_loop or EventLoop()
    self._static_dir_path = None

    if setup_static_files:
      self._SetupStaticFiles(session.GetCurrentTestFilePath())
      if css:
        self.AppendCSS(css)

  def _SetupStaticFiles(self, py_script):
    # Get path to caller and register static files/directories.
    base = os.path.splitext(py_script)[0]
    test = session.GetCurrentTestPath()

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
      self._static_dir_path = static_dirs[0]
      goofy_proxy.get_rpc_proxy(url=goofy_proxy.GOOFY_SERVER_URL).RegisterPath(
          '/tests/%s' % test, self._static_dir_path)
      autoload_bases.append(
          os.path.join(self._static_dir_path, os.path.basename(base)))

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
          '/tests/%s/%s' % (test, os.path.basename(autoload_path)),
          autoload_path)
      return file_utils.ReadFile(autoload_path).decode('UTF-8')

    self.SetHTML(
        html='<base href="/tests/%s/">' % test, id='head', append=True)

    # default CSS files are set in default_test_ui.html by goofy.py, and we
    # only set the HTML of body here.
    self.SetHTML(GetAutoload('html', self.default_html))

    js = GetAutoload('js')
    if js:
      self.RunJS(js)

    # TODO(pihsun): Change to insert a css link instead.
    css = GetAutoload('css')
    if css:
      self.AppendCSS(css)

  def SetHTML(self, html, append=False, id=None, autoscroll=False):
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
      autoscroll: If True and the element scroll were at bottom before SetHTML,
          scroll the element to bottom after SetHTML.
    """
    # pylint: disable=redefined-builtin
    self._event_loop.PostNewEvent(
        test_event.Event.Type.SET_HTML,
        html=html,
        append=append,
        id=id,
        autoscroll=autoscroll)

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
    self._event_loop.PostNewEvent(
        test_event.Event.Type.RUN_JS, js=js, args=kwargs)

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

  def InitJSTestObject(self, class_name, *args):
    """Initialize a JavaScript test object in frontend.

    The JavaScript object would be at window.testObject.

    Args:
      class_name: The class name of the JavaScript test object.
      args: Argument passed to the class constructor.

    Returns:
      A JavaScriptProxy to the frontend test object.
    """
    self.RunJS(
        'window.testObject = new %s(...args.constructorArg)' % class_name,
        constructorArg=args)
    return JavaScriptProxy(self, 'testObject')

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
    return self._static_dir_path

  def RunInBackground(self, target):
    """Run a function in background daemon thread.

    Pass the test if the function ends without exception, and fails the test if
    there's any exception raised.
    """
    def _target():
      try:
        target()
        self.Pass()
      except Exception:
        self.Fail(traceback.format_exc())
    process_utils.StartDaemonThread(target=_target)

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

  def HideElement(self, element_id):
    """Hide an element by setting display: none.

    Args:
      element_id: The HTML DOM id of the element to be hidden.
    """
    self.RunJS(
        'document.getElementById(args.id).style.display = "none"',
        id=element_id)

  def ShowElement(self, element_id):
    """Show an element by setting display: initial.

    Args:
      element_id: The HTML DOM id of the element to be shown.
    """
    self.RunJS(
        'document.getElementById(args.id).style.display = "initial"',
        id=element_id)

  def ImportHTML(self, url):
    """Import a HTML to the test pane.

    All other SetHTML / RunJS call would be scheduled after the import is done.
    """
    self._event_loop.PostNewEvent(
        test_event.Event.Type.IMPORT_HTML, url=url)

  def WaitKeysOnce(self, keys, timeout=None):
    """Wait for one of the keys to be pressed.

    Note that this must NOT be called in the UI thread.

    Args:
      keys: A key or an array of keys to wait for.
      timeout: Timeout for waiting the key, None for no timeout.
    Returns:
      The key that is pressed, or None if no key is pressed before timeout.
    """
    if threading.current_thread().name == _EVENT_LOOP_THREAD_NAME:
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

  # Methods below are proxy methods to event_loop for backward compatibility.

  def AddEventHandler(self, subtype, handler):
    """Adds an event handler.

    Args:
      subtype: The test-specific type of event to be handled.
      handler: The handler to invoke with a single argument (the event object).
    """
    return self._event_loop.AddEventHandler(subtype, handler)

  def PostEvent(self, event):
    """Posts an event to the event queue.

    Adds the test and invocation properties.

    Tests should use this instead of invoking post_event directly.
    """
    return self._event_loop.PostEvent(event)

  def Run(self, on_finish=None):
    """Runs the test event loop, waiting until the test completes.

    Args:
      on_finish: Callback function when event loop ends. This can be used to
          notify the test for necessary clean-up (e.g. terminate an event loop.)
    """
    return self._event_loop.Run(on_finish=on_finish)

  def Pass(self):
    """Passes the test."""
    return self._event_loop.Pass()

  def Fail(self, error_msg):
    """Fails the test immediately."""
    return self._event_loop.Fail(error_msg)

  def FailLater(self, error_msg):
    """Appends a error message to the error message list.

    This would cause the test to fail when Run() finished.
    """
    return self._event_loop.FailLater(error_msg)


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


class StandardUI(UI):
  """Standard Web UI that have a template.

  This is the default UI used by TestCaseWithUI.
  """

  default_html = '<test-template></test-template>'

  def __init__(self, event_loop=None):
    super(StandardUI, self).__init__(
        event_loop=event_loop, setup_static_files=False)
    self.ImportHTML('/templates.html')
    self._SetupStaticFiles(session.GetCurrentTestFilePath())

  def SetTitle(self, html):
    """Sets the title of the test UI.

    Args:
      html: The html content to write.
    """
    self.CallJSFunction('window.template.setTitle', html)

  def SetState(self, html, append=False):
    """Sets the state section in the test UI.

    Args:
      html: The html to write.
      append: Append html at the end.
    """
    self.CallJSFunction('window.template.setState', html, append)

  def SetInstruction(self, html):
    """Sets the instruction to operator.

    Args:
      html: The html content to write.
    """
    self.CallJSFunction('window.template.setInstruction', html)

  def DrawProgressBar(self, num_items=1):
    """Draw the progress bar and set it visible on the Chrome test UI.

    Args:
      num_items: Total number of items for the progress bar. Default to 1 so
          SetProgress can be used to set fraction done.
    """
    self.CallJSFunction('window.template.drawProgressBar', num_items)

  def AdvanceProgress(self):
    """Advance the progress bar."""
    self.CallJSFunction('window.template.advanceProgress')

  def SetProgress(self, value):
    """Set the number of completed items of progress bar.

    Args:
      value: Number of completed items, can be floating point.
    """
    self.CallJSFunction('window.template.setProgress', value)


class ScrollableLogUI(StandardUI):

  default_html = """
  <style>
    #container {
      flex: 1;
      width: 80%;
      display: flex;
      border: 1px solid gray;
    }
    #ui-log {
      flex: 1;
      overflow: auto;
      padding: 1em;
      font-family: monospace;
    }
  </style>
  <test-template>
    <div id="container">
      <pre id="ui-log"></pre>
    </div>
  </test-template>
  """

  def AppendLog(self, line):
    """Append a line of log to the UI.

    line: The log to be append.
    """
    self.AppendHTML(Escape(line), id='ui-log', autoscroll=True)

  def ClearLog(self):
    """Clear the log in UI."""
    self.SetHTML('', id='ui-log')

  def PipeProcessOutputToUI(self, cmd, callback=None):
    """Run a process and pipe its stdout and stderr to the UI.

    Args:
      cmd: The command line to be run. Would be passed as the first argument to
          Spawn.
      callback: Callback to be executed on each output line. The argument to
          the callback would be the line received.

    Returns:
      The return code of the process.
    """
    def _Callback(line):
      logging.info(line)
      if callback:
        callback(line)
      self.AppendLog(line + '\n')

    process = process_utils.Spawn(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, log=True)
    process_utils.PipeStdoutLines(process, _Callback)
    return process.returncode


class TaskEndException(Exception):
  """The exception to end a task."""
  pass


_EVENT_LOOP_PROBE_INTERVAL = 0.1
_TimedHandlerEvent = collections.namedtuple(
    '_TimedHandlerEvent', ['next_time', 'handler', 'interval'])


class NewEventLoop(BaseEventLoop):
  """The new implementation of UI event loop.

  TODO(pihsun): Remove EventLoop / BaseEventLoop and rename this to EventLoop
  when all pytests had migrated to TestCaseWithUI.
  """

  def __init__(self, handler_exception_hook):
    super(NewEventLoop, self).__init__()
    self._handler_exception_hook = handler_exception_hook
    self._timed_handler_event_queue = Queue.PriorityQueue()

  def Run(self):
    """Runs the test event loop, waiting until the test completes."""
    threading.current_thread().name = _EVENT_LOOP_THREAD_NAME

    end_event = None

    while end_event is None:
      # Give a minimum timeout that we should recheck the timed handler event
      # queue, in case some other threads register timed handler when we're
      # waiting for an event.
      timeout = _EVENT_LOOP_PROBE_INTERVAL

      # Run all expired timed handler.
      while True:
        try:
          timed_handler_event = self._timed_handler_event_queue.get_nowait()
        except Queue.Empty:
          break

        current_time = time.time()
        if timed_handler_event.next_time <= current_time:
          stop_iteration = False

          try:
            self._RunHandler(timed_handler_event.handler)
          except StopIteration:
            stop_iteration = True
          except Exception:
            self._handler_exception_hook()

          if not stop_iteration and timed_handler_event.interval is not None:
            self._timed_handler_event_queue.put(
                _TimedHandlerEvent(
                    next_time=time.time() + timed_handler_event.interval,
                    handler=timed_handler_event.handler,
                    interval=timed_handler_event.interval))
        else:
          timeout = min(timeout, timed_handler_event.next_time - current_time)
          self._timed_handler_event_queue.put(timed_handler_event)
          break

      # Process all events and wait for end event.
      end_event = self.event_client.wait(
          lambda event:
          (event.type == test_event.Event.Type.END_EVENT_LOOP and
           event.invocation == self.invocation and
           event.test == self.test),
          timeout=timeout)

    logging.info('Received end test event %r', end_event)
    self.event_client.close()

    if end_event.status == state.TestState.PASSED:
      pass
    elif end_event.status == state.TestState.FAILED:
      error_msg = getattr(end_event, 'error_msg', '')
      raise type_utils.TestFailure(error_msg)
    else:
      raise ValueError('Unexpected status in event %r' % end_event)

  def AddTimedHandler(self, handler, time_sec, repeat=False):
    """Add a handler to run in the event loop after time_sec seconds.

    This is similar to JavaScript setTimeout (or setInterval when repeat=True,
    except that the handler would be called once now).

    Args:
      handler: The handler to be called, would be run in the event loop thread.
      time_sec: Seconds before the handler would be called.
      repeat: If True, would call handler once now, and repeatly in interval
          time_sec.
    """
    self._timed_handler_event_queue.put(
        _TimedHandlerEvent(
            next_time=time.time() + (0 if repeat else time_sec),
            handler=handler,
            interval=time_sec if repeat else None))

  def AddTimedIterable(self, iterable, time_sec):
    """Add a iterable that would be consumed at interval time_sec.

    Args:
      iterable: The iterable for which next(iterable) would be called.
      time_sec: The interval between next calls in seconds.
    """
    self.AddTimedHandler(lambda: next(iterable), time_sec, repeat=True)

  def ClearHandlers(self):
    """Clear all event handlers."""
    super(NewEventLoop, self).ClearHandlers()
    type_utils.DrainQueue(self._timed_handler_event_queue)

  def CatchException(self, func):
    """Wraps function and pass exceptions to _handler_exception_hook.

    This makes the function works like it's in the main thread event handler.
    """
    @functools.wraps(func)
    def _Wrapper(*args, **kwargs):
      try:
        func(*args, **kwargs)
      except Exception:
        self._handler_exception_hook()

    return _Wrapper

  def _RunHandler(self, handler, *args):
    start_time = time.time()
    try:
      handler(*args)
    finally:
      used_time = time.time() - start_time
      if used_time > _HANDLER_WARN_TIME_LIMIT:
        logging.warn(
            'The handler (%r, args=%r) takes too long to finish (%.2f secs)! '
            'This would make the UI unresponsible for new events, '
            'consider moving the work load to background thread instead.',
            handler, args, used_time)

  def _HandleEvent(self, event):
    """Handles an event sent by a test UI."""
    if not (getattr(event, 'test', '') == self.test and
            getattr(event, 'invocation', '') == self.invocation):
      return

    if event.type == test_event.Event.Type.END_TEST:
      # This is the old event send from JavaScript test.pass / test.fail.
      # Transform them to the new task end event.
      # TODO(pihsun): Remove this after EventLoop is deprecated.
      try:
        if event.status == state.TestState.PASSED:
          raise TaskEndException()
        elif event.status == state.TestState.FAILED:
          error_msg = getattr(event, 'error_msg', '')
          raise type_utils.TestFailure(error_msg)
        else:
          raise ValueError('Unexpected status in event %r' % event)
      except Exception:
        self._handler_exception_hook()

    elif event.type == test_event.Event.Type.TEST_UI_EVENT:
      for handler in self.event_handlers.get(event.subtype, []):
        try:
          self._RunHandler(handler, event)
        except Exception:
          self._handler_exception_hook()


_Task = collections.namedtuple('Task', ['name', 'run', 'cleanup'])


class TestCaseWithUI(unittest.TestCase):
  """A unittest.TestCase with UI.

  Test should override runTest to do testing in background.
  """

  ui_class = StandardUI

  def __init__(self, methodName='runTest'):
    super(TestCaseWithUI, self).__init__(methodName='_RunTest')
    self.event_loop = None
    self.ui = None

    self.__method_name = methodName
    self.__task_end_event = threading.Event()
    self.__task_failed = False
    self.__tasks = []

  def PassTask(self):
    """Pass current task.

    Should only be called in the event callbacks or primary background test
    thread.
    """
    raise TaskEndException()

  def FailTask(self, msg):
    """Fail current task.

    Should only be called in the event callbacks or primary background test
    thread.
    """
    raise type_utils.TestFailure(msg)

  def WaitTaskEnd(self, timeout=None):
    """Wait for either TaskPass or TaskFail is called.

    Task that need to wait for frontend events to judge pass / fail should call
    this at the end of the task.

    An exception would be raised if TaskPass or TaskFail is called before
    timeout. This makes the function acts like time.sleep that ends early when
    timeout is given.

    Args:
      timeout: The timeout for waiting the task end, None for no timeout.

    Raises:
      TaskEndException if the task end before timeout.
    """
    if self.__task_end_event.wait(timeout=timeout):
      raise TaskEndException

  def AddTask(self, task, cleanup=None):
    """Add a task to the test.

    The task passed in can either be a TestTask object, or two functions task
    and cleanup.

    Args:
      task: A task function or a TestTask object to be run.
      cleanup: A cleanup function to be run after task is completed. Should be
          None if task is a TestTask object.
    """
    if callable(task):
      name = task.__name__
      run = task
    else:
      # Passing a task object, transforming into _Task.
      # We should ideally do isinstance(task, test_task.TestTask), but it'll
      # create circular imports.
      # TODO(pihsun): Clean this up after codes are reorganized.
      if not (hasattr(task, 'Run') and hasattr(task, 'Cleanup')):
        raise ValueError('Unknown type for task: %s' % type(task))

      if cleanup is not None:
        raise ValueError('cleanup should be None when passing a task object.')

      name = task.__class__.__name__
      run = task.Run
      cleanup = task.Cleanup

    self.__tasks.append(_Task(name=name, run=run, cleanup=cleanup))


  def run(self, result=None):
    # We override TestCase.run and do initialize of ui objects here, since the
    # session.GetCurrentTestFilePath() used by UI is not set when __init__ is
    # called (It's set by invocation after the TestCase instance is created),
    # and initialize using setUp() means that all pytests inheriting this need
    # to remember calling super(..., self).setUp(), which is a lot of
    # boilerplate code and easy to forget.
    self.event_loop = NewEventLoop(self.__HandleException)
    self.ui = self.ui_class(event_loop=self.event_loop)

    super(TestCaseWithUI, self).run(result=result)

  def _RunTest(self):
    """The main test procedure that would be run by unittest."""
    thread = process_utils.StartDaemonThread(target=self.__RunTasks)
    try:
      self.event_loop.Run()
    finally:
      # Ideally, the background would be the one calling FailTask / PassTask,
      # or would be waiting in WaitTaskEnd when an exception is thrown, so the
      # thread should exit cleanly shortly after the event loop ends.
      #
      # If after 1 second, the thread is alive, most likely that the thread is
      # in some blocking operation and someone else fails the test, then we
      # assume that we don't care about the thread not cleanly stopped.
      #
      # In this case, we try to raise an exception in the thread (To possibly
      # trigger some cleanup process in finally block or context manager),
      # wait for 3 more seconds for (possible) cleanup to run, and just ignore
      # the thread. (Even if the thread doesn't terminate in time.)
      thread.join(1)
      if thread.isAlive():
        try:
          sync_utils.TryRaiseExceptionInThread(thread.ident, TaskEndException)
        except ValueError:
          # The thread is no longer valid, ignore it
          pass
        else:
          thread.join(3)

  def __RunTasks(self):
    """Run the tasks in background daemon thread."""
    # Add runTest as the only task if there's none.
    if not self.__tasks:
      self.AddTask(getattr(self, self.__method_name))

    for task in self.__tasks:
      self.__task_end_event.clear()
      try:
        try:
          task.run()
        finally:
          self.event_loop.ClearHandlers()
          self.ui.UnbindAllKeys()
          if task.cleanup:
            task.cleanup()
      except Exception:
        self.__HandleException()
        if self.__task_failed:
          return

    self.event_loop.PostNewEvent(
        test_event.Event.Type.END_EVENT_LOOP, status=state.TestState.PASSED)

  def __HandleException(self):
    """Handle exception in event handlers or tasks.

    This should be called in the except clause, and is also called by the event
    loop in the main thread.
    """
    exception = sys.exc_info()[1]
    assert exception is not None, 'Not handling an exception'

    if not isinstance(exception, TaskEndException):
      error_msg = traceback.format_exc()
      self.event_loop.PostNewEvent(
          test_event.Event.Type.END_EVENT_LOOP,
          status=state.TestState.FAILED,
          error_msg=error_msg)
      self.__task_failed = True
    self.__task_end_event.set()
