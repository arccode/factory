#!/usr/bin/env python2

# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""An XMLRPC server running on NUC in Dolphin Uno.

It provides interface to switch Plankton-Raiden's function and verify
DP output.
"""

import argparse
import glob
import logging
import os
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler
from SimpleXMLRPCServer import SimpleXMLRPCServer
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.test.fixture.dolphin import dolphin_bft_fixture
from cros.factory.test.fixture.dolphin import plankton_hdmi
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


DOLPHIN_RAIDEN_CONF = {
    # A dict of USB Type-A serial parameters.
    'usb_serial_params': {
        'driver': 'ftdi_sio',
        'baudrate': 115200,
        'bytesize': 8,
        'parity': 'N',
        'stopbits': 1,
        'timeout': 3,
        'writeTimeout': 3},
    'auto_pairing': True,
    # A string for Plankton FTDI driver product ID.
    'product_id': '500c'}


class DolphinXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
  """XMLRPC request handler for Dolphin Uno server.

  During the response of SimpleXMLRPCRequestHandler, it will try to obtain
  client's domain name among network for logging. Since Dolphin Uno system is
  just exclusive network and no DNS server, this step will take a long time and
  drag down overall efficiency. By fixing that, we derive this class and
  override the method to do without requesting domain name.
  """
  def address_string(self):
    """Return the client address formatted for logging.

    This method is overridden to do without requesting domain name.
    """
    host, _ = self.client_address[:2]
    return '%s (no getfqdn)' % host  # original: return socket.getfqdn(host)


def _PrepareGoldenImage():
  # TODO(deanliao): find a better way for DUT to specify golden image.
  base_dir = os.path.dirname(os.path.realpath(__file__))
  golden_tar_file = os.path.abspath(os.path.join(
      base_dir, '..', '..', 'pytests', 'raiden_display_static',
      'template.tar.gz'))
  file_utils.ExtractFile(golden_tar_file, base_dir)
  return os.path.abspath(os.path.join(base_dir, 'golden.png'))


def _CheckPlanktonHDMIPresentDaemon(uvc_port, uvc_device_name,
                                    check_interval_secs=5):
  """Checks Plankton HDMI present and notices operator if fail."""
  show_success_msg = True
  while True:
    if uvc_port:
      try:
        plankton_hdmi.PlanktonHDMI.FindUVCVideoDeviceIndex(uvc_port)
        camera_present = True
      except Exception:
        camera_present = False
    else:
      camera_present = bool(glob.glob(
          '/sys/bus/usb/drivers/uvcvideo/*/video4linux/video0'))

    if not camera_present:
      logging.error('Camera device is not detected. Please re-plug '
                    'Plankton HDMI %s !!!', uvc_device_name)
      show_success_msg = True
    elif show_success_msg:
      logging.info('OK!! Plankton HDMI %s detected.', uvc_device_name)
      show_success_msg = False
    time.sleep(check_interval_secs)


def RegisterDolphinFixture(server):
  """Registers API of DolphinBFTFixture."""
  dolphin = dolphin_bft_fixture.DolphinBFTFixture()
  dolphin.Init(**DOLPHIN_RAIDEN_CONF)
  server.register_instance(dolphin)


def RegisterPlanktonHDMI(server, golden, uvc_port):
  """Registers API of PlanktonHDMI and Dolphin DP test."""
  video_capturer = plankton_hdmi.PlanktonHDMI(
      uvc_video_index=None if uvc_port else 0,
      uvc_video_port=uvc_port,
      capture_fps=60)
  server.register_instance(video_capturer)

  # TODO(johnylin): pass-in golden_image_path through PlanktonHDMI constructor
  # and move VerifyDP() into PlanktonHDMI.
  golden_image_path = golden if golden else _PrepareGoldenImage()

  # TODO(stimim): setting return_corr=True does nothing now, should fix it.
  def VerifyDP(return_corr=False):
    """Verifies DP output.

    Args:
      return_corr: Set True for returning corr_values directly.

    Returns:
      If return_corr is False, return True if DP output is quite similar to
      golden image. If return_corr is True, return correlation values of DP
      output and golden image.
    """
    return video_capturer.CaptureCompare(
        golden_image_path, (0.8, 0.8, 0.8), return_corr)

  server.register_function(VerifyDP)


def main():
  parser = argparse.ArgumentParser(description='Dolphin Uno server')
  parser.add_argument('--addr', default='0.0.0.0',
                      help='Server binding IP address.')
  parser.add_argument('--port', default=9999, type=int,
                      help='Server binding port.')
  parser.add_argument('--dolphin', action='store_true',
                      help='Add DolphinBFTFixture control')
  parser.add_argument('--hdmi', action='store_true',
                      help='Add Plankton-HDMI capture control')
  parser.add_argument('--uvc_port', default=None, type=str,
                      help='UVC device port path, ex. 3-1. If not specified, '
                      'video0 will be used as default device.')
  parser.add_argument('--uvc_device_name', default='', type=str,
                      help='UVC device name for showing on messages.')
  parser.add_argument('--checkhdmi', action='store_true',
                      help='Periodic checking Plankton-HDMI present')
  parser.add_argument('--golden',
                      help='Golden image path. Default using golden.png in '
                      'py/test/pytests/raiden_display_static/template.tar.gz')
  parser.add_argument('--debug', action='store_true', help='Logging DEBUG')

  args = parser.parse_args()

  logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

  server = SimpleXMLRPCServer((args.addr, args.port),
                              requestHandler=DolphinXMLRPCRequestHandler,
                              allow_none=True)
  server.register_introspection_functions()

  if args.dolphin:
    RegisterDolphinFixture(server)

  if args.hdmi:
    RegisterPlanktonHDMI(server, args.golden, args.uvc_port)
    if args.checkhdmi:
      process_utils.StartDaemonThread(
          target=_CheckPlanktonHDMIPresentDaemon,
          args=(args.uvc_port, args.uvc_device_name))

  logging.info('XMLRPC server listening on %s:%d', args.addr, args.port)
  server.serve_forever()


if __name__ == "__main__":
  main()
