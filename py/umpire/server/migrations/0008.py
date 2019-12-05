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


def Migrate():
  with open('/var/db/factory/umpire/active_umpire.json') as f:
    config = json.load(f)
  if 'rulesets' in config:
    for r in config['rulesets']:
      r.pop('enable_update', None)
  SaveNewActiveConfig(config)
