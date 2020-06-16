# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
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


def NormalizeConfig(config):
  """Normalize config.

  This is same as what is done in Dome models.py.
  """
  bundle_id_set = set(b['id'] for b in config['bundles'])

  # We do not allow multiple rulesets referring to the same bundle, so
  # duplicate the bundle if we have found such cases.
  ruleset_id_set = set()
  for r in config['rulesets']:
    if r['bundle_id'] not in ruleset_id_set:
      ruleset_id_set.add(r['bundle_id'])
    else:  # need to duplicate
      # generate a new name, may generate very long _copy_copy_copy... at the
      # end if there are many conflicts
      new_name = r['bundle_id']
      while True:
        new_name = '%s_copy' % new_name
        if new_name not in ruleset_id_set and new_name not in bundle_id_set:
          ruleset_id_set.add(new_name)
          bundle_id_set.add(new_name)
          break

      # find the original bundle and duplicate it
      src_bundle = next(
          b for b in config['bundles'] if b['id'] == r['bundle_id'])
      dst_bundle = copy.deepcopy(src_bundle)
      dst_bundle['id'] = new_name
      config['bundles'].append(dst_bundle)

      # update the ruleset
      r['bundle_id'] = new_name

  # sort 'bundles' section by their IDs
  config['bundles'].sort(key=lambda b: b['id'])

  # We do not allow bundles exist in 'bundles' section but not in 'ruleset'
  # section.
  for b in config['bundles']:
    if b['id'] not in ruleset_id_set:
      ruleset_id_set.add(b['id'])
      config['rulesets'].append({'active': False,
                                 'bundle_id': b['id'],
                                 'note': b['note']})


def MergeRulesetToBundle(config):
  """Merge ruleset to bundle.

  This assumes that bundle and ruleset is already 1 to 1 (as after
  NormalizeConfig). Also this override the bundle's note with ruleset's note,
  since Dome use note from ruleset.
  """
  bundle_map = {b['id']: b for b in config['bundles']}

  for r in config['rulesets']:
    bundle = bundle_map[r['bundle_id']]
    assert 'active' not in bundle
    bundle['active'] = r['active']
    bundle['note'] = r['note']

  assert all('active' in b for b in config['bundles'])

  # Order bundle to the same order as corresponding ruleset.
  config['bundles'] = [bundle_map[r['bundle_id']] for r in config['rulesets']]
  del config['rulesets']


def Migrate():
  with open('/var/db/factory/umpire/active_umpire.json') as f:
    config = json.load(f)
  NormalizeConfig(config)
  MergeRulesetToBundle(config)
  SaveNewActiveConfig(config)
