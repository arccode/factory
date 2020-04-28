#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Multicast service to spawn uftp server"""

from __future__ import print_function

from multiprocessing import Process
import os
import sys

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

  while True:
    Spawn(cmd, call=True)


def Main():
  assert len(sys.argv) == 3

  resource_dir = os.path.dirname(sys.argv[1])
  payloads = json_utils.LoadFile(sys.argv[1])
  multicast_dict = json_utils.LoadFile(sys.argv[2])['multicast']

  for component in multicast_dict:
    for part in multicast_dict[component]:
      file_name = payloads[component][part]
      file_path = os.path.join(resource_dir, file_name)
      multicast_addr = multicast_dict[component][part]

      p = Process(name=file_name, target=SpawnUFTP,
                  args=(file_path, multicast_addr))
      p.start()


if __name__ == '__main__':
  Main()
