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
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import utils


SRCROOT = os.environ['CROS_WORKON_SRCROOT']
ssh_options = None  # set in main


def SyncTestList(host, test_list=None):
  if test_list is None:
    logging.info('Checking release board on %s...', host)
    release = utils.LogAndCheckOutput(['ssh'] + ssh_options +
                                      [host, 'cat /etc/lsb-release'])
    match = re.search(r'^CHROMEOS_RELEASE_BOARD=(.+)', release, re.MULTILINE)
    if not match:
      logging.warn('Unable to determine release board')
      return
    board = match.group(1)
    logging.info('Board is %s; copying test_list from overlay', board)

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

  utils.LogAndCheckCall(['rsync', test_list,
                         host + ':/usr/local/factory/custom/test_list'])


def main():
  parser = argparse.ArgumentParser(
      description='Rsync and run Goofy on a remote device.')
  parser.add_argument('host', metavar='HOST',
                      help='host to run on')
  parser.add_argument('-a', dest='clear_state', action='store_true',
                      help='clear Goofy state and logs on device')
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

  global ssh_options  # pylint: disable=W0603
  ssh_options = ['-o', 'IdentityFile=%s' % testing_rsa.name,
                 '-o', 'UserKnownHostsFile=/dev/null',
                 '-o', 'User=root',
                 '-o', 'StrictHostKeyChecking=no']

  logging.basicConfig(level=logging.INFO)
  os.environ['RSYNC_CONNECT_PROG'] = 'ssh ' + ' '.join(ssh_options)

  utils.LogAndCheckCall(['make', '--quiet'], cwd=factory.FACTORY_PATH)
  SyncTestList(args.host, args.test_list)

  utils.LogAndCheckCall(['rsync', '-aC', '--exclude', '*.pyc'] +
                        [os.path.join(factory.FACTORY_PATH, x)
                         for x in ('bin', 'py', 'py_pkg', 'sh', 'test_lists')] +
                        ['%s:/usr/local/factory' % args.host])

  utils.LogAndCheckCall(['ssh'] + ssh_options +
                        [args.host, '/usr/local/factory/bin/restart'] +
                        (['-a'] if args.clear_state else []))


if __name__ == '__main__':
  main()
