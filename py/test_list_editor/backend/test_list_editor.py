#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import http.server
import logging
import os

# TODO(youcheng): Bundle non-standard libraries.
from jsonrpclib import SimpleJSONRPCServer

from cros.factory.test.env import paths
from cros.factory.test.i18n import translation
from cros.factory.test.test_lists import test_list_common
from cros.factory.test_list_editor.backend import common
from cros.factory.test_list_editor.backend import rpc
from cros.factory.utils import sys_utils


class Server:

  class HTTPRequestHandler(
      SimpleJSONRPCServer.SimpleJSONRPCRequestHandler,
      http.server.SimpleHTTPRequestHandler):

    def end_headers(self):
      if self.command == 'POST':
        # Allow CORS for front-end development.
        self.send_header('Access-Control-Allow-Origin', '*')
      http.server.BaseHTTPRequestHandler.end_headers(self)

  def __init__(self, port, dirs):
    self.port = port
    self.rpc = rpc.RPC(dirs)
    self.httpd = SimpleJSONRPCServer.SimpleJSONRPCServer(
        ('', port), Server.HTTPRequestHandler)
    self.httpd.register_introspection_functions()
    self.httpd.register_instance(self.rpc)

  def Start(self):
    logging.info('httpd started at http://localhost:%d/', self.port)
    self.httpd.serve_forever()


def _GetPrivateOverlayDir(board):
  def Locate(path, name):
    while True:
      if os.path.isdir(os.path.join(path, name)):
        return path
      if path == '/':
        return None
      path = os.path.dirname(path)

  if board:
    if sys_utils.InCrOSDevice():
      raise ValueError('BOARD may not be set in DUT environment.')
    repo_dir = Locate(common.SCRIPT_DIR, '.repo')
    if not repo_dir:
      raise RuntimeError('Not in a Chromium OS source tree.')
    private_overlay_dir = os.path.join(
        repo_dir, 'src', 'private-overlays', 'overlay-%s-private' % board)
  else:
    private_overlay_dir = Locate(os.getcwd(), '.git')
    if (not private_overlay_dir or
        os.path.basename(os.path.dirname(private_overlay_dir)) !=
        'private-overlays'):
      return None
  return private_overlay_dir


def _AddPrivateOverlay(dirs, board):
  private_overlay_dir = _GetPrivateOverlayDir(board)
  if private_overlay_dir is None:
    return

  base_dir = os.path.join(private_overlay_dir, common.PRIVATE_FACTORY_RELPATH)
  test_list_dir = os.path.join(base_dir, test_list_common.TEST_LISTS_RELPATH)
  if not os.path.isdir(test_list_dir):
    raise RuntimeError('Directory %r not found.' % test_list_dir)
  dirs.append((os.path.basename(private_overlay_dir).split('-')[1], base_dir))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '-b', '--board', help='Board name of the private overlay to open.')
  parser.add_argument(
      '-p', '--port', default=common.PORT, type=int,
      help='The port to listen for HTTP requests.')
  args = parser.parse_args()

  dirs = [('factory', paths.FACTORY_DIR)]
  _AddPrivateOverlay(dirs, args.board)

  if not os.path.isdir(common.STATIC_DIR):
    # TODO(youcheng): Pull static files automatically.
    raise RuntimeError('%r is required.' % common.STATIC_DIR)
  os.chdir(common.STATIC_DIR)

  if not os.path.isdir(translation.LOCALE_DIR):
    # TODO(youcheng): Provide an option to automatically build locale/.
    logging.warning(
        'Directory %r not found. There will be no i18n support.',
        translation.LOCALE_DIR)

  server = Server(args.port, dirs)
  server.Start()
  # TODO(youcheng): Launch browser automatically.


if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  main()
