#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import importlib
import logging
import os
import sys

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


# Version for Umpire internal environment migrations.
UMPIRE_ENV_VERSION = 2

_ENV_DIR = os.path.join('/', umpire_env.DEFAULT_BASE_DIR)
_SESSION_JSON_PATH = os.path.join(_ENV_DIR, umpire_env.SESSION_JSON_FILE)

_WIP_KEY = 'migrate_in_progress'


def _GetEnvironmentVersionAndData():
  if not os.listdir(_ENV_DIR):
    logging.info('Clean installation.')
    return (-1, None)

  try:
    env = json_utils.JSONDatabase(_SESSION_JSON_PATH)
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

  migration_name = '%04d' % migration_id
  module = importlib.import_module(
      'cros.factory.umpire.server.migrations.%s' % migration_name)
  try:
    os.chdir(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            'migrations', migration_name))
  except OSError:
    pass

  if env:
    if env.get(_WIP_KEY):
      raise "Please remove field %r from %r before running migrations." % (
          _WIP_KEY, _SESSION_JSON_PATH)
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
  version = _GetEnvironmentVersionAndData()[0]
  if version > UMPIRE_ENV_VERSION:
    raise RuntimeError('Cannot downgrade Umpire version.')
  while version < UMPIRE_ENV_VERSION:
    version += 1
    process_utils.Spawn([__file__, str(version)], log=True, check_call=True)


def _Usage():
  print('Usage: %s run' % __file__)
  print('Usage: %s {MIGRATION_ID}' % __file__)


def main():
  if len(sys.argv) != 2:
    _Usage()
    return

  if sys.argv[1] == 'run':
    RunMigrations()
    return

  try:
    migration_id = int(sys.argv[1])
  except ValueError:
    _Usage()
    return
  _RunMigration(migration_id)


if __name__ == '__main__':
  main()
