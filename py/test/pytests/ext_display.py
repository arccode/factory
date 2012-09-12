# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test external display with optional audio playback test."""

import os
import random
import threading
import unittest
import uuid

from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory_task import FactoryTask, FactoryTaskManager
from cros.factory.utils.process_utils import Spawn

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
_TITLE_AUDIO_TEST = lambda d: test_ui.MakeLabel(
  '%s Audio' % d, u'%s 音讯' % d)
_TITLE_DISCONNECT_TEST = lambda d: test_ui.MakeLabel(
  '%s Disconnect' % d, u'%s 移除' % d)
_MSG_CONNECT_TEST = lambda d: test_ui.MakeLabel(
  'Connect external display: %s' % d,
  u'请接上外接显示屏: %s' % d)
_MSG_VIDEO_TEST = lambda d: test_ui.MakeLabel(
  'Do you see video on %s?' % d,
  u'外接显示屏 %s 是否有画面?' % d)
_MSG_AUDIO_TEST = lambda d: test_ui.MakeLabel(
  'Do you hear audio from %s?' % d,
  u'外接显示屏 %s 是否有听到声音?' % d)
_MSG_DISCONNECT_TEST = lambda d: test_ui.MakeLabel(
  'Disconnect external display: %s' % d,
  u'移除外接显示屏: %s' % d)
_MSG_PROMPT_PASS_KEY = lambda k: test_ui.MakeLabel(
  'Press <span id="pass_key">%s</span> to pass the test.' % k,
  u'通過請按 <span id="pass_key">%s</span> 鍵' % k)


class ExtDisplayTask(FactoryTask):  # pylint: disable=W0223
  """Base class of tasks for external display test.

  Args:
    ui: a test_ui.UI object.
    template: a ui_templates.TwoSections object.
    title: task title showed on the upper-left corner of the test area.
    instruction: task instruction showed on the center of the test area.
    pass_key: True to bind Enter key to pass the task.
  """
  def __init__(self, ui, template, title, instruction,  # pylint: disable=W0231
               pass_key=True):
    self._ui = ui
    self._template = template
    self._title = title
    self._instruction = instruction
    self._pass_key = pass_key

  def _BindPassFailKeys(self):
    """Binds pass and/or fail keys.

    If self._pass_key is True, binds Enter key to pass the task; otherwise,
    pressing Enter triggers nothing.
    Always binds Esc key to fail the task.
    """
    if self._pass_key:
      self._ui.BindKey(test_ui.ENTER_KEY, lambda _: self.Pass())
    else:
      self._ui.BindKey(test_ui.ENTER_KEY, lambda _: None)

    self._ui.BindKey(test_ui.ESCAPE_KEY,
                     lambda _: self.Fail(
        '%s failed by operator.' % self.__class__.__name__, later=True))

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

  def InitUI(self):
    """Initializes UI.

    Sets task title and instruction. Binds pass/fail keys.
    Should be called in the beginning of Run().
    """
    self._SetTitleInstruction()
    self._BindPassFailKeys()

  def RunCommand(self, command, fail_message=None):
    """Executes a command and checks if it runs successfully.

    Args:
      command: command list.
      fail_message: optional string. If assigned and the command's return code
          is nonzero, Fail will be called with fail_message.
    """
    p = Spawn(command, call=True, ignore_stdout=True, read_stderr=True)
    if p.returncode != 0 and fail_message:
      self.Fail('%s\nerror:%s' % (fail_message, p.stderr_data))


