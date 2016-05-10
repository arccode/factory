#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from __future__ import print_function

import re

import factory_common  # pylint: disable=W0611
from cros.factory.test.dut import component
from cros.factory.test.utils import drm_utils
from cros.factory.utils import sys_utils

from cros.factory.external import PIL


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


class Display(component.DUTComponent):

  # syspath for backlight control
  BACKLIGHT_SYSPATH_PATTERN = '/sys/class/backlight/*'

  def GetPortInfo(self):
    """Gets the port info of all the display ports.

    Returns:
      A dict of port IDs to PortInfo instances of all the display ports.
    """
    ports = {}

    if sys_utils.IsFreon(self._dut):
      # TODO(hungte) Currently Freon+DRM can't run remotely. We need a
      # DUT-based implementation.
      if not self._dut.link.IsLocal():
        raise DisplayError('Cannot support Freon+DRM remotely.')
      d = None
      for p in sorted(self._dut.Glob('/dev/dri/*')):
        d = drm_utils.DRMFromPath(p)
        if d.resources:
          break
      else:
        raise DisplayError('Can\'t find suitable DRM devices')

      for connector in d.resources.connectors:
        port_info = PortInfo(
            connected=(connector.status == 'connected'))
        port_info.drm_handle = d
        port_info.drm_connector = connector
        if port_info.connected:
          fb = connector.GetAssociatedFramebuffer()
          if fb:
            port_info.width = fb.width
            port_info.height = fb.height
            port_info.drm_fb = fb
          else:
            # Sometimes display may response framebuffer info slowly, so
            # we should assume the port is not connected yet and retry later.
            port_info.connected = False
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

      xrandr_output = self._dut.CheckOutput(['xrandr', '-d', ':0'])
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

  def CaptureFramebuffer(self, port, box=None, downscale=False):
    """Captures a RGB image of the framebuffer on the given display port.

    On freon boards the screenshots are captured from DRM framebuffer directly.
    On non-freon boards the screenshots are captured using xwd.

    Args:
      port: The ID of the display port to capture.
      box: A tuple (left, upper, right, lower) of the two coordinates to crop
          the image from.
      downscale: Whether to downscale the captured framebuffer to RGB 16-235
          TV-scale.

    Returns:
      A PIL.Image object of the captured RGB image.
    """
    port_info_dict = self.GetPortInfo()
    if port not in port_info_dict:
      raise DisplayError('Unknown port %s; valid ports are: %r' %
                         (port, port_info_dict.keys()))
    port_info = port_info_dict[port]
    if not port_info.connected:
      raise DisplayError('Port %s is not connected')

    image = None
    if sys_utils.IsFreon(self._dut):
      if not port_info.drm_fb:
        raise DisplayError(
            'Connector %s does not have an associated framebuffer' % port)
      image = port_info.drm_fb.AsRGBImage()
    else:
      with self._dut.temp.TempFile(suffix='.rgb') as temp:
        # 'convert' (ImageMagick) can be executed locally while xwd must run on
        # remote DUT. We haven't seen a project that is using xwd without
        # ImageMagick installed so here we try to run convert remotely.  Can be
        # revised to run locally when needed.
        self._dut.CheckCall('xwd -d :0 -root | convert - "%s"' % temp)
        image = PIL.Image.fromstring(
            'RGB', (port_info.x_fb_width, port_info.x_fb_height),
            self._dut.ReadFile(temp))
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

      image = PIL.Image.eval(image, Downscale)

    return image

  def SetBacklightBrightness(self, level):
    """Sets the backlight brightness level.

    Args:
      level: A floating-point value in [0.0, 1.0] indicating the backlight
          brightness level.

    Raises:
      ValueError if the specified value is invalid.
    """
    if not (level >= 0.0 and level <= 1.0):
      raise ValueError('Invalid brightness level.')
    interfaces = self._dut.Glob(self.BACKLIGHT_SYSPATH_PATTERN)
    for i in interfaces:
      max_value = self._dut.ReadFile(self._dut.path.join(i, 'max_brightness'))
      new_value = int(level * float(max_value.strip()))
      self._dut.WriteFile(self._dut.path.join(i, 'brightness'), str(new_value))

  def DisplayImage(self, image_path):
    """Display image file on the screen.

    Since there is no standard way to display image file. We may need to
    implmenent it for each board if it wants to use this API.

    Args:
      image_path: Image file path on DUT.
    """
    raise NotImplementedError

  def StopDisplayImage(self):
    """Stop displaying Image on DUT.

    It's a cleanup function. For some DUTs they may need display process running
    during the display time. This function is used to clean the process.
    """
    pass
