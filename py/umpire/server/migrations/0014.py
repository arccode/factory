# Copyright 2020 The Chromium OS Authors. All rights reserved.
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

  encoded_json_config = json_config.encode('utf-8')
  json_name = 'umpire.%s.json' % hashlib.md5(encoded_json_config).hexdigest()
  json_path = os.path.join('resources', json_name)
  with open(os.path.join(_ENV_DIR, json_path), 'w') as f:
    f.write(json_config)

  os.unlink(_CONFIG_PATH)
  os.symlink(json_path, _CONFIG_PATH)


def Migrate():
  with open(_CONFIG_PATH) as f:
    config = json.load(f)

  if 'services' in config and 'http' in config['services']:
    config['services']['umpire_http'] = config['services'].pop('http')
    SaveNewActiveConfig(config)
