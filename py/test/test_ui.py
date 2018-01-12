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
from cros.factory.test.i18n import _
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


PASS_KEY_LABEL = _('Press Enter to pass.')
FAIL_KEY_LABEL = _('Press ESC to fail.')
PASS_FAIL_KEY_LABEL = [PASS_KEY_LABEL, FAIL_KEY_LABEL]

_HANDLER_WARN_TIME_LIMIT = 5
_EVENT_LOOP_THREAD_NAME = 'TestEventLoopThread'


class EventLoop(object):
  """Event loop for test."""

  def __init__(self, handler_exception_hook, event_client_class=None):
    self.test = session.GetCurrentTestPath()
    self.invocation = session.GetCurrentTestInvocation()
    self.event_client = (event_client_class or test_event.BlockingEventClient)(
        callback=self._HandleEvent)
    self.event_handlers = {}
    self._handler_exception_hook = handler_exception_hook
    self._timed_handler_event_queue = Queue.PriorityQueue()

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
    if not self.event_client.is_closed():
      event.test = self.test
      event.invocation = self.invocation
      self.event_client.post_event(event)

  def PostNewEvent(self, event_type, *args, **kwargs):
    """Constructs an event from given type and parameters, and post it."""
    return self.PostEvent(test_event.Event(event_type, *args, **kwargs))

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
    self.event_handlers.clear()
    type_utils.DrainQueue(self._timed_handler_event_queue)

  def CatchException(self, func):
    """Wraps function and pass exceptions to _handler_exception_hook.

    This makes the function works like it's in the main thread event handler.
    """
    @functools.wraps(func)
    def _Wrapper(*args, **kwargs):
      try:
        return func(*args, **kwargs)
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
            getattr(event, 'invocation', '') == self.invocation and
            getattr(event, 'type', '') == test_event.Event.Type.TEST_UI_EVENT):
      return

    for handler in self.event_handlers.get(event.subtype, []):
      try:
        self._RunHandler(handler, event)
      except Exception:
        self._handler_exception_hook()


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


def EnsureI18n(labels):
  """Pass all translation dict to i18n_test_ui.MakeI18nLabel and join them."""
  if not isinstance(labels, list):
    labels = [labels]
  else:
    labels = type_utils.FlattenList(labels)
  return ''.join(
      i18n_test_ui.MakeI18nLabel(label) if isinstance(label, dict) else label
      for label in labels)


