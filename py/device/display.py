# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.device import device_types


class DisplayError(Exception):
  """Error raised by the display module."""


class PortInfo:
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

  def __init__(self, connected=False, width=None, height=None, left=None,
               top=None):
    self.connected = connected
    self.width = width
    self.height = height
    self.left = left
    self.top = top


# pylint: disable=abstract-method
class LinuxDisplay(device_types.DeviceComponent):

  # syspath for backlight control
  BACKLIGHT_SYSPATH_PATTERN = '/sys/class/backlight/*'

  def GetPortInfo(self):
    """Gets the port info of all the display ports.

    Returns:
      A dict of port IDs to PortInfo instances of all the display ports.
    """
    raise NotImplementedError

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
    raise NotImplementedError

  def SetBacklightBrightness(self, level):
    """Sets the backlight brightness level.

    Args:
      level: A floating-point value in [0.0, 1.0] indicating the backlight
          brightness level.

    Raises:
      ValueError if the specified value is invalid.
    """
    if not 0.0 <= level <= 1.0:
      raise ValueError('Invalid brightness level.')
    interfaces = self._device.Glob(self.BACKLIGHT_SYSPATH_PATTERN)
    for i in interfaces:
      max_value = self._device.ReadFile(
          self._device.path.join(i, 'max_brightness'))
      new_value = int(level * float(max_value.strip()))
      self._device.WriteFile(
          self._device.path.join(i, 'brightness'), str(new_value))

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
