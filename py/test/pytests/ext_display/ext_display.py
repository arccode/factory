# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test external display with optional audio playback test."""

import logging
import os
import random
import re
import threading
import time
import unittest
import uuid

from cros.factory.test import audio_utils
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test import utils
from cros.factory.test.args import Arg
from cros.factory.test.event import Event
from cros.factory.test.factory_task import (FactoryTaskManager,
                                            InteractiveFactoryTask)
from cros.factory.test.fixture.bft_fixture import (BFTFixture,
                                                   BFTFixtureException,
                                                   CreateBFTFixture,
                                                   TEST_ARG_HELP)
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
_MSG_FIXTURE_VIDEO_TEST = lambda d: test_ui.MakeLabel(
    'Fixture is checking if video is displayed on %s?' % d,
    u'治具正在測試外接显示屏 %s 是否有画面?' % d)
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
  Or the calling thread can stop it using Stop().
  It probes display state every _CONNECTION_CHECK_PERIOD_SECS seconds.

  Args:
    display_id: target display ID.
    connect: DetectDisplayTask.CONNECT or DetectDisplayTask.DISCONNECT
    on_success: callback for success.
  """
  def __init__(self, display_id, connect, on_success):
    threading.Thread.__init__(self, name='WaitDisplayThread')
    self._done = threading.Event()
    self._connect = connect == DetectDisplayTask.CONNECT
    self._xrandr_expect = re.compile(
        '^%s %s' % (display_id,
                    'connected' if self._connect else 'disconnected'),
        re.MULTILINE)
    self._on_success = on_success

  def run(self):
    while not self._done.is_set():
      # First checks the xrandr output pattern matches the expected status
      # of the specified external display.
      if self._xrandr_expect.search(SpawnOutput(['xrandr', '-d', ':0'])):
        display_info = factory.get_state_instance().GetDisplayInfo()
        # In the case of connecting an external display, make sure there
        # is an item in display_info with 'isInternal' False.
        # On the other hand, in the case of disconnecting an external display,
        # we can not check display info has no display with 'isInternal' False
        # because any display for chromebox has 'isInternal' False.
        if ((self._connect and
             any([x['isInternal'] == False for x in display_info])) or
            not self._connect):
          logging.info('Get display info %r', display_info)
          self._on_success()
          self.Stop()

      self._done.wait(_CONNECTION_CHECK_PERIOD_SECS)

  def Stop(self):
    """Stops the thread."""
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
    connect: (CONNECT/DISCONNECT) checks for connect/disconnect.
  """
  CONNECT = 'connected'
  DISCONNECT = 'disconnected'

  def __init__(self, args, title, instruction, connect):
    super(DetectDisplayTask, self).__init__(args, title, instruction,
                                            pass_key=False)
    self._wait_display = WaitDisplayThread(args.display_id, connect,
                                           self.PostSuccessEvent)
    self._pass_event = str(uuid.uuid4())  # used to bind a post event.
    self._fixture = args.fixture
    self._connect = connect == self.CONNECT

    # Whether or not to send a BFT command.
    self._bft_command = self._fixture is not None
    if self._connect and args.already_connect:
      self._bft_command = False

  def PostSuccessEvent(self):
    """Posts an event to trigger self.Pass().

    It is called by another thread. It ensures that self.Pass() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(Event(Event.Type.TEST_UI_EVENT,
                             subtype=self._pass_event))

  def Prepare(self):
    """Called before running display detection loop."""
    pass

  def Run(self):
    # If the display is unable to detect, it should not perform the remaining
    # tasks.
    self.InitUI(fail_later=False)
    self.Prepare()
    self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
    self._wait_display.start()

    if self._bft_command:
      try:
        self._fixture.SetDeviceEngaged(BFTFixture.Device.EXT_DISPLAY,
                                       self._connect)
      except BFTFixtureException as e:
        self.Fail('Detect display failed: %s' % e)

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
      DetectDisplayTask.CONNECT)


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
      DetectDisplayTask.DISCONNECT)


class FixtureCheckDisplayThread(threading.Thread):
  """A thread to use fixture to check display.

  When expected connection state is observed, it calls on_success and stop.
  Or the calling thread can stop it using Stop().
  It probes display state every _CONNECTION_CHECK_PERIOD_SECS seconds.

  Args:
    fixture: BFTFixture instance.
    check_interval_secs: Interval between checks in seconds.
    retry_times: Number of retries before fail.
    on_success: callback for success.
    on_failure: callback for failure.
  """
  def __init__(self, fixture, check_interval_secs, retry_times, on_success,
               on_failure):
    threading.Thread.__init__(self, name='FixtureCheckDisplayThread')
    self._done = threading.Event()
    self._fixture = fixture
    self._check_interval = check_interval_secs
    self._retry_times = retry_times
    self._on_success = on_success
    self._on_failure = on_failure

  def run(self):
    num_tries = 0
    while not self._done.is_set():
      try:
        self._fixture.CheckExtDisplay()
        self._on_success()
        self.Stop()
        return
      except BFTFixtureException:
        num_tries += 1
        if num_tries < self._retry_times:
          logging.info(
            'Cannot see screen on external display. Wait for %.1f seconds.',
            self._check_interval)
          self._done.wait(self._check_interval)
        else:
          logging.error(
            'Failed to see screen on external display after %d retries.',
            self._retry_times)
          self._on_failure()
          self.Stop()

  def Stop(self):
    """Stops the thread."""
    self._done.set()


class VideoTask(ExtDisplayTask):
  """Task to show screen on external display only.

  The task is passed only after an operator press a random digit which
  is promoted on the external display.

  Args:
    args: refer base class.
  """
  def __init__(self, args):
    self._fixture = args.fixture
    self._manual = not self._fixture
    self._ui = args.ui
    self._original_primary_display = self._GetPrimayScreenId()

    # Bind a random key (0-9) to pass the task.
    if self._manual:
      self._pass_digit = random.randint(0, 9)
      instruction = '%s<br>%s' % (
        _MSG_VIDEO_TEST(args.display_label),
        _MSG_PROMPT_PASS_KEY(self._pass_digit))

    if self._fixture:
      instruction = _MSG_FIXTURE_VIDEO_TEST(args.display_label)
      self._check_display = FixtureCheckDisplayThread(self._fixture, 1, 10,
                                                      self.PostSuccessEvent,
                                                      self.PostFailureEvent)
      self._pass_event = str(uuid.uuid4())  # used to bind a post event.
      self._fail_event = str(uuid.uuid4())  # used to bind a post event.
      self._ui.AddEventHandler(self._pass_event, lambda _: self.Pass())
      self._ui.AddEventHandler(
          self._fail_event,
          lambda _: self.Fail('Fail to check screen on external display'))

    super(VideoTask, self).__init__(args,
                                    _TITLE_VIDEO_TEST(args.display_label),
                                    instruction,
                                    pass_key=False)

  def _GetPrimayScreenId(self):
    for info in factory.get_state_instance().GetDisplayInfo():
      if info['isPrimary']:
        return info['id']
    self.Fail('Fail to get primary display ID')

  def SetMainDisplay(self, recover_original=True):
    """Sets the main display.

    If there are two displays, this method can switch main display based on
    recover_original. If there is only one display, it returns if the only
    display is an external display (e.g. on a chromebox).

    Args:
      recover_original: True to set the original display as main;  False to
          set the other (external) display as main.
    """
    display_info = factory.get_state_instance().GetDisplayInfo()
    if len(display_info) == 1:
      # Fail the test if we see only one display and it's the internal one.
      if display_info[0]['isInternal']:
        self.Fail('Fail to detect external display')
      else:
        return

    os.environ['DISPLAY'] = ':0'
    os.environ['XAUTHORITY'] = '/home/chronos/.Xauthority'
    # Try to switch main display for at most 5 times.
    tries_left = 5
    while tries_left:
      if not (recover_original ^ (self._GetPrimayScreenId() ==
                                  self._original_primary_display)):
        # Stop the loop if these two conditions are either both True or
        # both False.
        break
      utils.SendKey('Alt+F4')
      tries_left -= 1
      time.sleep(2)

    if tries_left == 0:
      self.Fail('Fail to switch main display')

  def PostSuccessEvent(self):
    """Posts an event to trigger self.Pass().

    It is called by another thread. It ensures that self.Pass() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(Event(Event.Type.TEST_UI_EVENT,
                             subtype=self._pass_event))

  def PostFailureEvent(self):
    """Posts an event to trigger self.Fail().

    It is called by another thread. It ensures that self.Fail() is called
    via event queue to prevent race condition.
    """
    self._ui.PostEvent(Event(Event.Type.TEST_UI_EVENT,
                             subtype=self._fail_event))

  def Run(self):
    self.SetMainDisplay(recover_original=False)
    self.InitUI()

    if self._fixture:
      # Show light green background for Fixture's light sensor checking.
      self._ui.RunJS(
          'document.getElementById("state").style.backgroundColor = "#00ff00";')

    if self._manual:
      self.BindDigitKeys(self._pass_digit)

    if self._fixture:
      self._check_display.start()

  def Cleanup(self):
    self.SetMainDisplay(recover_original=True)
    if self._manual:
      self.UnbindDigitKeys()
    if self._fixture:
      self._check_display.Stop()


