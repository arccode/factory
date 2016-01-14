# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests Raiden DP function with Plankton-Raiden, which links/unlinks DUT Raiden
port to DP sink. And with Plankton-HDMI as DP sunk to capture DP output to
verify.
"""

import evdev
import logging
import os
import time
import unittest
import xmlrpclib

import factory_common  # pylint: disable=W0611

from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.fixture.dolphin import plankton_hdmi
from cros.factory.test.utils import evdev_utils
from cros.factory.utils import file_utils
from cros.factory.utils import sync_utils


_TEST_TITLE = test_ui.MakeLabel('Raiden Display Test', u'Raiden 显示测试')

_CONNECT_STR = lambda d: test_ui.MakeLabel(
    'Connecting BFT display: %s' % d,
    u'正在连接 BFT 显示屏: %s' % d)
_VIDEO_STR = lambda d: test_ui.MakeLabel(
    'BFT display %s is connected. Sending image...' % d,
    u'已连接 BFT 显示屏: %s, 正在传送画面' % d)
_DISCONNECT_STR = lambda d: test_ui.MakeLabel(
    'Disconnecting BFT display: %s' % d,
    u'正在移除 BFT 显示屏: %s' % d)

_BLACKSCREEN_STR = test_ui.MakeLabel(
    'Caution: monitor may turn black for a short time.',
    u'注意: 萤幕可能会有短暂黑屏')

_ID_CONTAINER = 'raiden-display-container'

# The style is in raiden_display.css
# The layout contains one div for display.
_HTML_DISPLAY = (
    '<link rel="stylesheet" type="text/css" href="raiden_display.css">'
    '<div id="%s"></div>\n' % _ID_CONTAINER)

_WAIT_DISPLAY_SIGNAL_SECS = 3
_WAIT_RETEST_SECS = 2


class RaidenDisplayTest(unittest.TestCase):
  """Tests Raiden ports display functionality."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('raiden_index', int, 'Index of DUT raiden port'),
      Arg('bft_media_device', str,
          'Device name of BFT used to insert/remove the media.'),
      Arg('display_id', str,
          'Display ID used to identify display in xrandr/modeprint.'),
      Arg('capture_resolution', tuple,
          'A tuple (x-res, y-res) indicating the'
          'image capture resolution to use.',
          default=(1920, 1080)),
      Arg('capture_fps', int, 'Camera capture rate in frames per second.',
          default=30),
      Arg('uvc_video_dev_index', int, 'index of video device (-1 for default)',
          default=-1),
      Arg('uvc_video_dev_port', str, 'port of video device (ex. 3-1)',
          optional=True),
      Arg('corr_value_threshold', tuple,
          'A tuple of (b, g, r) channel histogram '
          'correlation pass/fail threshold. '
          'Should be int/float type, ex. (0.8, 0.8, 0.8)',
          default=(0.8, 0.8, 0.8)),
      Arg('dp_verify_server', str,
          'Server URL for verifying DP output, e.g. "http://192.168.0.1:9999". '
          'Default None means verifying locally.',
          optional=True),
      Arg('verify_display_switch', bool,
          'Set False to test without display switch, and compare default '
          'wallpaper only (can save more testing time).',
          default=True)
  ]

  def setUp(self):
    self._dut = dut.Create()
    self._ui = test_ui.UI()
    self._template = ui_templates.TwoSections(self._ui)
    self._template.SetTitle(_TEST_TITLE)
    self._ui.AppendHTML(_HTML_DISPLAY)

    self._static_dir = self._ui.GetStaticDirectoryPath()
    self._display_image_path = os.path.join(self._static_dir, 'template.png')
    self._golden_image_path = os.path.join(self._static_dir, 'golden.png')
    self.ExtractTestImage()

    self._ui.CallJSFunction('setupDisplayTest', _ID_CONTAINER)

    self._total_tests = 0
    self._finished_tests = 0
    self._finished = False
    self._image_matched = True

    self._testing_display = self.args.display_id
    self._bft_fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    self._bft_media_device = self.args.bft_media_device
    if self._bft_media_device not in self._bft_fixture.Device:
      self.Fail('Invalid args.bft_media_device: ' + self._bft_media_device)

    self._original_primary_display = self._GetPrimaryScreenId()

    self._verify_server = None
    self._server_camera_enabled = False
    self._camera_device = None
    self._verify_locally = not self.args.dp_verify_server
    if self.args.dp_verify_server:
      # allow_none is necessary as most of the methods return None.
      self._verify_server = xmlrpclib.ServerProxy(
          self.args.dp_verify_server, allow_none=True)
    else:
      uvc_video_index = (None if self.args.uvc_video_dev_index < 0 else
                         self.args.uvc_video_dev_index)
      self._camera_device = plankton_hdmi.PlanktonHDMI(
          uvc_video_index=uvc_video_index,
          uvc_video_port=self.args.uvc_video_dev_port,
          capture_resolution=self.args.capture_resolution,
          capture_fps=self.args.capture_fps)

  def tearDown(self):
    # Make sure to disable camera of dp_verify_server in the end of test.
    if self._server_camera_enabled:
      self._verify_server.DisableCamera()
    self._bft_fixture.Disconnect()
    self.RemoveTestImage()
    return

  def ExtractTestImage(self):
    """Extracts selected test images from zipped files."""
    filename = ('template.tar.gz' if self.args.verify_display_switch else
                'wallpaper.tar.gz')
    file_utils.ExtractFile(os.path.join(self._static_dir, filename),
                           self._static_dir)

  def RemoveTestImage(self):
    """Removes extracted image files after test finished."""
    file_utils.TryUnlink(self._display_image_path)
    file_utils.TryUnlink(self._golden_image_path)

  def TestConnectivity(self, connect):
    """Tests connectivity of bft media device.

    It uses BFT fixture to engage / disengage the display device.

    Args:
      connect: True if testing engagement, False if testing disengagement.
    """
    if connect:
      self._template.SetInstruction(_CONNECT_STR(self._bft_media_device))
      self._bft_fixture.SetDeviceEngaged(self._bft_media_device, engage=True)
      time.sleep(0.5)
      # DUT control for Raiden function: DP mode
      self._dut.usb_c.ResetHPD(self.args.raiden_index)
      time.sleep(1)  # Wait for reset HPD response
      self._dut.usb_c.SetHPD(self.args.raiden_index)
      self._dut.usb_c.SetPortFunction(self.args.raiden_index, 'dp')
      sync_utils.WaitFor(self._PollDisplayConnected, timeout_secs=10)
    else:
      self._template.SetInstruction(_DISCONNECT_STR(self._bft_media_device))
      self._dut.usb_c.ResetHPD(self.args.raiden_index)
      self._bft_fixture.SetDeviceEngaged(self._bft_media_device, engage=False)
      sync_utils.WaitFor(lambda: not self._PollDisplayConnected(),
                         timeout_secs=10)

    if not self.args.verify_display_switch:
      self.AdvanceProgress()
      return

    time.sleep(_WAIT_DISPLAY_SIGNAL_SECS)  # need a delay for display_info
    display_info = factory.get_state_instance().DeviceGetDisplayInfo()
    # In the case of connecting an external display, make sure there
    # is an item in display_info with 'isInternal' False.
    # On the other hand, in the case of disconnecting an external display,
    # we can not check display info has no display with 'isInternal' False
    # because any display for chromebox has 'isInternal' False.
    if not connect or any(x['isInternal'] == False for x in display_info):
      logging.info('Get display info %r', display_info)
      self.AdvanceProgress()
    else:
      self.Fail('Get the wrong display info')

  def TestDisplayPlayback(self):
    """Projects the screen to external display, make the display to show an
    image by JS function.
    """
    if self.args.verify_display_switch:
      self._template.SetInstruction(_VIDEO_STR(self._bft_media_device))
      self._ui.CallJSFunction('switchDisplayOnOff')
      self.SetMainDisplay(recover_original=False)

    time.sleep(_WAIT_DISPLAY_SIGNAL_SECS)  # wait for display signal stable
    self.AdvanceProgress()

  def TestCaptureImage(self):
    """Tests and compares loopback image.

    Link to camera device and capture an image from camera. Compare to
    the image projected to external display by bgr-channel histogram
    comparisons to judge DP functionality.

    Raises:
      BFTFixtureException: If it failed to detect camera.
    """
    if self._verify_locally:
      self._image_matched = self._camera_device.CaptureCompare(
          self._golden_image_path, self.args.corr_value_threshold)
    else:
      corr_values = self._verify_server.VerifyDP(True)
      self._image_matched = all(
          c >= t for c, t in zip(corr_values, self.args.corr_value_threshold))
      logging.info('CompareHist correlation result = b: %.4f, g: %.4f, r: %.4f',
                   corr_values[0], corr_values[1], corr_values[2])

    if self.args.verify_display_switch:
      self._ui.CallJSFunction('switchDisplayOnOff')
      self.SetMainDisplay(recover_original=True)
      time.sleep(_WAIT_DISPLAY_SIGNAL_SECS)  # wait for display signal stable

    self.AdvanceProgress()

  def SetMainDisplay(self, recover_original=True):
    """Sets the main display.

    If there are two displays, this method can switch main display based on
    recover_original. If there is only one display, it returns if the only
    display is an external display (e.g. on a chromebox).

    Args:
      recover_original: True to set the original display as main; False to
          set the other (external) display as main.
    """
    display_info = factory.get_state_instance().DeviceGetDisplayInfo()
    if len(display_info) == 1:
      # Fail the test if we see only one display and it's the internal one.
      if display_info[0]['isInternal']:
        self.Fail('Fail to detect external display')
      else:
        return

    # Try to switch main display for at most 5 times.
    tries_left = 5
    while tries_left:
      if not (recover_original ^ (self._GetPrimaryScreenId() ==
                                  self._original_primary_display)):
        # Stop the loop if these two conditions are either both True or
        # both False.
        break
      evdev_utils.SendKeys([evdev.ecodes.KEY_LEFTALT, evdev.ecodes.KEY_F4])
      tries_left -= 1
      time.sleep(_WAIT_RETEST_SECS)

    if tries_left == 0:
      self.Fail('Fail to switch main display')

  def Fail(self, msg):
    """Fails the test."""
    self._ui.Fail(msg)
    raise factory.FactoryTestFailure(msg)

  def AdvanceProgress(self, value=1):
    """Advances the progess bar.

    Args:
      value: The amount of progress to advance.
    """
    self._finished_tests += value
    if self._finished_tests > self._total_tests:
      self._finished_tests = self._total_tests
    self._template.SetProgressBarValue(
        100 * self._finished_tests / self._total_tests)

  def _GetPrimaryScreenId(self):
    """Gets ID of primary screen.

    Returns:
      Integer for screen ID.
    """
    for info in factory.get_state_instance().DeviceGetDisplayInfo():
      if info['isPrimary']:
        return info['id']
    self.Fail('Fail to get primary display ID')

  def _PollDisplayConnected(self):
    """Event for polling display connected.

    Returns:
      True if connected; otherwise False.
    """
    return self._dut.display.GetPortInfo()[self._testing_display].connected

  def runTest(self):
    """Runs display test."""
    # Sanity check
    if self.args.verify_display_switch:
      self.assertTrue(os.path.isfile(self._display_image_path))
    self.assertTrue(os.path.isfile(self._golden_image_path))

    self._template.DrawProgressBar()
    # Connect, video playback, capture, disconnect
    self._total_tests = 4
    self._template.SetProgressBarValue(0)
    self._template.SetState(_BLACKSCREEN_STR)

    logging.info('Testing device: %s', self._bft_media_device)

    if self._verify_locally:
      self._camera_device.EnableCamera()
    else:
      self._verify_server.EnableCamera()
      self._server_camera_enabled = True

    self.TestConnectivity(connect=True)
    self.TestDisplayPlayback()
    self.TestCaptureImage()
    self.TestConnectivity(connect=False)

    if self._verify_locally:
      self._camera_device.DisableCamera()
    else:
      self._verify_server.DisableCamera()
      self._server_camera_enabled = False

    self._finished = True
    if not self._image_matched:
      self.Fail('DP Loopback image correlation is below threshold.')
