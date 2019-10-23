# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests USB type-C DP function with Plankton-Raiden, which links/unlinks DUT
USB type-C port to DP sink. And with Plankton-HDMI as DP sunk to capture DP
output to verify.
"""

import logging
import os
import xmlrpc.client

from cros.factory.device import device_utils
from cros.factory.test.fixture import bft_fixture
from cros.factory.test.fixture.dolphin import plankton_hdmi
from cros.factory.test.i18n import _
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test.utils import evdev_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import sync_utils

from cros.factory.external import evdev


_WAIT_DISPLAY_SIGNAL_SECS = 3
_WAIT_RETEST_SECS = 2


class PlanktonDisplayTest(test_case.TestCase):
  """Tests USB type-C ports display functionality."""
  ARGS = [
      Arg('bft_fixture', dict, bft_fixture.TEST_ARG_HELP),
      Arg('usb_c_index', int, 'Index of DUT USB type-C port'),
      Arg('bft_media_device', str,
          'Device name of BFT used to insert/remove the media.'),
      Arg('display_id', str,
          'Display ID used to identify display in xrandr/modeprint.'),
      Arg('capture_resolution', list,
          '[x-res, y-res] indicating the image capture resolution to use.',
          default=[1920, 1080]),
      Arg('capture_fps', int, 'Camera capture rate in frames per second.',
          default=30),
      Arg('uvc_video_dev_index', int, 'index of video device (-1 for default)',
          default=-1),
      Arg('uvc_video_dev_port', str, 'port of video device (ex. 3-1)',
          default=None),
      Arg('corr_value_threshold', list,
          '[b, g, r] channel histogram correlation pass/fail threshold. '
          'Should be int/float type, ex. [0.8, 0.8, 0.8]',
          default=[0.8, 0.8, 0.8]),
      Arg('dp_verify_server', str,
          'Server URL for verifying DP output, e.g. "http://192.168.0.1:9999". '
          'Default None means verifying locally.',
          default=None),
      Arg('verify_display_switch', bool,
          'Set False to test without display switch, and compare default '
          'wallpaper only (can save more testing time).',
          default=True),
      Arg('force_dp_renegotiated', bool,
          'Force DP to renegotiate with plankton by disconnecting TypeC port',
          default=False),
      Arg('fire_hpd_manually', bool, 'Fire HPD manually.', default=False)
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

    self._static_dir = self.ui.GetStaticDirectoryPath()
    self._display_image_path = os.path.join(self._static_dir, 'template.png')
    self._golden_image_path = os.path.join(self._static_dir, 'golden.png')
    self.ExtractTestImage()

    self.frontend_proxy = self.ui.InitJSTestObject('DisplayTest')

    self._image_matched = True

    self._testing_display = self.args.display_id
    self._bft_fixture = bft_fixture.CreateBFTFixture(**self.args.bft_fixture)
    self._bft_media_device = self.args.bft_media_device
    if self._bft_media_device not in self._bft_fixture.Device:
      self.FailTask('Invalid args.bft_media_device: ' + self._bft_media_device)

    self._original_primary_display = self._GetPrimaryScreenId()

    self._verify_server = None
    self._server_camera_enabled = False
    self._camera_device = None
    self._verify_locally = not self.args.dp_verify_server
    if self.args.dp_verify_server:
      # allow_none is necessary as most of the methods return None.
      self._verify_server = xmlrpc.client.ServerProxy(
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
      self._DisableServerCamera()
    self._bft_fixture.Disconnect()
    self.RemoveTestImage()

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
      self.ui.SetInstruction(
          _('Connecting BFT display: {device}', device=self._bft_media_device))
      self._bft_fixture.SetDeviceEngaged(self._bft_media_device, engage=True)
      if self.args.force_dp_renegotiated:
        self._bft_fixture.SetFakeDisconnection(1)
        # disconnetion by software for re-negotiation.
        self.Sleep(1)
      else:
        self.Sleep(0.5)
      if self.args.fire_hpd_manually:
        self._dut.usb_c.SetHPD(self.args.usb_c_index)
        self._dut.usb_c.SetPortFunction(self.args.usb_c_index, 'dp')
      sync_utils.WaitFor(self._PollDisplayConnected, timeout_secs=10)
    else:
      self.ui.SetInstruction(
          _('Disconnecting BFT display: {device}',
            device=self._bft_media_device))
      if self.args.fire_hpd_manually:
        self._dut.usb_c.ResetHPD(self.args.usb_c_index)
      self._bft_fixture.SetDeviceEngaged(self._bft_media_device, engage=False)
      if self.args.force_dp_renegotiated:
        self._bft_fixture.SetFakeDisconnection(1)
        # disconnetion by software for re-negotiation.
        self.Sleep(1)
      sync_utils.WaitFor(lambda: not self._PollDisplayConnected(),
                         timeout_secs=10)

    if not self.args.verify_display_switch:
      self.ui.AdvanceProgress()
      return

    # need a delay for display_info
    self.Sleep(_WAIT_DISPLAY_SIGNAL_SECS)
    display_info = state.GetInstance().DeviceGetDisplayInfo()
    logging.info('Get display info %r', display_info)
    # In the case of connecting an external display, make sure there
    # is an item in display_info with 'isInternal' False.
    # On the other hand, in the case of disconnecting an external display,
    # we can not check display info has no display with 'isInternal' False
    # because any display for chromebox has 'isInternal' False.
    if not connect or any(x['isInternal'] is False for x in display_info):
      self.ui.AdvanceProgress()
    else:
      self.FailTask('Get the wrong display info')

  def TestDisplayPlayback(self):
    """Projects the screen to external display, make the display to show an
    image by JS function.
    """
    if self.args.verify_display_switch:
      self.ui.SetInstruction(
          _('BFT display {device} is connected. Sending image...',
            device=self._bft_media_device))
      self.frontend_proxy.ToggleFullscreen()
      self.SetMainDisplay(recover_original=False)

    # wait for display signal stable
    self.Sleep(_WAIT_DISPLAY_SIGNAL_SECS)
    self.ui.AdvanceProgress()

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
      self._image_matched = self._verify_server.VerifyDP(False)

    if self.args.verify_display_switch:
      self.frontend_proxy.ToggleFullscreen()
      self.SetMainDisplay(recover_original=True)
      # wait for display signal stable
      self.Sleep(_WAIT_DISPLAY_SIGNAL_SECS)

    self.ui.AdvanceProgress()

  def SetMainDisplay(self, recover_original=True):
    """Sets the main display.

    If there are two displays, this method can switch main display based on
    recover_original. If there is only one display, it returns if the only
    display is an external display (e.g. on a chromebox).

    Args:
      recover_original: True to set the original display as main; False to
          set the other (external) display as main.
    """
    display_info = state.GetInstance().DeviceGetDisplayInfo()
    if len(display_info) == 1:
      # Fail the test if we see only one display and it's the internal one.
      if display_info[0]['isInternal']:
        self.FailTask('Fail to detect external display')
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
      self.Sleep(_WAIT_RETEST_SECS)

    if tries_left == 0:
      self.FailTask('Fail to switch main display')

  def _GetPrimaryScreenId(self):
    """Gets ID of primary screen.

    Returns:
      Integer for screen ID.
    """
    for info in state.GetInstance().DeviceGetDisplayInfo():
      if info['isPrimary']:
        return info['id']
    self.FailTask('Fail to get primary display ID')
    return None

  def _PollDisplayConnected(self):
    """Event for polling display connected.

    Returns:
      True if connected; otherwise False.
    """
    return self._dut.display.GetPortInfo()[self._testing_display].connected

  def _DisableServerCamera(self):
    if not self._server_camera_enabled:
      return
    def _PingDPVerifyServer():
      return self._dut.Call(
          ['wget', self.args.dp_verify_server, '-T', '1']) == 8
    sync_utils.WaitFor(_PingDPVerifyServer, timeout_secs=30)
    self._verify_server.DisableCamera()
    self._server_camera_enabled = False

  def runTest(self):
    """Runs display test."""
    # Sanity check
    if self.args.verify_display_switch:
      self.assertTrue(os.path.isfile(self._display_image_path))
    self.assertTrue(os.path.isfile(self._golden_image_path))

    # Connect, video playback, capture, disconnect
    self.ui.DrawProgressBar(4)

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
      self._DisableServerCamera()
      self._server_camera_enabled = False

    if not self._image_matched:
      self.FailTask('DP Loopback image correlation is below threshold.')
