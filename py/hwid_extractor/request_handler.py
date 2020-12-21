# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""A tool to quickly extract HWID and serial no. from DUT."""

from http import server as http_server
import os


WWW_ROOT_DIR = os.path.join(os.path.dirname(__file__), 'www')


class RequestHandler(http_server.SimpleHTTPRequestHandler):
  """Implementation of the request handler."""

  def __init__(self, *args, **kargs):
    #TODO(chungsheng): Use argument `directory` after python3.7
    os.chdir(WWW_ROOT_DIR)
    super().__init__(*args, **kargs)
