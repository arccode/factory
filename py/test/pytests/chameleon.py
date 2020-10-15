# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test that utilizes Chameleon to do automated display testing."""

import contextlib
import logging
import os
import xmlrpc.client

from PIL import Image
from PIL import ImageChops
from PIL import ImageDraw

from cros.factory.device import device_utils
from cros.factory.test.env import goofy_proxy
from cros.factory.test.i18n import _
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.utils import arg_utils
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


PORTS = type_utils.Enum(['DP', 'HDMI'])
EDIDS = {
    PORTS.DP: {
        ('2560x1600', '60Hz'): 'DP_2560x1600_60Hz',
        ('1920x1080', '60Hz'): 'DP_1920x1080_60Hz',
    },
    PORTS.HDMI: {
        ('3840x2160', '30Hz'): 'HDMI_3840x2160_30Hz',
        ('1920x1200', '60Hz'): 'HDMI_1920x1200_60Hz',
        ('1920x1080', '60Hz'): 'HDMI_1920x1080_60Hz',
    }
}


class Chameleon:
  """An interface to the Chameleon RPC server.

  Properties:
    chameleond: The XMLRPC server proxy for the Chameleond on the Chameleon
        board.
  """
  PORT_ID_MAP = {
      PORTS.DP: 1,
      PORTS.HDMI: 3,
  }

  def __init__(self, hostname, port):
    self.chameleond = xmlrpc.client.ServerProxy('http://%s:%s' %
                                                (hostname, port))

  def Reset(self):
    """Resets the Chameleon board."""
    self.chameleond.Reset()

  def IsPhysicallyPlugged(self, port):
    """Checks if the give port is physically plugged.

    Args:
      port: The port to check.
    """
    return self.chameleond.IsPhysicalPlugged(self.PORT_ID_MAP[port])

  def Plug(self, port):
    """Plugs the given port.

    Args:
      port: The port to plug.
    """
    logging.info('Emit HPD on %s port', port)
    self.chameleond.Plug(self.PORT_ID_MAP[port])

  def CreateEdid(self, edid):
    """Creates a EDID instance on the Chameleon board.

    Args:
      edid: A byte string of the EDID.

    Returns:
      The ID of the created EDID instance.
    """
    return self.chameleond.CreateEdid(xmlrpc.client.Binary(edid))

  def ApplyEdid(self, port, edid_id):
    """Applies the given EDID on the port.

    Args:
      port: The port.
      edid_id: The EDID ID.
    """
    self.chameleond.ApplyEdid(self.PORT_ID_MAP[port], edid_id)

  def DumpPixels(self, port):
    """Dumps the pixels on the given port.

    Args:
      port: The port to dump.

    Returns:
      A byte string of the dumped RGB pixels.
    """
    return self.chameleond.DumpPixels(self.PORT_ID_MAP[port]).data

  def DestroyEdid(self, edid_id):
    """Destroys the give EDID instance.

    Args:
      edid_id: The ID of the EDID instance.
    """
    self.chameleond.DestroyEdid(edid_id)

  def GetResolution(self, port):
    """Gets the active resolution of the give port.

    Args:
      port: The port.

    Returns:
      A (width, height) tuple representing the resolution.
    """
    resolution = self.chameleond.DetectResolution(self.PORT_ID_MAP[port])
    logging.info('Chameleon %s port resolution: %s', port, resolution)
    return resolution

  def Capture(self, port):
    """Captures the framebuffer on the give port.

    Args:
      port: The port to capture.

    Returns:
      A PIL.Image object of the captured RGB image.
    """
    return Image.fromstring(
        'RGB', self.GetResolution(port), self.DumpPixels(port))

  @contextlib.contextmanager
  def PortEdid(self, port, edid):
    """A context manager to run the given EDID of the given port.

    Args:
      port: The port.
      edid: The EDID byte string.

    Yields:
      The ID of the created EDID instance.
    """
    edid_id = self.CreateEdid(edid)
    self.ApplyEdid(port, edid_id)
    try:
      yield edid_id
    finally:
      self.DestroyEdid(edid_id)


