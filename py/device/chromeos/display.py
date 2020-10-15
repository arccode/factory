# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.device import display
from cros.factory.test.utils import drm_utils

from cros.factory.external import PIL

if PIL.MODULE_READY:
  from cros.factory.external.PIL import Image  # pylint: disable=no-name-in-module


class DisplayError(Exception):
  """Error raised by the display module."""


# pylint: disable=abstract-method
class ChromeOSPortInfo(display.PortInfo):
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
  # The following attributes are only used by freon boards.
  drm_handle = None
  drm_connector = None
  drm_fb = None


class ChromeOSDisplay(display.LinuxDisplay):

  def GetPortInfo(self):
    """Gets the port info of all the display ports.

    Returns:
      A dict of port IDs to PortInfo instances of all the display ports.
    """
    ports = {}
    # TODO(hungte) Currently Freon+DRM can't run remotely. We need a
    # DUT-based implementation.
    if not self._device.link.IsLocal():
      raise DisplayError('Cannot support Freon+DRM remotely.')
    d = None
    for p in sorted(self._device.Glob('/dev/dri/*')):
      d = drm_utils.DRMFromPath(p)
      if d.resources:
        break
    else:
      raise DisplayError('Can\'t find suitable DRM devices')
    for connector in d.resources.connectors:
      port_info = display.PortInfo(
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
    return ports

  def CaptureFramebuffer(self, port, box=None, downscale=False):
    """Captures a RGB image of the framebuffer on the given display port.

    Screenshots are captured from DRM framebuffer directly.

    Args:
      port: The ID of the display port to capture.
      box: A tuple (left, upper, right, lower) of the two coordinates to crop
          the image from.
      downscale: Whether to downscale the captured framebuffer to RGB 16-235
          TV-scale.

    Returns:
      A Image.Image object of the captured RGB image.
    """
    port_info_dict = self.GetPortInfo()
    if port not in port_info_dict:
      raise DisplayError('Unknown port %s; valid ports are: %r' %
                         (port, list(port_info_dict)))
    port_info = port_info_dict[port]
    if not port_info.connected:
      raise DisplayError('Port %s is not connected')

    image = None
    if not port_info.drm_fb:
      raise DisplayError(
          'Connector %s does not have an associated framebuffer' % port)
    image = port_info.drm_fb.AsRGBImage()

    if box is not None:
      image = image.crop(box)

    if downscale:
      def Downscale(p):
        """Downscale the given pixel from PC-scale to TV-scale."""
        return (p - 128) * 110 // 128 + 126

      image = Image.eval(image, Downscale)

    return image
