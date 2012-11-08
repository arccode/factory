# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test external display with optional audio playback test."""

import random
import threading
import unittest
import uuid

from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory_task import FactoryTaskManager
from cros.factory.test.factory_task import InteractiveFactoryTask
from cros.factory.test.pytests import audio
from cros.factory.utils.process_utils import SpawnOutput

_TEST_TITLE = test_ui.MakeLabel('External Display Test',
                                u'外接显示屏测试')
_DIV_CENTER_INSTRUCTION = """
<div id='instruction-center' class='template-instruction'></div>"""
_CSS = '#pass_key {font-size:36px; font-weight:bold;}'

# Interval (seconds) of probing connection state.
_CONNECTION_CHECK_PERIOD_SECS = 2

# Messages for tasks
_TITLE_CONNECT_TEST = lambda d: test_ui.MakeLabel(
    '%s Connect' % d, u'%s 连接' % d)
_TITLE_VIDEO_TEST = lambda d: test_ui.MakeLabel(
    '%s Video' % d, u'%s 视讯' % d)
_TITLE_DISCONNECT_TEST = lambda d: test_ui.MakeLabel(
    '%s Disconnect' % d, u'%s 移除' % d)
_MSG_CONNECT_TEST = lambda d: test_ui.MakeLabel(
    'Connect external display: %s' % d,
    u'请接上外接显示屏: %s' % d)
_MSG_VIDEO_TEST = lambda d: test_ui.MakeLabel(
    'Do you see video on %s?' % d,
    u'外接显示屏 %s 是否有画面?' % d)
_MSG_DISCONNECT_TEST = lambda d: test_ui.MakeLabel(
    'Disconnect external display: %s' % d,
    u'移除外接显示屏: %s' % d)
_MSG_PROMPT_PASS_KEY = lambda k: test_ui.MakeLabel(
    'Press <span id="pass_key">%d</span> to pass the test.' % k,
    u'通过请按 <span id="pass_key">%d</span> 键' % k)


class ExtDisplayTask(InteractiveFactoryTask):  # pylint: disable=W0223
  """Base class of tasks for external display test.

  Args:
    args: a ExtDisplayTaskArg object.
    title: task title showed on the upper-left corner of the test area.
    instruction: task instruction showed on the center of the test area.
    pass_key: True to bind Enter key to pass the task.
  """
  def __init__(self, args, title, instruction,  # pylint: disable=W0231
               pass_key=True):
    super(ExtDisplayTask, self).__init__(args.ui)
    self._args = args
    self._ui = args.ui
    self._template = args.template
    self._title = title
    self._instruction = instruction
    self._pass_key = pass_key

  def _SetTitleInstruction(self):
    """Sets title and instruction.

    Shows task title on the upper left corner and instruction at the center
    of the test area.
    """
    self._template.SetInstruction(self._title)
    self._ui.SetHTML(
      '%s<br>%s' % (self._instruction,
                    test_ui.MakePassFailKeyLabel(pass_key=self._pass_key)),
      id='instruction-center')

  def InitUI(self, fail_later=True):
    """Initializes UI.

    Sets task title and instruction. Binds pass/fail keys.
    Should be called in the beginning of Run().

    Args:
      fail_later: True to fail later when fail key is pressed.
    """
    self._SetTitleInstruction()
    self.BindPassFailKeys(pass_key=self._pass_key, fail_later=fail_later)


class WaitDisplayThread(threading.Thread):
  """A thread to wait for display connection state.

  When expected connection state is observed, it calls on_success and stop.
  Or the calling thread can stop it using stop().
  It probes display state every _CONNECTION_CHECK_PERIOD_SECS seconds.

  Args:
    display_id: target display ID.
    connect: 'connected' / 'disconnected'
    on_success: callback for success.
  """
  def __init__(self, display_id, connect, on_success):
    threading.Thread.__init__(self, name='WaitDisplayThread')
    self._done = threading.Event()
    self._xrandr_expect = '%s %s' % (display_id, connect)
    self._on_success = on_success

  def run(self):
    while not self._done.is_set():
      if self._xrandr_expect in SpawnOutput(['xrandr', '-d', ':0']):
        self._on_success()
        self.Stop()
      else:
        self._done.wait(_CONNECTION_CHECK_PERIOD_SECS)

  def Stop(self):
    """Stops the thread.
    """
    self._done.set()


