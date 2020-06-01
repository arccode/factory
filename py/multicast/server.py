#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Multicast service to spawn uftp server"""

from __future__ import print_function

import os
import signal
import sys
import time

from cros.factory.utils import json_utils
from cros.factory.utils.process_utils import Spawn


UFTP_PATH = '/usr/bin/uftp'

CC_TYPE = 'tfmcc' # TCP friendly multicast congestion control
LOG_LEVEL = '0'
ROBUST_FACTOR = '50'
TTL = '10'

def SpawnUFTP(file_name, multicast_addr):
  addr, port = multicast_addr.split(':')

  cmd = [UFTP_PATH, '-M', addr, '-t', TTL, '-u', port, '-p', port,
         '-x', LOG_LEVEL, '-C', CC_TYPE, '-s', ROBUST_FACTOR, file_name]

  return Spawn(cmd)


def Main():
  assert len(sys.argv) == 3

  resource_dir = os.path.dirname(sys.argv[1])
  payloads = json_utils.LoadFile(sys.argv[1])
  multicast_dict = json_utils.LoadFile(sys.argv[2])['multicast']

  procs = []
  for component in multicast_dict:
    for part in multicast_dict[component]:
      file_name = payloads[component][part]
      file_path = os.path.join(resource_dir, file_name)
      multicast_addr = multicast_dict[component][part]

      args = (file_path, multicast_addr)

      p = SpawnUFTP(*args)

      procs.append({'process': p, 'args': args})

  def handler(signum, frame):
    del signum, frame  # unused
    for proc in procs:
      proc['process'].kill()
      proc['process'].wait()
    sys.exit(0)

  signal.signal(signal.SIGTERM, handler)

  while True:
    for proc in procs:
      args = proc['args']
      if proc['process'].poll() is not None:
        proc['process'] = SpawnUFTP(*args)
    time.sleep(1)


if __name__ == '__main__':
  Main()
