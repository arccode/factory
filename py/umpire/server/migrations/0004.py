# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import hashlib
import json
import os

_ENV_DIR = '/var/db/factory/umpire'
_CONFIG_PATH = os.path.join(_ENV_DIR, 'active_umpire.json')

# Configuration to migrate (no transform).
MIGRATE_KEYS = {
    'shopfloor_service_url': 'services.shop_floor.service_url'}


def MigrateConfig(config, migrate_keys):
  """Migrates a config by moving key values to new location."""
  modified = False

  for old_key, new_key in migrate_keys.items():
    if old_key not in config:
      continue

    modified = True
    value = config.get(old_key)
    del config[old_key]
    new_keys = new_key.split('.')
    sub_config = config
    for key in new_keys[:-1]:
      sub_config.setdefault(key, {})
      sub_config = sub_config[key]
    sub_config[new_keys[-1]] = value

  return modified


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


def Migrate():
  with open(_CONFIG_PATH) as f:
    config = json.load(f)

  if not MigrateConfig(config, MIGRATE_KEYS):
    return

  SaveNewActiveConfig(config)