class ChameleonDisplayTest(test_case.TestCase):
  """A factory test that utilizes Chameleon to do automated display testing."""
  ARGS = [
      arg_utils.Arg('chameleon_host', str,
                    'the hostname/IP address of the Chameleon server'),
      arg_utils.Arg('chameleon_port', int,
                    'the port of the Chameleon server', default=9992),
      arg_utils.Arg('test_info', list,
                    ('[dut_port, chameleon_port, resolution_width, '
                     'resolution_height, refresh_rate]; for example: '
                     '["DP1", "DP", 1920, 1080, 60] or '
                     '["DP1", "HDMI", 1920, 1080, 60]')),
      arg_utils.Arg('load_test_image', bool,
                    ('whether to load the reference pattern image; True to '
                     'load the test image in a Chrome window on the external '
                     'display, which may have timing issue to the test caused '
                     "by Chrome's pop-up messages"), default=False),
      arg_utils.Arg('ignore_regions', list,
                    ('a list of regions to ignore when comparing captured '
                     'images; each element of the list must be a [x, y, width, '
                     'height] to specify the rectangle to ignore'),
                    default=[]),
      arg_utils.Arg('downscale_to_tv_level', bool,
                    ('whether to downscale the internal framebuffer to TV '
                     'level for comparison'), default=False),
  ]

  IMAGE_TEMPLATE_WIDTH = 1680
  IMAGE_TEMPLATE_HEIGHT = 988
  IMAGE_TEMPLATE_FILENAME = 'template-%sx%s.svg' % (
      IMAGE_TEMPLATE_WIDTH, IMAGE_TEMPLATE_HEIGHT)
  CHAMELEON_IMAGE_PATH = '/usr/local/chameleon.png'
  INTERNAL_IMAGE_PATH = '/usr/local/internal.png'
  DIFF_IMAGE_PATH = '/usr/local/diff_image.png'
  UI_IMAGE_RESIZE_RATIO = 0.4

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.chameleon = Chameleon(
        self.args.chameleon_host, self.args.chameleon_port)
    self.goofy_rpc = state.GetInstance()
    self.image_template_file = file_utils.CreateTemporaryFile(
        prefix='image_template.')

  def tearDown(self):
    os.unlink(self.image_template_file)

  def ProbeDisplay(self, chameleon_port):
    """Probes the internal/original and the external displays on the given port.

    Args:
      chameleon_port: The chameleon port to probe.

    Returns:
      A tuple (original_display, external_display) of the display info of the
      probed internal/original and external display.
    """
    logging.info('Probing external display...')

    def DoProbe():
      """Probes the display info.

      Returns:
        A tuple (original_display, external_display) of the display info of the
        probed internal/original and external display, or None if probing
        failed.
      """
      display_info = self.goofy_rpc.DeviceGetDisplayInfo()
      original_display = None
      for info in display_info:
        if info['isInternal']:
          original_display = info
          break
      else:
        return None
      for info in display_info:
        if info['id'] != original_display['id'] and not info['isInternal']:
          return original_display, info
      return None

    display_info = self.goofy_rpc.DeviceGetDisplayInfo()
    ext_display = None
    if len(display_info) == 2:
      # pylint: disable=unpacking-non-sequence
      orig_display, ext_display = DoProbe()
      if not ext_display:
        # In case where these is no internal display (e.g. Chromebox), we cannot
        # decide which external display is used for testing.
        logging.error('Unable to determine the external display to test.')
        self.fail('Please unplug the display to test.')
    elif len(display_info) == 1:
      self.ui.SetState(_('Please plug in the display to test'))
      logging.info('Checking %s physical port on Chameleon...', chameleon_port)
      sync_utils.WaitFor(
          lambda: self.chameleon.IsPhysicallyPlugged(chameleon_port),
          10, poll_interval=0.5)
      logging.info('%s port on Chameleon is physically plugged.',
                   chameleon_port)
      self.chameleon.Plug(chameleon_port)
      sync_utils.WaitFor(lambda: DoProbe() is not None, 10, poll_interval=0.5)
      # pylint: disable=unpacking-non-sequence
      orig_display, ext_display = DoProbe()
    else:
      self.fail('More than two displays detected; '
                'please remove all external displays')

    logging.info('External display probed: %s', ext_display)
    return (orig_display, ext_display)

  @contextlib.contextmanager
  def NewWindow(self, left, top, width=None, height=None):
    """Context manager to create a new window with the given attributes.

    If width and height are not given, the window is fullscreen by default.

    Args:
      left: The offset from the left in pixels.
      top: The offset from the top in pixels.
      width: The width of the new window in pixels.
      height: The height of the new window in pixels.

    Yields:
      The ID of the created window.
    """
    logging.info('Creating new window of size %sx%s at +%s+%s...',
                 width, height, left, top)
    window_id = self.goofy_rpc.DeviceCreateWindow(left, top)['id']
    if width is not None and height is not None:
      self.goofy_rpc.DeviceUpdateWindow(
          window_id, {'width': width, 'height': height})
    else:
      self.goofy_rpc.DeviceUpdateWindow(window_id, {'state': 'fullscreen'})
    try:
      yield window_id
    finally:
      self.goofy_rpc.DeviceRemoveWindow(window_id)

  def LoadTestImage(self, window_id, width, height):
    """Loads a test image of the given width and height on the given window.

    Args:
      window_id: The ID of the window.
      width: The width of the test image in pixels.
      height: The height of the test image in pixels.
    """
    logging.info('Loading test image of size %sx%s...', width, height)
    image_template = os.path.join(
        self.ui.GetStaticDirectoryPath(), self.IMAGE_TEMPLATE_FILENAME)
    with open(self.image_template_file, 'w') as output:
      with open(image_template) as f:
        output.write(f.read().format(
            scale_width=width / self.IMAGE_TEMPLATE_WIDTH,
            scale_height=height / self.IMAGE_TEMPLATE_HEIGHT))

    tab_id = self.goofy_rpc.DeviceQueryTabs(window_id)[0]['id']
    url = 'http://%s:%s%s' % (
        net_utils.LOCALHOST,
        goofy_proxy.DEFAULT_GOOFY_PORT,
        self.ui.URLForFile(self.image_template_file))
    self.goofy_rpc.DeviceUpdateTab(tab_id, {'url': url})

  def CaptureImages(self, dut_port, chameleon_port):
    """Captures the framebuffers on the given port to RGB images.

    This captures both the Chameleon and the internal framebuffers.

    Args:
      dut_port: The DUT port to capture.
      chameleon_port: The Chameleon port to capture.

    Returns:
      A (chameleon_image, internal_image) tuple of the captured RGB PIL.Image
      instances.
    """
    logging.info('Capturing %s port framebuffer on Chameleon...',
                 chameleon_port)
    chameleon_image = self.chameleon.Capture(chameleon_port)
    logging.info('Capturing %s port framebuffer on DUT...', dut_port)
    internal_image = self.dut.display.CaptureFramebuffer(
        dut_port, downscale=self.args.downscale_to_tv_level)
    return internal_image, chameleon_image

  def TestPort(self, dut_port, chameleon_port, width, height, refresh_rate):
    """Tests the given port using the given resolution.

    Args:
      dut_port: The DUT port to test.
      chameleon_port: The Chameleon port to test.
      width: The width of the resolution in pixels.
      height: The height of the resolution in pixels.
      refresh_rate: The screen refresh rate.
    """
    mode = ('%sx%s' % (width, height), '%sHz' % refresh_rate)
    logging.info(
        ('Testing DUT %s port on Chameleon %s port using mode %s...'),
        dut_port, chameleon_port, mode)
    self.ui.SetState(
        _('Testing DUT {dut_port} port on Chameleon {chameleon_port} port'
          ' using mode {mode}...',
          dut_port=dut_port,
          chameleon_port=chameleon_port,
          mode=mode))

    if not mode in EDIDS[chameleon_port]:
      self.fail('Invalid mode for %s: %s' % (chameleon_port, mode))

    with open(os.path.join(
        self.ui.GetStaticDirectoryPath(), EDIDS[chameleon_port][mode])) as f:
      edid = f.read()
    with self.chameleon.PortEdid(chameleon_port, edid):
      original_display, external_display = self.ProbeDisplay(chameleon_port)

      self.ui.SetState(
          _('Automated testing on {dut_port} to {chameleon_port} '
            'in progress...',
            dut_port=dut_port,
            chameleon_port=chameleon_port))

      if self.args.load_test_image:
        with self.NewWindow(
            external_display['workArea']['left'],
            external_display['workArea']['top']) as window_id:
          self.LoadTestImage(window_id, width, height)
          internal_image, chameleon_image = self.CaptureImages(
              dut_port, chameleon_port)
      else:
        internal_image, chameleon_image = self.CaptureImages(
            dut_port, chameleon_port)

    logging.info('Comparing captured images...')
    diff_image = ImageChops.difference(chameleon_image, internal_image)
    chameleon_image.save(self.CHAMELEON_IMAGE_PATH)
    internal_image.save(self.INTERNAL_IMAGE_PATH)

    logging.info('Cutting off ignored regions...')
    for r in self.args.ignore_regions:
      x, y, w, h = r
      draw = ImageDraw.Draw(diff_image)
      draw.rectangle((x, y, x + w, y + h), fill='rgb(0, 0, 0)')
      del draw
    diff_image.save(self.DIFF_IMAGE_PATH)
    histogram = diff_image.convert('L').histogram()
    pixel_diff_margin = 1 if self.args.downscale_to_tv_level else 0
    if sum(histogram[pixel_diff_margin + 1:]) > 0:
      self.ui.SetState([
          _('Captured images mismatch'), '<br><br>',
          '<image src="%s" width=%d height=%d></image>' %
          (self.ui.URLForFile(self.DIFF_IMAGE_PATH),
           original_display['workArea']['width'] * self.UI_IMAGE_RESIZE_RATIO,
           original_display['workArea']['height'] * self.UI_IMAGE_RESIZE_RATIO)
      ])
      # Wait 10 seconds for the operator to inspect the difference.
      self.Sleep(10)
      self.fail(('Captured image of port %s from Chameleon does not match '
                 'the internal framebuffer; check %s for the difference') %
                (chameleon_port, self.DIFF_IMAGE_PATH))

  def runTest(self):
    dut_port, chameleon_port, width, height, refresh_rate = self.args.test_info
    self.assertTrue(
        chameleon_port in PORTS,
        'Invalid port: %s; chameleon port must be one of %s' %
        (chameleon_port, PORTS))
    # Wait for 5 seconds for the fade-in visual effect.
    self.Sleep(5)
    self.TestPort(dut_port, chameleon_port, width, height, refresh_rate)
