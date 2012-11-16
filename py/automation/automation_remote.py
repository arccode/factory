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
import signal
import tempfile
import time
import thread

import factory_common # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess


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
  parser.add_argument('--testlist', default=None,
                      help='the path of the customize testlist to use'
                           '(if not specified, use default testlist')
  parser.add_argument('--shopfloor_ip', default='192.168.1.254')
  parser.add_argument('--shopfloor_port', default=8082)
  parser.add_argument('--shopfloor_dir', default=None)
  parser.add_argument('--logdata_dir', help='the local path where the logs are'
                      ' copied to')
  parser.add_argument('--serial_number',
                      help='the serial number of the DUT')

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

  # if giving test_list, copy the file to DUT
  if args.testlist:
    Spawn(scp_command +
          [args.testlist, args.device +
           ':/usr/local/factory/custom/test_list'],
          check_call=True, log=True)

  # Update shopfloor address on the device test_list
  Spawn(ssh_command +
        [args.device,
         "sed -i \"s/^options.shopfloor_server_url = '.*'/"
         "options.shopfloor_server_url = 'http:\/\/%s:%s\/'/g\" "
         "/usr/local/factory/custom/test_list" %
         (args.shopfloor_ip, args.shopfloor_port)],
         check_call=True, log=True)

  # Copy new config file
  if args.config:
    Spawn(scp_command +
          [args.config, args.device +
           ':/usr/local/factory/py/automation/automation.config'],
          check_call=True, log=True)

  # Replace the serial number
  if args.serial_number:
    Spawn(ssh_command +
          [args.device,
           "sed -i 's/SERIAL_NUMBER/%s/g' "
           "/usr/local/factory/py/automation/automation.config" %
           args.serial_number],
          check_call=True, log=True)

  # Turn on automation
  Spawn(ssh_command +
        [args.device, 'touch /var/factory/state/factory.automation'],
         check_call=True, log=True)
  # Restart factory on device
  Spawn(ssh_command +
        [args.device, '/usr/local/factory/bin/restart'],
         check_call=True, log=True)

  # rsync log on device
  def SyncLog():
    while True:
      time.sleep(0.1)
      Spawn(rsync_command +
            ['%s:/var/factory' % args.device, args.logdata_dir],
            ignore_stdout=True, ignore_stderr=True)
  thread.start_new_thread(SyncLog, ())

  def handler(signum, frame):  # pylint: disable=W0613
    raise SystemExit
  signal.signal(signal.SIGTERM, handler)

  shopfloor = None
  try:
    # Check whether use specific shopfloor directory
    # if not, send message to user
    if args.shopfloor_dir:
      logging.info('Shopfloor directory: ' + args.shopfloor_dir)
      data_dir = os.path.join(args.shopfloor_dir, 'shopfloor_data')
      logging.info('Shopfloor data directory: ' + data_dir)
      shopfloor = Spawn(['%s/shopfloor_server.sh' % args.shopfloor_dir,
                         '--simple',
                         '--auto-archive-logs=',
                         '--address=%s' % args.shopfloor_ip,
                         '--port=%s' % args.shopfloor_port,
                         '--data-dir=%s' % data_dir], log=True)
      shopfloor.wait()
    else:
      logging.info('Shopfloor server is not started')
  except:  # pylint: disable=W0702
    logging.warning('Shopfloor error. Possibly port already in use?')
  finally:
    if shopfloor:
      TerminateOrKillProcess(shopfloor)


if __name__ == '__main__':
  Main()