class ExtDisplayTaskArg(object):
  """Contains args needed by ExtDisplayTask."""
  def __init__(self):
    self.main_display_id = None
    self.display_label = None
    self.display_id = None
    self.card_id = 0
    self.audio_port = None
    self.ui = None
    self.template = None
    self.fixture = None

    # This is for a reboot hack which tells DetectDisplayTask
    # whether to send a display plug command or not.
    self.already_connect = False

  def ParseDisplayInfo(self, info):
    """Parses tuple from args.display_info.

    Args:
      info: a tuple in args.display_info. Refer display_info definition.

    Raises:
      ValueError if parse error.
    """
    # Sanity check
    if len(info) not in [2, 3]:
      raise ValueError('ERROR: invalid display_info item: ' + str(info))

    self.display_label, self.display_id = info[:2]
    if len(info) == 3:
      self.audio_port = info[2][1]
      if isinstance(info[2][0], int):
        self.card_id = info[2][0]
      elif isinstance(info[2][0], (str, unicode)):
        self.card_id = audio_utils.GetCardIndexByName(info[2][0])
      else:
        raise ValueError('Card ID should be an integer or a string')


class ExtDisplayTest(unittest.TestCase):
  """Main class for external display test."""
  ARGS = [
    Arg('main_display', str, 'xrandr ID for ChromeBook\'s main display.',
        optional=False),
    Arg('display_info', list,
        ('A list of tuples:\n'
         '\n'
         '  (display_label, display_id, audio_info)\n'
         '\n'
         'Each tuple represents an external port.\n'
         '\n'
         '- display_label: (str) display name seen by operator, e.g. VGA.\n'
         '- display_id: (str) ID used to identify display in xrandr.\n'
         '  e.g. VGA1.\n'
         '- audio_info: a tuple of (str, str) where the first str is the\n'
         '  card name and the second str is the amixer port name for audio\n'
         '  test. If set, the audio playback test is added for the display.'),
        optional=False),
    Arg('bft_fixture', dict, TEST_ARG_HELP, default=None, optional=True),
    Arg('connect_only', bool,
        'Just detect ext display connection. This is for a hack that DUT needs '
        'reboot after connect to prevent X crash.',
        default=False),
    Arg('start_output_only', bool,
        'Only start output of external display. This is for bringing up '
        'the external display for other tests that need it.',
        default=False),
    Arg('stop_output_only', bool,
        'Only stop output of external display. This is for bringing down '
        'the external display that other tests have finished using.',
        default=False),
    Arg('already_connect', bool,
        'Also for the reboot hack with fixture. With it set to True, DUT does '
        'not issue plug ext display command.',
        default=False),
  ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._task_manager = None
    self._fixture = None
    if self.args.bft_fixture:
      self._fixture = CreateBFTFixture(**self.args.bft_fixture)

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
      args.fixture = self._fixture
      args.already_connect = self.args.already_connect

      if not self.args.stop_output_only:
        tasks.append(ConnectTask(args))
        if not self.args.connect_only:
          tasks.append(VideoTask(args))
          if args.audio_port:
            audio_label = test_ui.MakeLabel('%s Audio' % args.display_label,
                                            u' %s 音讯' % args.display_label)
            tasks.append(audio.AudioDigitPlaybackTask(
                self._ui, audio_label, args.audio_port,
                'instruction', 'instruction-center', card_id=args.card_id))
          if not self.args.start_output_only:
            tasks.append(DisconnectTask(args))
      else:
        tasks.append(DisconnectTask(args))

      return tasks

  def runTest(self):
    self.InitUI()
    self._task_manager = FactoryTaskManager(
      self._ui, self.ComposeTasks(),
      update_progress=self._template.SetProgressBarValue)
    self._task_manager.Run()
