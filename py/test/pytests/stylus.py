# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test stylus functionality.

Description
-----------
Verifies if stylus is functional by asking operator to draw specified lines or
shapes using stylus.

For EMR stylus, drawing a diagonal line from left-bottom to right-top corner
should be sufficient to validate all scan lines. But for clamshells with hall
sensor, the magnet may cause EMR stylus to be non-functional in particular area.
To test that, set argument `endpoints_ratio` to build the lines for operator to
draw.

Test Procedure
--------------
1. When started, a diagonal line is displayed on screen.
2. Operator must use stylus to draw and follow the displayed line.
3. If the stylus moved too far (specified in argument `error_margin`) from the
   requested path, test will fail.

Dependency
----------
- Based on Linux evdev.

Examples
--------
To check stylus functionality by drawing a diagonal line, add this in test
list::

  {
    "pytest_name": "stylus"
  }

To check if the magnet in left side will cause problems, add this in test list
to draw a line from left-top to left-bottom::

  {
    "pytest_name": "stylus",
    "args": {
      "endpoints_ratio": [
        [0, 0],
        [0, 1]
      ]
    }
  }
"""

import threading

from cros.factory.test.i18n import _
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import evdev_utils
from cros.factory.test.utils import touch_monitor
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils
from cros.factory.utils.type_utils import Enum

from cros.factory.external import evdev


class StylusMonitor(touch_monitor.SingleTouchMonitor):

  def __init__(self, device, ui):
    super(StylusMonitor, self).__init__(device)
    self._ui = ui
    self._lock = threading.RLock()
    self._buffer = []

  @sync_utils.Synchronized
  def OnMove(self):
    """See SingleTouchMonitor.OnMove."""
    cur_state = self.GetState()
    if cur_state.keys[evdev.ecodes.BTN_TOUCH]:
      # Instead of directly call JavaScript function 'handler' here, we buffer
      # the events to reduce the latency from CallJSFunction.
      self._buffer.append([cur_state.x, cur_state.y])

  @sync_utils.Synchronized
  def Flush(self):
    if self._buffer:
      self._ui.CallJSFunction('handler', self._buffer)
      self._buffer = []


class StylusTest(test_case.TestCase):
  """Stylus factory test."""

  ARGS = [
      Arg('device_filter', (int, str, list), 'Stylus input event id, evdev '
          'name, or evdev events.',
          default=None),
      Arg('error_margin', int,
          'Maximum tolerable distance to the diagonal line (in pixel).',
          default=25),
      Arg('begin_ratio', float,
          'The beginning position of the diagonal line segment to check. '
          'Should be in (0, 1).',
          default=0.01),
      Arg('end_ratio', float,
          'The ending position of the diagonal line segment to check. '
          'Should be in (0, 1).',
          default=0.99),
      Arg('step_ratio', float,
          'If the distance between an input event to the latest accepted '
          'input event is larger than this size, it would be ignored. '
          'Should be in (0, 1).',
          default=0.01),
      Arg('endpoints_ratio', list,
          'A list of two pairs, each pair contains the X and Y coordinates '
          'ratio of an endpoint of the line segment for operator to draw. '
          'Both endpoints must be on the border '
          '(e.g., X=0 or X=1 or Y=0 or Y=1).',
          default=[[0, 1], [1, 0]]),
      Arg('autostart', bool,
          'Starts the test automatically without prompting.  Operators can '
          'still press ESC to fail the test.',
          default=False),
      Arg('flush_interval', float,
          'The time interval of flushing event buffers.',
          default=0.1),
      Arg('angle_compensation', Enum([0, 90, 180, 270]),
          'Specify one of the following angles to compensate UI orientation '
          'in counter-clockwise direction: [0, 90, 180, 270].  '
          'This is a special argument that should be changed only when '
          'panel scanout orientation is different from default system '
          'orientation, e.g. panel scanout is following portrait direction but '
          'system default orientation is in landscape mode.',
          default=0)
  ]

  def setUp(self):
    filters = [evdev_utils.IsStylusDevice]
    if isinstance(self.args.device_filter, list):
      filters += self.args.device_filter
    else:
      filters += [self.args.device_filter]

    self._device = evdev_utils.FindDevice(*filters)
    self._monitor = None
    self._dispatcher = None
    self._daemon = None
    self._state = state.GetInstance()

    assert self.args.error_margin >= 0
    assert 0 < self.args.begin_ratio < self.args.end_ratio < 1
    assert 0 < self.args.step_ratio < 1

    assert len(self.args.endpoints_ratio) == 2
    assert self.args.endpoints_ratio[0] != self.args.endpoints_ratio[1]
    for point in self.args.endpoints_ratio:
      assert isinstance(point, list) and len(point) == 2
      assert all(0 <= x_or_y <= 1 for x_or_y in point)
      assert any(x_or_y in [0, 1] for x_or_y in point)

    assert self.args.flush_interval > 0

  def tearDown(self):
    if self._dispatcher is not None:
      self._dispatcher.close()
    self._device.ungrab()

  def runTest(self):
    self.ui.BindStandardFailKeys()
    if not self.args.autostart:
      self.ui.SetHTML(
          _('Please extend the green line with stylus to the other end.<br>'
            'Stay between the two red lines.<br>'
            'Press SPACE to start; Esc to fail.'),
          id='msg')
      self.ui.WaitKeysOnce(test_ui.SPACE_KEY)

    self._daemon = process_utils.StartDaemonThread(target=self.CheckRotation)
    self._device = evdev_utils.DeviceReopen(self._device)
    self._device.grab()
    self._monitor = StylusMonitor(self._device, self.ui)
    self._dispatcher = evdev_utils.InputDeviceDispatcher(self._device,
                                                         self._monitor.Handler)
    self._dispatcher.StartDaemon()
    while True:
      self._monitor.Flush()
      self.Sleep(self.args.flush_interval)

  def CheckRotation(self):
    last_rotation = None
    angle_compensation = self.args.angle_compensation
    rotate_msg = {
        (90  + angle_compensation) % 360: _('clockwise'),
        (180 + angle_compensation) % 360: _('upside down'),
        (270 + angle_compensation) % 360: _('counterclockwise')
    }

    while True:
      rotation = self._state.DeviceGetDisplayInfo()[0]['rotation']

      if last_rotation == rotation:
        pass
      elif rotation in rotate_msg:
        # Wrong rotation
        self.ui.CallJSFunction('hideStylusTest')
        self.ui.SetHTML(
            _('Please rotate the device: {msg}', msg=rotate_msg[rotation]),
            id='msg')
      else:
        self.ui.CallJSFunction('setupStylusTest',
                               self.args.error_margin, self.args.begin_ratio,
                               self.args.end_ratio, self.args.step_ratio,
                               self.args.endpoints_ratio)

      last_rotation = rotation
      self.Sleep(0.5)
