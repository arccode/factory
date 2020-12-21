#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""A tool to quickly extract HWID and serial no. from DUT."""

import argparse
from http import server as http_server
import logging
import sys

from cros.factory.hwid_extractor import request_handler


def ParseArguments(raw_args):
  """Parse command line arguments."""
  parser = argparse.ArgumentParser()
  parser.add_argument('-p', '--port', type=int, default=8000,
                      help='Port to run the http server.')
  parser.add_argument('-v', '--verbosity', action='count', default=0,
                      help='Logging verbosity.')
  args = parser.parse_args(raw_args)
  return args


def Main(raw_args):
  args = ParseArguments(raw_args)
  logging.basicConfig(level=logging.WARNING - args.verbosity * 10)
  server_address = ('localhost', args.port)
  server = http_server.HTTPServer(server_address,
                                  request_handler.RequestHandler)
  logging.info('Starting HWID Extractor server on http://localhost:%d',
               args.port)
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    pass
  server.server_close()
  logging.info('HWID Extractor server stopped.')


if __name__ == '__main__':
  sys.exit(Main(sys.argv[1:]))
