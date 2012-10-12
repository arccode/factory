#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''rsyncs goofy and runs on a remote device.'''

import argparse
import glob
import logging
import os
import re
import sys
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.utils.process_utils import Spawn


SRCROOT = os.environ['CROS_WORKON_SRCROOT']

ssh_command = None  # set in main
rsync_command = None


def SyncTestList(host, test_list=None):
  if test_list is None:
    logging.info('Checking release board on %s...', host)
    release = Spawn(ssh_command + [host, 'cat /etc/lsb-release'],
                    check_output=True, log=True).stdout_data
    match = re.search(r'^CHROMEOS_RELEASE_BOARD=(.+)', release, re.MULTILINE)
    if not match:
      logging.warn('Unable to determine release board')
      return None
    board = match.group(1)
    logging.info('Copying test_list from %s overlay', board)

    release_board = match.group(1)
    test_list_glob = os.path.join(
        os.environ['CROS_WORKON_SRCROOT'], 'src',
        '*-overlays', 'overlay-%s-*' % release_board,
        'chromeos-base', 'autotest-private-board', 'files', 'test_list')
    test_lists = glob.glob(test_list_glob)
    if not test_lists:
      logging.warn('Unable to find test list %s', test_list_glob)
      return
    test_list = test_lists[0]

  Spawn(rsync_command +
        [test_list, host + ':/usr/local/factory/custom/test_list'],
        check_call=True, log=True)

  return board


def main():
  parser = argparse.ArgumentParser(
      description='Rsync and run Goofy on a remote device.')
  parser.add_argument('host', metavar='HOST',
                      help='host to run on')
  parser.add_argument('-a', dest='clear_state', action='store_true',
                      help='clear Goofy state and logs on device')
  parser.add_argument('--autotest', dest='autotest', action='store_true',
                      help='also rsync autotest directory')
  parser.add_argument('--norestart', dest='restart', action='store_false',
                      help="don't restart Goofy")
  parser.add_argument('--hwid', action='store_true',
                      help="update HWID bundle")
  parser.add_argument('--test_list',
                      help=("test list to use (defaults to the one in "
                            "the board's overlay"))
  args = parser.parse_args()

  # Copy testing_rsa into a private file since otherwise ssh will ignore it
  testing_rsa = tempfile.NamedTemporaryFile(prefix='testing_rsa.')
  testing_rsa.write(open(os.path.join(
      SRCROOT, 'src/scripts/mod_for_test_scripts/ssh_keys/testing_rsa')).read())
  testing_rsa.flush()
  os.fchmod(testing_rsa.fileno(), 0400)

  global ssh_command, rsync_command  # pylint: disable=W0603
  ssh_command = ['ssh',
                 '-o', 'IdentityFile=%s' % testing_rsa.name,
                 '-o', 'UserKnownHostsFile=/dev/null',
                 '-o', 'User=root',
                 '-o', 'StrictHostKeyChecking=no']
  rsync_command = ['rsync', '-e', ' '.join(ssh_command)]

  logging.basicConfig(level=logging.INFO)

  Spawn(['make', '--quiet'], cwd=factory.FACTORY_PATH,
        check_call=True, log=True)
  board = SyncTestList(args.host, args.test_list)

  if args.autotest:
    Spawn(rsync_command +
          ['-aC', '--exclude', 'tests'] +
          [os.path.join(SRCROOT, 'src/third_party/autotest/files/client/'),
           '%s:/usr/local/autotest/' % args.host],
          check_call=True, log=True)

  Spawn(rsync_command +
        ['-aC', '--exclude', '*.pyc'] +
        [os.path.join(factory.FACTORY_PATH, x)
         for x in ('bin', 'py', 'py_pkg', 'sh', 'test_lists')] +
        ['%s:/usr/local/factory' % args.host],
        check_call=True, log=True)

  if args.hwid:
    if not board:
      sys.exit('Cannot update hwid without board')
    chromeos_hwid_path = os.path.join(
        os.path.dirname(factory.FACTORY_PATH), 'chromeos-hwid')
    Spawn(['./create_bundle', board.upper()],
          cwd=chromeos_hwid_path, check_call=True, log=True)
    Spawn(ssh_command + [args.host, 'bash'],
          stdin=open(os.path.join(chromeos_hwid_path,
                                  'hwid_bundle_%s.sh' % board.upper())),
          check_call=True, log=True)

  if args.restart:
    Spawn(ssh_command +
          [args.host, '/usr/local/factory/bin/restart'] +
          (['-a'] if args.clear_state else []),
          check_call=True, log=True)


if __name__ == '__main__':
  main()