class DetectDisplayTask(ExtDisplayTask):
  """Task to wait for connecting / disconnecting a external display.

  A base class of ConnectTask and DisconnectTask.

  Args:
    args: refer base class.
    title: refer base class.
    instruction: refer base class.
    display_label: target display's human readable name.
    display_id: target display's id in xrandr.
    connect: (_CONNECT/_DISCONNECT) checks for connect/disconnect.
  """
  _CONNECT = 'connected'
  _DISCONNECT = 'disconnected'

  def __init__(self, args, title, instruction, connect):
    super(DetectDisplayTask, self).__init__(args, title, instruction,
                                            pass_key=False)
    self._wait_display = WaitDisplayThread(args.display_id, connect,
                                           self.PostSuccessEvent)
    self._pass_event = str(uuid.uuid4())  # used to bind a post event.

  def PostSuccessEvent(self):
    """Posts an event to trigger self.Pass().

    It is called by another thread. It ensures that self.Pass() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(Event(Event.Type.TEST_UI_EVENT,
                             subtype=self._pass_event))

  def Prepare(self):
    """Called before running display detection loop.
    """
    pass

  def Run(self):
    # If the display is unable to detect, it should not perform the remaining
    # tasks.
    self.InitUI(fail_later=False)
    self.Prepare()
    self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
    self._wait_display.start()

  def Cleanup(self):
    self._wait_display.Stop()


class ConnectTask(DetectDisplayTask):
  """Task to wait for a external display to connect.

  Args:
    args: refer base class.
  """
  def __init__(self, args):
    super(ConnectTask, self).__init__(
      args,
      _TITLE_CONNECT_TEST(args.display_label),
      _MSG_CONNECT_TEST(args.display_label),
      DetectDisplayTask._CONNECT)


class DisconnectTask(DetectDisplayTask):
  """Task to wait for a external display to disconnect.

  Args:
    args: refer base class.
  """
  def __init__(self, args):
    super(DisconnectTask, self).__init__(
      args,
      _TITLE_DISCONNECT_TEST(args.display_label),
      _MSG_DISCONNECT_TEST(args.display_label),
      DetectDisplayTask._DISCONNECT)

  def Prepare(self):
    self.RunCommand(
      ['xrandr', '-d', ':0', '--output', self._args.main_display_id, '--auto',
       '--output', self._args.display_id, '--off'],
      'Fail to switch back to main display %s' % self._args.main_display_id)


class VideoTask(ExtDisplayTask):
  """Task to show screen on external display only.

  The task is passed only after an operator press a random digit which
  is promoted on the external display.

  Args:
    args: refer base class.
  """
  def __init__(self, args):
    # Bind a random key (0-9) to pass the task.
    self._pass_digit = random.randint(0, 9)
    instruction = '%s<br>%s' % (
      _MSG_VIDEO_TEST(args.display_label),
      _MSG_PROMPT_PASS_KEY(self._pass_digit))

    super(VideoTask, self).__init__(args,
                                    _TITLE_VIDEO_TEST(args.display_label),
                                    instruction,
                                    pass_key=False)

  def Run(self):
    self.InitUI()
    self.BindDigitKeys(self._pass_digit)
    self.RunCommand(
      ['xrandr', '-d', ':0', '--output', self._args.main_display_id, '--off',
      '--output', self._args.display_id, '--auto'],
      'Fail to show display %s' % self._args.display_id)

  def Cleanup(self):
    self.UnbindDigitKeys()


class ExtDisplayTaskArg(object):
  """Contains args needed by ExtDisplayTask.
  """
  def __init__(self):
    self.main_display_id = None
    self.display_label = None
    self.display_id = None
    self.audio_port = None
    self.ui = None
    self.template = None

  def ParseDisplayInfo(self, info):
    """
    It parses tuple from args.display_info.

    Args:
      info: a tuple in args.display_info. Refer display_info definition.

    Raises:
      ValueError if parse error.
    """
    # Sanity check
    if (len(info) not in [2, 3] or any(not isinstance(i, str) for i in info)):
      raise ValueError('ERROR: invalid display_info item: ' + str(info))

    self.display_label, self.display_id = info[:2]
    if len(info) == 3:
      self.audio_port = info[2]


class ExtDisplayTest(unittest.TestCase):
  ARGS = [
    Arg('main_display', str, 'xrandr ID for ChromeBook\'s main display.',
        optional=False),
    Arg('display_info', list,
        ('A list of tuple: (display_label, display_id, audio_port).\n'
         'Each tuple represents an external port.\n'
         'display_label: (str) display name seen by operator, e.g. VGA.\n'
         'display_id: (str) ID used to identify display in xrandr. e.g. VGA1.\n'
         'audio_port: (str, opt) amixer port name for audio test. If set,\n'
         '    the audio playback test is added for the display.'),
        optional=False),
  ]

  def __init__(self, *args, **kwargs):
    super(ExtDisplayTest, self).__init__(*args, **kwargs)
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._task_manager = None

  def InitUI(self):
    """Initializes UI.

    Sets test title and draw progress bar.
    """
    self._template.SetTitle(_TEST_TITLE)
    self._template.SetState(_DIV_CENTER_INSTRUCTION)
    self._template.DrawProgressBar()
    self._ui.AppendCSS(_CSS)

  def ComposeTasks(self):
    """Composes test tasks acoording to display_info dargs.

    Returns:
      A list of test tasks derived from ExtDisplayTask.

    Raises:
      ValueError if args.display_info is invalid.
    """
    tasks = []
    for info in self.args.display_info:
      args = ExtDisplayTaskArg()
      args.ParseDisplayInfo(info)
      args.main_display_id = self.args.main_display
      args.ui = self._ui
      args.template = self._template
      tasks.append(ConnectTask(args))
      tasks.append(VideoTask(args))
      if args.audio_port:
        audio_label = test_ui.MakeLabel('%s Audio' % args.display_label,
                                        u' %s 音讯' % args.display_label)
        tasks.append(audio.AudioDigitPlaybackTask(
            self._ui, audio_label, args.audio_port,
            'instruction', 'instruction-center'))
      tasks.append(DisconnectTask(args))
    return tasks

  def runTest(self):
    self.InitUI()
    self._task_manager = FactoryTaskManager(
      self._ui, self.ComposeTasks(),
      update_progress=self._template.SetProgressBarValue)
    self._task_manager.Run()
