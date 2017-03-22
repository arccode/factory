#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import glob
import logging
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(__file__)
FACTORY_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
PO_DIR = os.path.join(FACTORY_DIR, 'po')
SRC_DIR = os.path.abspath(os.path.join(FACTORY_DIR, '..', '..'))


def InChroot():
  """Returns True if currently in the chroot."""
  return 'CROS_WORKON_SRCROOT' in os.environ


def GetTargetBaseDir(board):
  if board is None:
    return FACTORY_DIR
  cmd = ('equery-{board} which factory-board ||'
         ' equery-{board} which chromeos-factory-board').format(board=board)
  if not InChroot():
    cmd = 'cros_sdk sh -c "{cmd}" 2>/dev/null'.format(cmd=cmd)

  target_path = subprocess.check_output(cmd, shell=True)
  target_path = os.path.abspath(os.path.join(target_path, '..', 'files'))

  if not InChroot():
    relpath = os.path.relpath(target_path, '/mnt/host/source/src/')
    target_path = os.path.join(SRC_DIR, relpath)

  return target_path


def DoPoMake(locale, board, action):
  env = {'LOCALE': locale}
  if board is not None:
    env['BOARD'] = board

  cmd = ['make', '-C', PO_DIR, action]
  if board is not None and not InChroot():
    cmd = ['cros_sdk'] + ['%s=%s' % (k, v) for k, v in env.iteritems()] + [
        'make', '-C', '/mnt/host/source/src/platform/factory/po/', action
    ]
    env = {}

  env.update(os.environ)
  with open('/dev/null', 'wb') as devnull:
    subprocess.check_call(cmd, env=env, stdout=devnull)


def main():
  parser = argparse.ArgumentParser(
      description='Migrate old test list to use new i18n library.')
  parser.add_argument('-b', '--board', help='The target board overlay.')
  args = parser.parse_args()

  logging.basicConfig(
      format='[%(levelname).1s] %(asctime)-8s L%(lineno)-3d %(message)s',
      datefmt='%H:%M:%S',
      level=logging.INFO)

  if subprocess.call('which yapf >/dev/null 2>&1', shell=True):
    logging.error('yapf not found, install it by "pip install yapf".')
    sys.exit(1)

  board = args.board
  locale = 'zh-CN'
  logging.info('board = %s', board)

  target = GetTargetBaseDir(args.board)
  target_po = os.path.join(target, 'po', locale + '.po')

  if not os.path.exists(target_po):
    logging.info("Target po %s doesn't exist, generating...", target_po)
    action = 'init'
    if os.path.exists(os.path.join(PO_DIR, locale + '.po')):
      action = 'update'
    DoPoMake(locale, board, action)

  assert os.path.exists(
      target_po), "%s doesn't exists... Something went wrong" % target_po

  test_list_files = glob.glob(
      os.path.join(target, 'py', 'test', 'test_lists', '*.py'))

  logging.info('Running migrate script...')
  subprocess.check_call([
      os.path.join(SCRIPT_DIR, 'migrate.py'), '-t', target_po
  ] + test_list_files)

  DoPoMake(locale, board, 'update')

  logging.info('All done. Generated po file at %s.', target_po)
  logging.info('Please see README.md for a list to check before commit.')


if __name__ == '__main__':
  main()
