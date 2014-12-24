# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from __future__ import print_function

import re

from PIL import Image

import factory_common  # pylint: disable=W0611
from cros.factory.system import drm
from cros.factory.test import utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class DisplayError(Exception):
  """Error raised by the display module."""


class PortInfo(object):
  """A class for holding relevant display port info.

  Attributes:
    connected: True if the port is connected; False otherwise.
    width: The width of the associated framebuffer; None if no framebuffer is
        associated.
    height: The height of the associated framebuffer; None if no framebuffer is
        associated.
    left: The position to the left of the associated framebuffer; None if not
        applicable.
    top: The position to the top of the associated framebuffer; None if not
        applicable.
  """
  # The following attributes are only used by X-based boards.
  x_fb_width = None
  x_fb_height = None

  # The following attributes are only used by freon boards.
  drm_handle = None
  drm_connector = None
  drm_fb = None

  def __init__(self, connected=False, width=None, height=None, left=None,
               top=None):
    self.connected = connected
    self.width = width
    self.height = height
    self.left = left
    self.top = top


def GetPortInfo():
  """Gets the port info of all the display ports.

  Returns:
    A dict of port IDs to PortInfo instances of all the display ports.
  """
  ports = {}

  if utils.IsFreon():
    d = drm.DRMFromMinor(0)
    for connector in d.resources.connectors:
      port_info = PortInfo(
          connected=(connector.status == 'connected'))
      port_info.drm_handle = d
      port_info.drm_connector = connector
      if port_info.connected:
        fb = connector.GetAssociatedFramebuffer()
        port_info.width = fb.width
        port_info.height = fb.height
        port_info.drm_fb = fb
      ports[connector.id] = port_info

  else:
    SCREEN_REGEXP = re.compile(
        (r'Screen 0: minimum \d+ x \d+, '
         r'current (?P<width>\d+) x (?P<height>\d+), maximum \d+ x \d+'),
        re.MULTILINE)
    PORT_REGEXP = re.compile(
        (r'(?P<name>\w+) (?P<connected>connected|disconnected) '
         r'((?P<width>\d+)x(?P<height>\d+)\+(?P<left>\d+)\+(?P<top>\d+))?'),
        re.MULTILINE)

    xrandr_output = process_utils.CheckOutput(['xrandr', '-d', ':0'])
    match_obj = SCREEN_REGEXP.search(xrandr_output)
    x_fb_width = int(match_obj.group('width'))
    x_fb_height = int(match_obj.group('height'))

    for p in PORT_REGEXP.finditer(xrandr_output):
      groupdict = p.groupdict()
      # Convert strings to integers.
      for x in ('width', 'height', 'top', 'left'):
        value = groupdict[x]
        groupdict[x] = int(value) if value is not None else value

      port_info = PortInfo(
          connected=(groupdict['connected'] == 'connected'),
          width=groupdict['width'], height=groupdict['height'],
          left=groupdict['left'], top=groupdict['top'])
      port_info.x_fb_width = x_fb_width
      port_info.x_fb_height = x_fb_height
      ports[groupdict['name']] = port_info

  return ports

def CaptureFramebuffer(port, box=None, downscale=False):
  """Captures a RGB image of the framebuffer on the given display port.

  On freon boards the screenshots are captured from DRM framebuffer directly.
  On non-freon boards the screenshots are captured using xwd.

  Args:
    port: The ID of the display port to capture.
    box: A tuple (left, upper, right, lower) of the two coordinates to crop the
        image from.
    downscale: Whether to downscale the captured framebuffer to RGB 16-235
        TV-scale.

  Returns:
    A PIL.Image object of the captured RGB image.
  """
  port_info_dict = GetPortInfo()
  if port not in port_info_dict:
    raise DisplayError('Unknown port %s; valid ports are: %r' %
                       (port, port_info_dict.keys()))
  port_info = port_info_dict[port]
  if not port_info.connected:
    raise DisplayError('Port %s is not connected')

  image = None
  if utils.IsFreon():
    if not port_info.drm_fb:
      raise DisplayError(
          'Connector %s does not have an associated framebuffer' % port)
    image = port_info.drm_fb.AsRGBImage()
  else:
    with file_utils.UnopenedTemporaryFile(suffix='.rgb') as temp:
      process_utils.Spawn('xwd -d :0 -root | convert - "%s"' % temp,
                          shell=True, check_call=True)
      with open(temp) as f:
        image = Image.fromstring(
            'RGB', (port_info.x_fb_width, port_info.x_fb_height), f.read())
      # The captured image contains the giant X framebuffer. We need to crop
      # the captured framebuffer.
      image = image.crop((port_info.left, port_info.top,
                          port_info.left + port_info.width,
                          port_info.top + port_info.height))

  if box is not None:
    image = image.crop(box)

  if downscale:
    def Downscale(p):
      """Downscale the given pixel from PC-scale to TV-scale."""
      return (p - 128) * 110 / 128 + 126

    image = Image.eval(image, Downscale)

  return image