class WaitDisplayThread(threading.Thread):
  """A thread to wait for display connection state.

  When expected connection state is observed, it calls on_success and stop.
  Or the calling thread can stop it using stop().
  It probes display state every _CONNECTION_CHECK_PERIOD_SECS seconds.

  Args:
    display_id: target display ID.
    connect: (self._CONNECT/self._DISCONNECT) checks for connect/disconnect.
    on_success: callback for success.
  """
  def __init__(self, display_id, connect, on_success):
    threading.Thread.__init__(self, name='WaitDisplayThread')
    self._done = threading.Event()
    self._display_id = display_id
    self._connect = connect
    self._on_success = on_success

  def run(self):
    expect = '%s %s' % (self._display_id, self._connect)
    while not self._done.is_set():
      if expect in Spawn(['xrandr', '-d', ':0'],
                         call=True, read_stdout=True).stdout_data:
        self._on_success()
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
    ui: refer base class.
    template: refer base class.
    title: refer base class.
    instruction: refer base class.
    display_label: target display's human readable name.
    display_id: target display's id in xrandr.
    connect: (_CONNECT/_DISCONNECT) checks for connect/disconnect.
  """
  _CONNECT = 'connected'
  _DISCONNECT = 'disconnected'

  def __init__(self, ui, template, title, instruction, display_label,
               display_id, connect):
    super(DetectDisplayTask, self).__init__(ui, template, title, instruction,
                                            pass_key=False)
    self._display_label = display_label
    self._display_id = display_id
    self._wait_display = WaitDisplayThread(display_id, connect,
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
    self.InitUI()
    self.Prepare()
    self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
    self._wait_display.start()

  def Cleanup(self):
    self._wait_display.Stop()


class ConnectTask(DetectDisplayTask):
  """Task to wait for a external display to connect.

  Args:
    ui: refer base class.
    template: refer base class.
    display_label: target display's human readable name.
    display_id: target display's id in xrandr.
  """
  def __init__(self, ui, template, display_label, display_id):
    super(ConnectTask, self).__init__(
      ui, template,
      _TITLE_CONNECT_TEST(display_label),
      _MSG_CONNECT_TEST(display_label),
      display_label, display_id, DetectDisplayTask._CONNECT)


class DisconnectTask(DetectDisplayTask):
  """Task to wait for a external display to disconnect.

  Args:
    ui: refer base class.
    template: refer base class.
    display_label: target display's human readable name.
    display_id: target display's id in xrandr.
    main_display_id: computer's main display's id in xrandr.
  """
  def __init__(self, ui, template, display_label, display_id, main_display_id):
    super(DisconnectTask, self).__init__(
      ui, template,
      _TITLE_DISCONNECT_TEST(display_label),
      _MSG_DISCONNECT_TEST(display_label),
      display_label, display_id, DetectDisplayTask._DISCONNECT)
    self._main_display_id = main_display_id

  def Prepare(self):
    self.RunCommand(
      ['xrandr', '-d', ':0', '--output', self._main_display_id, '--auto',
       '--output', self._display_id, '--off'],
      'Fail to switch back to main display %s' % self._main_display_id,)


class VideoTask(ExtDisplayTask):
  """Task to show screen on external display only.

  The task is passed only after an operator press a random digit which
  is promoted on the external display.

  Args:
    ui: refer base class.
    template: refer base class.
    display_label: target display's human readable name.
    display_id: target display's id in xrandr.
    main_display_id: computer's main display's id in xrandr.
  """
  def __init__(self, ui, template, display_label, display_id, main_display_id):
    # Bind a random key (0-9) to pass the task.
    self._pass_num = str(random.randint(0, 9))
    instruction = '%s<br>%s' % (
      _MSG_VIDEO_TEST(display_label),
      _MSG_PROMPT_PASS_KEY(self._pass_num))

    super(VideoTask, self).__init__(ui, template,
                                    _TITLE_VIDEO_TEST(display_label),
                                    instruction,
                                    pass_key=False)
    self._ext_display_only = [
      'xrandr', '-d', ':0', '--output', main_display_id, '--off',
      '--output', display_id, '--auto']
    self._msg_fail_ext = 'Fail to show display %s(%s)' % (display_label,
                                                          display_id)

  def Run(self):
    self.InitUI()
    self._ui.BindKey(self._pass_num, lambda _: self.Pass())
    self.RunCommand(self._ext_display_only, self._msg_fail_ext)


class AudioTask(ExtDisplayTask):
  """Task to play audio through external display.

  Args:
    ui: refer base class.
    template: refer base class.
    display_label: target display's human readable name.
    audio_port: target display's audio port in amixer.
    audio_sample: audio sample filename.
  """
  def __init__(self, ui, template, display_label, audio_port, audio_sample):
    super(AudioTask, self).__init__(ui, template,
                                    _TITLE_AUDIO_TEST(display_label),
                                    _MSG_AUDIO_TEST(display_label))
    self._display_label = display_label
    self._audio_port = audio_port
    self._audio_sample = audio_sample
    self._play = None

  def Run(self):
    self.InitUI()
    self.RunCommand(
      ['amixer', '-c', '0', 'cset', 'name="%s"' % self._audio_port, 'on'],
      'Fail to enable audio.')
    self._play = Spawn(['aplay', '-q', self._audio_sample])

  def Cleanup(self):
    if self._play and self._play.poll() is None:
      self._play.terminate()

    self.RunCommand(
      ['amixer', '-c', '0', 'cset', 'name="%s"' % self._audio_port, 'off'],
      'Fail to disable audio.')


class ExtDisplayTest(unittest.TestCase):
  ARGS = [
    Arg('main_display', str, 'xrandr ID for ChromeBook\'s main display.',
        optional=False),
    Arg('display_info', list,
        ('A list of tuples: [(display_label, display_id, audio_port, '
         'audio_sample),...].\n'
         'Each tuple represents an external port.\n'
         'display_label: (str) display name seen by operator, e.g. VGA.\n'
         'display_id: (str) ID used to identify display in xrandr. e.g. VGA1.\n'
         'audio_port: (str, opt) amixer port name for audio test.\n'
         'audio_sample: (str, opt) path to an audio sample file.\n'
         'Note that audio_port and audio_sample must be set together to\n'
         'enable audio playback test.'),
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
    def _ParseDisplayInfo(info):
      """Parses tuple inside args.display_info.

      Args:
        info: a tuple in args.display_info. Refer display_info definition.

      Returns:
        (display_label, display_id, audio_port, audio_sample)
        audio_port and audio_sample could be None.
      """
      num_args = len(info)
      if (num_args not in set([2, 4]) or
          any([type(args) is not str for args in info])):
        raise ValueError('ERROR: invalid display_info item: ' + str(info))
      display_label, display_id = info[:2]
      if num_args == 4:
        audio_port, audio_sample = info[2:4]
        if not os.path.isfile(audio_sample):
          raise ValueError('ERROR: Cannot find audio sample file: ' +
                           audio_sample)
        return (display_label, display_id, audio_port, audio_sample)
      else:
        return (display_label, display_id, None, None)

    tasks = []
    ui = self._ui
    template = self._template
    main_display_id = self.args.main_display
    for info in self.args.display_info:
      display_label, display_id, audio_port, audio_sample = _ParseDisplayInfo(
        info)
      tasks.append(ConnectTask(ui, template, display_label, display_id))
      tasks.append(VideoTask(ui, template, display_label, display_id,
                             main_display_id))
      if audio_sample:
        tasks.append(AudioTask(ui, template, display_label, audio_port,
                               audio_sample))
      tasks.append(DisconnectTask(ui, template, display_label, display_id,
                                  main_display_id))
    return tasks

  def runTest(self):
    self.InitUI()
    self._task_manager = FactoryTaskManager(
      self._ui, self.ComposeTasks(),
      update_progress=self._template.SetProgressBarValue)
    self._task_manager.Run()
