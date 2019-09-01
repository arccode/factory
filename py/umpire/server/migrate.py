#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import argparse
import glob
import importlib
import logging
import os
import re
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import json_utils


_ENV_DIR = os.path.join('/', umpire_env.DEFAULT_BASE_DIR)
_SESSION_JSON_PATH = os.path.join(_ENV_DIR, umpire_env.SESSION_JSON_FILE)

_WIP_KEY = 'migrate_in_progress'

_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
_MIGRATIONS_DIR = os.path.join(_SCRIPT_DIR, 'migrations')
_MIGRATION_NAME_RE = r'(\d{4})\.py$'
_MIGRATION_NAME_TEMPLATE = '%04d'


def _GetVersionOfLatestMigration():
  s = set()
  for path in glob.glob(os.path.join(_MIGRATIONS_DIR, '*')):
    matched = re.match(_MIGRATION_NAME_RE, os.path.basename(path))
    if matched:
      s.add(int(matched.group(1)))
  if max(s) != len(s) - 1:
    raise RuntimeError('Missing some migration scripts.')
  return max(s)


def _GetEnvironmentVersionAndData():
  if not os.listdir(_ENV_DIR):
    logging.info('Clean installation.')
    return (-1, None)

  try:
    env = json_utils.JSONDatabase(_SESSION_JSON_PATH, convert_to_str=False)
  except IOError:
    logging.info(
        '%s not found. Assuming before migration mechanism.',
        _SESSION_JSON_PATH)
    return (0, None)

  logging.info('%r : %s', _SESSION_JSON_PATH, json_utils.DumpStr(env))
  return (env['version'], env)


def _RunMigration(migration_id):
  version, env = _GetEnvironmentVersionAndData()
  if migration_id != version + 1:
    raise RuntimeError(
        "Shouldn't run migration #%d when environment version is %d." % (
            migration_id, version))

  migration_name = _MIGRATION_NAME_TEMPLATE % migration_id
  module = importlib.import_module(
      'cros.factory.umpire.server.migrations.%s' % migration_name)
  try:
    os.chdir(os.path.join(_MIGRATIONS_DIR, migration_name))
  except OSError:
    pass

  if env:
    if env.get(_WIP_KEY):
      raise RuntimeError(
          "Please remove field %r from %r before running migrations." % (
              _WIP_KEY, _SESSION_JSON_PATH))
    env[_WIP_KEY] = True
    env.Save()

  logging.info('Start running migration %s ...', migration_name)
  try:
    module.Migrate()
  except Exception:
    logging.error(
        'Migration %s failed. Please manually fix it and remember to remove '
        'field %r from %r before re-run it.',
        migration_name, _WIP_KEY, _SESSION_JSON_PATH)
    raise
  logging.info('Migration %s finished successfully.', migration_name)

  if env:
    env.Load()
    del env[_WIP_KEY]
    env['version'] = migration_id
    env.Save()


def RunMigrations():
  latest = _GetVersionOfLatestMigration()
  version = _GetEnvironmentVersionAndData()[0]
  if version > latest:
    raise RuntimeError('Cannot downgrade Umpire version.')
  while version < latest:
    version += 1
    if os.fork() == 0:
      _RunMigration(version)
      sys.exit()
    if os.wait()[1] != 0:
      raise RuntimeError('Stop running migrations.')


def main():
  parser = argparse.ArgumentParser()
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument(
      '-a', '--run-all', action='store_true',
      help='run all necessary migrations.')
  group.add_argument(
      '-r', dest='migration_id', type=int, help='run the specified migration.')
  args = parser.parse_args()

  if args.run_all:
    RunMigrations()
  else:
    _RunMigration(args.migration_id)


if __name__ == '__main__':
  main()
