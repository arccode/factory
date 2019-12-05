# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import hashlib
import json
import os


_ENV_DIR = '/var/db/factory/umpire'
_CONFIG_PATH = os.path.join(_ENV_DIR, 'active_umpire.json')


def SaveNewActiveConfig(config):
  """Serialize and saves the configuration as new active config file."""
  json_config = json.dumps(
      config, indent=2, separators=(',', ': '), sort_keys=True) + '\n'
  json_name = 'umpire.%s.json' % (
      hashlib.md5(json_config.encode('utf-8')).hexdigest())
  json_path = os.path.join('resources', json_name)
  with open(os.path.join(_ENV_DIR, json_path), 'w') as f:
    f.write(json_config)

  os.unlink(_CONFIG_PATH)
  os.symlink(json_path, _CONFIG_PATH)


def FindActiveBundle(config):
  """Find the name of first active bundle in a config."""
  bundle = next(b for b in config['bundles'] if b['active'])
  return bundle['id']


def Migrate():
  with open(_CONFIG_PATH) as f:
    config = json.load(f)

  active_bundle_id = FindActiveBundle(config)
  config['active_bundle_id'] = active_bundle_id
  for b in config['bundles']:
    del b['active']

  SaveNewActiveConfig(config)
