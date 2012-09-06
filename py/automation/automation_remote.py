#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''A script to run on host to invoke factory test automation on device

The script (run in chroot) will:
* Update the shopfloor server address on device
* Copy the automation config into device (if specified)
* Turn on automation and restart factory on device
* Run shopfloor server on host
* Maintain a copy of the device log
'''

import argparse
import logging
import os
import shutil
import socket
import tempfile
import time
import thread

import factory_common # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn


SRCROOT = os.environ['CROS_WORKON_SRCROOT']


def Main():
  description = 'A script to run on host '\
                'to invoke factory test automation on device'
  parser = argparse.ArgumentParser(description)

  parser.add_argument('device', metavar='DEVICE',
                      help='device to run on')
  parser.add_argument('--config',
                      help='the path of the automation config file to use '
                           '(if not specified, '
                           'use automation/automation.config on device)')
  parser.add_argument('--shopfloor_ip', default='192.168.123.1')
  parser.add_argument('--shopfloor_port', default=None)

  args = parser.parse_args()

  logging.basicConfig(level=logging.INFO)

  # Copy testing_rsa into a private file since otherwise ssh will ignore it
  testing_rsa = tempfile.NamedTemporaryFile(prefix='testing_rsa.')
  testing_rsa.write(open(os.path.join(
      SRCROOT, 'src/scripts/mod_for_test_scripts/ssh_keys/testing_rsa')).read())
  testing_rsa.flush()
  os.fchmod(testing_rsa.fileno(), 0400)

  connection_option = ['-o', 'IdentityFile=%s' % testing_rsa.name,
                       '-o', 'UserKnownHostsFile=/dev/null',
                       '-o', 'User=root',
                       '-o', 'StrictHostKeyChecking=no']
  scp_command = ['scp'] + connection_option
  ssh_command = ['ssh'] + connection_option
  rsync_command = ['rsync', '-a', '--quiet', '-e',  ' '.join(ssh_command)]

  # Update shopfloor address on the device test_list
  Spawn(ssh_command +
        [args.device,
         "sed -i \"s/^_SHOP_FLOOR_SERVER_URL = '.*'/"
         "_SHOP_FLOOR_SERVER_URL = 'http:\/\/%s:%s\/'/g\" "
         "/usr/local/factory/custom/test_list" %
         (args.shopfloor_ip, args.shopfloor_port)],
         check_call=True, log=True)

  # Copy new config file
  if args.config:
    Spawn(scp_command +
          [args.config, args.device +
           ':/usr/local/factory/py/automation/automation.config'],
          check_call=True, log=True)
  # Turn on automation
  Spawn(ssh_command +
        [args.device, 'touch /var/factory/state/factory.automation'],
         check_call=True, log=True)
  # Restart factory on device
  Spawn(ssh_command +
        [args.device, '/usr/local/factory/bin/restart'],
         check_call=True, log=True)

  # Shopfloor data and /var/factory will be placed in this dir
  temp_dir = tempfile.mkdtemp(prefix='shopfloor_')

  # rsync log on device
  def SyncLog():
    while True:
      time.sleep(0.1)
      Spawn(rsync_command +
            ['%s:/var/factory' % args.device, temp_dir],
            ignore_stdout=True, ignore_stderr=True)
  thread.start_new_thread(SyncLog, ())

  if args.shopfloor_port is None:
    # Find unused port
    s = socket.socket()
    s.bind((args.shopfloor_ip, 0))
    args.shopfloor_port = s.getsockname()[1]
    s.close()

  # Run shopfloor_server
  shopfloor_dir = os.path.join(SRCROOT,
                               'src/platform/factory-utils/factory_setup')
  csv_file = os.path.join(shopfloor_dir,
                        'testdata/shopfloor/devices.csv')
  shutil.copy(csv_file, temp_dir)
  try:
    Spawn(['%s/shopfloor_server.py' % shopfloor_dir,
           '--module=shopfloor.simple.ShopFloor',
           '--data-dir=%s' % temp_dir,
           '--address=%s' % args.shopfloor_ip,
           '--port=%s' % args.shopfloor_port],
           check_call=True, log=True)
  except:  # pylint: disable=W0702
    logging.warning('Shopfloor error. Possibly port already in use?')

if __name__ == '__main__':
  Main()
