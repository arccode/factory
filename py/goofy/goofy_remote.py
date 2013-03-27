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


def GetBoard(host):
  logging.info('Checking release board on %s...', host)
  release = Spawn(ssh_command + [host, 'cat /etc/lsb-release'],
                  check_output=True, log=True).stdout_data
  match = re.search(r'^CHROMEOS_RELEASE_BOARD=(.+)', release, re.MULTILINE)
  if not match:
    logging.warn('Unable to determine release board')
    return None
  return match.group(1)


def SyncTestList(host, board, test_list,
                 clear_factory_environment, clear_password, shopfloor_host):
  # Uses dash in board name for overlay directory name
  board_dash = board.replace('_', '-')

  if test_list is None:
    test_list_globs = []
    for x in [['chromeos-factory-board', 'files', 'test_lists',
               'test_list'],
              ['autotest-private-board', 'files', 'test_list']]:
      test_list_globs.append(
        os.path.join(
            os.environ['CROS_WORKON_SRCROOT'], 'src',
            '*-overlays', 'overlay-%s-*' % board_dash,
            'chromeos-base', *x))
      test_list_globs.append(
        os.path.join(
            os.environ['CROS_WORKON_SRCROOT'], 'src',
            '*-overlays', 'overlay-variant-%s-*' % board_dash,
            'chromeos-base', *x))

    test_lists = sum([glob.glob(x) for x in test_list_globs], [])
    if not test_lists:
      logging.warn('Unable to find test list %s', test_list_globs)
      return
    test_list = test_lists[0]
    logging.info('Using test list %s', test_list)

  old_test_list_data = test_list_data = open(test_list).read()
  if clear_factory_environment:
    test_list_data = test_list_data.replace(
        '_FACTORY_ENVIRONMENT = True',
        '_FACTORY_ENVIRONMENT = False')
  if clear_password:
    test_list_data += '\noptions.engineering_password_sha1 = None\n'
  if shopfloor_host:
    test_list_data += '\noptions.shopfloor_server_url = "http://%s:8082/"\n' % (
        shopfloor_host)

  if old_test_list_data != test_list_data:
    tmp_test_list = tempfile.NamedTemporaryFile(prefix='test_list.', bufsize=0)
    tmp_test_list.write(test_list_data)
    test_list = tmp_test_list.name

  test_list_dir = (
      'custom' if 'autotest-private-board' in test_list
      else 'test_lists')

  Spawn(rsync_command +
        [test_list, host + ':/usr/local/factory/%s/test_list' % test_list_dir],
        check_call=True, log=True)

  return board


def main():
  parser = argparse.ArgumentParser(
      description='Rsync and run Goofy on a remote device.')
  parser.add_argument('host', metavar='HOST',
                      help='host to run on')
  parser.add_argument('-a', dest='clear_state', action='store_true',
                      help='clear Goofy state and logs on device')
  parser.add_argument('-e', dest='clear_factory_environment',
                      action='store_true',
                      help='set _FACTORY_ENVIRONMENT = False in test_list')
  parser.add_argument('-p', dest='clear_password',
                      action='store_true',
                      help='remove password from test_list')
  parser.add_argument('-s', dest='shopfloor_host',
                      help='set shopfloor host')
  parser.add_argument('--board', '-b', dest='board',
                      help='board to use (default: auto-detect')
  parser.add_argument('--autotest', dest='autotest', action='store_true',
                      help='also rsync autotest directory')
  parser.add_argument('--norestart', dest='restart', action='store_false',
                      help="don't restart Goofy")
  parser.add_argument('--hwid', action='store_true',
                      help="update HWID bundle")
  parser.add_argument('--run', '-r', dest='run_test',
                      help="the test to run on device")
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
  board = args.board or GetBoard(args.host)

  if args.autotest:
    Spawn(rsync_command +
          ['-aC', '--exclude', 'tests'] +
          [os.path.join(SRCROOT, 'src/third_party/autotest/files/client/'),
           '%s:/usr/local/autotest/' % args.host],
          check_call=True, log=True)

  board_dash = board.replace('_', '-')
  private_paths = [os.path.join(SRCROOT, 'src', 'private-overlays',
                                'overlay-%s-private' % board_dash,
                                'chromeos-base', 'chromeos-factory-board',
                                'files'),
                   os.path.join(SRCROOT, 'src', 'private-overlays',
                                'overlay-variant-%s-private' % board_dash,
                                'chromeos-base', 'chromeos-factory-board',
                                'files')]

  for private_path in private_paths:
    if os.path.isdir(private_path):
      Spawn(rsync_command +
            ['-aC', '--exclude', 'bundle'] +
            [private_path + '/', '%s:/usr/local/factory/' % args.host],
            check_call=True, log=True)

  Spawn(rsync_command +
        ['-aC', '--exclude', '*.pyc'] +
        [os.path.join(factory.FACTORY_PATH, x)
         for x in ('bin', 'py', 'py_pkg', 'sh', 'test_lists', 'third_party')] +
        ['%s:/usr/local/factory' % args.host],
        check_call=True, log=True)

  SyncTestList(args.host, board, args.test_list,
               args.clear_factory_environment, args.clear_password,
               args.shopfloor_host)

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
          [args.host, '/usr/local/factory/bin/factory_restart'] +
          (['-a'] if args.clear_state else []),
          check_call=True, log=True)

  if args.run_test:
    Spawn(ssh_command +
          [args.host, 'goofy_rpc', r'RunTest\(\"%s\"\)' % args.run_test],
          check_call=True, log=True)

if __name__ == '__main__':
  main()