class UI(object):
  """Web UI for a factory test."""

  default_html = ''

  def __init__(self, event_loop):
    self._event_loop = event_loop
    self._static_dir_path = None

  def SetupStaticFiles(self):
    # Get path to current test and register static files/directories.
    test = session.GetCurrentTestPath()
    py_script = session.GetCurrentTestFilePath()
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
    # This should be the only place that calls SetHTML(..., id=None).
    self.SetHTML(GetAutoload('html', self.default_html), id=None)

    js = GetAutoload('js')
    if js:
      self.RunJS(js)

    # TODO(pihsun): Change to insert a css link instead.
    css = GetAutoload('css')
    if css:
      self.AppendCSS(css)

  def SetHTML(self, html, id, append=False, autoscroll=False):
    """Sets a HTML snippet to the UI in the test pane.

    Note that <script> tags are not allowed in SetHTML() and
    AppendHTML(), since the scripts will not be executed. Use RunJS()
    or CallJSFunction() instead.

    Args:
      html: The HTML snippet to set.
      id: Writes html to the element identified by id.
      append: Whether to append the HTML snippet.
      autoscroll: If True and the element scroll were at bottom before SetHTML,
          scroll the element to bottom after SetHTML.
    """
    # pylint: disable=redefined-builtin
    self._event_loop.PostNewEvent(
        test_event.Event.Type.SET_HTML,
        html=EnsureI18n(html),
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
    RunJS('test.alert(args.arg_0)', arg_0='123'), and the 'this' when the
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
    self._event_loop.AddEventHandler(uuid_str, handler)
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

  def ToggleClass(self, element_id, dom_class, force=None):
    """Toggle an element class by classList.toggle().

    Args:
      element_id: The HTML DOM id of the element to be shown.
      dom_class: The DOM class to be toggled.
      force: Should be None, True or False. If None, toggle the class. If True,
          add the class, else remove the class.
    """
    if force is None:
      self.RunJS(
          'document.getElementById(args.id).classList.toggle(args.dom_class)',
          id=element_id,
          dom_class=dom_class)
    else:
      self.RunJS(
          'document.getElementById(args.id).classList.toggle(args.dom_class, '
          'args.force)',
          id=element_id,
          dom_class=dom_class,
          force=force)

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
      return sync_utils.QueueGet(key_pressed, timeout=timeout)
    except Queue.Empty:
      return None
    finally:
      for key in keys:
        self.UnbindKey(key)


class StandardUI(UI):
  """Standard Web UI that have a template.

  This is the default UI used by TestCaseWithUI.
  """

  default_html = '<test-template></test-template>'

  def __init__(self, event_loop=None):
    super(StandardUI, self).__init__(event_loop=event_loop)
    self.ImportHTML('/templates.html')

  def SetTitle(self, html):
    """Sets the title of the test UI.

    Args:
      html: The html content to write.
    """
    self.CallJSFunction('window.template.setTitle', EnsureI18n(html))

  def SetState(self, html, append=False):
    """Sets the state section in the test UI.

    Args:
      html: The html to write.
      append: Append html at the end.
    """
    self.CallJSFunction('window.template.setState', EnsureI18n(html), append)

  def SetInstruction(self, html):
    """Sets the instruction to operator.

    Args:
      html: The html content to write.
    """
    self.CallJSFunction('window.template.setInstruction', EnsureI18n(html))

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

  def SetTimerValue(self, value):
    """Set the remaining time of timer.

    Would show the timer if it's not already shown.

    Args:
      value: Remaining time.
    """
    self.CallJSFunction('window.template.setTimerValue', value)

  def HideTimer(self):
    """Hide the timer."""
    self.CallJSFunction('window.template.hideTimer')

  def SetView(self, view):
    """Set the view of the template.

    Args:
      view: The id of the view.
    """
    self.CallJSFunction('window.template.setView', view)

  def StartCountdownTimer(self, timeout_secs, timeout_handler=None):
    """Start a countdown timer.

    It updates UI for time remaining and calls timeout_handler when timeout.
    All works are done in the event loop, and no extra threads are created.

    Args:
      timeout_secs: Number of seconds to timeout.
      timeout_handler: Callback called when timeout reaches.

    Returns:
      A threading.Event that would stop the countdown timer when set.
    """
    end_time = time.time() + timeout_secs
    stop_event = threading.Event()
    def _Timer():
      while not stop_event.is_set():
        time_remaining = end_time - time.time()
        if time_remaining <= 0:
          if timeout_handler:
            timeout_handler()
          break
        self.SetTimerValue(time_remaining)
        yield
      self.HideTimer()
    self._event_loop.AddTimedIterable(_Timer(), 1)
    return stop_event

  def StartFailingCountdownTimer(self, timeout_secs, error_msg=None):
    """Start a countdown timer that fail the task after timeout.

    Args:
      timeout_secs: Number of seconds to timeout.
      error_msg: Error message to fail the test when timeout.

    Returns:
      A threading.Event that would stop the countdown timer when set.
    """
    if error_msg is None:
      error_msg = 'Timed out after %d seconds.' % timeout_secs

    def _TimeoutHandler():
      raise type_utils.TestFailure(error_msg)

    return self.StartCountdownTimer(timeout_secs, _TimeoutHandler)


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


_Task = collections.namedtuple('Task', ['name', 'run'])


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

  def __WaitTaskEnd(self, timeout):
    if self.__task_end_event.wait(timeout=timeout):
      raise TaskEndException

  def WaitTaskEnd(self):
    """Wait for either TaskPass or TaskFail is called.

    Task that need to wait for frontend events to judge pass / fail should call
    this at the end of the task.
    """
    self.__WaitTaskEnd(None)

  def Sleep(self, secs):
    """Sleep for secs seconds, but ends early if test failed.

    An exception would be raised if TaskPass or TaskFail is called before
    timeout. This makes the function acts like time.sleep that ends early when
    timeout is given.

    Args:
      secs: Seconds to sleep.

    Raises:
      TaskEndException if the task end before secs seconds.
    """
    self.__WaitTaskEnd(secs)

  def AddTask(self, task, *task_args, **task_kwargs):
    """Add a task to the test.

    Extra arguments would be passed to the task function.

    Args:
      task: A task function.
      task_args, task_kwargs: Arguments for the task function.
    """
    name = task.__name__
    run = lambda: task(*task_args, **task_kwargs)

    self.__tasks.append(_Task(name=name, run=run))


  def run(self, result=None):
    # We override TestCase.run and do initialize of ui objects here, since the
    # session.GetCurrentTestFilePath() used by UI is not set when __init__ is
    # called (It's set by invocation after the TestCase instance is created),
    # and initialize using setUp() means that all pytests inheriting this need
    # to remember calling super(..., self).setUp(), which is a lot of
    # boilerplate code and easy to forget.
    self.event_loop = EventLoop(self.__HandleException)
    self.ui = self.ui_class(event_loop=self.event_loop)
    self.ui.SetupStaticFiles()

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
    # Set the sleep function for various polling methods in sync_utils to
    # self.WaitTaskEnd, so tests using methods like sync_utils.WaitFor would
    # still be ended early when the test ends.
    with sync_utils.WithPollingSleepFunction(self.Sleep):
      # Add runTest as the only task if there's none.
      if not self.__tasks:
        self.AddTask(getattr(self, self.__method_name))

      for task in self.__tasks:
        self.__task_end_event.clear()
        try:
          self.__SetupGoofyJSEvents()
          try:
            task.run()
          finally:
            self.__task_end_event.set()
            self.event_loop.ClearHandlers()
            self.ui.UnbindAllKeys()
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

  def __SetupGoofyJSEvents(self):
    """Setup handlers for events from frontend JavaScript."""
    def handler(event):
      status = event.data.get('status')
      if status == state.TestState.PASSED:
        self.PassTask()
      elif status == state.TestState.FAILED:
        self.FailTask(event.data.get('error_msg', ''))
      else:
        raise ValueError('Unexpected status in event %r' % event)
    self.event_loop.AddEventHandler('goofy_ui_task_end', handler)
