# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Run minijack frontend as FastCGI application."""


import logging
import multiprocessing
from flup.server.fcgi_fork import WSGIServer

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.frontend import wsgi
from cros.factory.shopfloor.launcher import constants


LOCALHOST = '127.0.0.1'
# TODO(rong): Move to constants or make it an option.
MINIJACK_FCGI_PORT = constants.DEFAULT_BIND_PORT + 4

def main():
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  bind_address = (LOCALHOST, MINIJACK_FCGI_PORT)
  cpu_count = multiprocessing.cpu_count()
  fork_args = {
      'minSpare': 1,
      'maxSpare': min(cpu_count * 2, 8),
      'maxChildren': max(cpu_count * 4, 16),
      'maxRequests': 64}
  server = WSGIServer(wsgi.application, bindAddress=bind_address, **fork_args)
  server.run()


if __name__ == '__main__':
  main()
