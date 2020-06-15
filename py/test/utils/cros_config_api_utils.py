# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A wrapper for cros-config-api."""
import os

from google.protobuf import json_format

try:
  from chromiumos.config.payload import config_bundle_pb2
  MODULE_READY = True
except ImportError:
  MODULE_READY = False
from cros.factory.test.env import paths
from cros.factory.utils import file_utils


def ReadConfig(path):
  """Reads a json proto from a file.

  Args:
    path: Path to the json proto.
  """
  config = config_bundle_pb2.ConfigBundle()
  json_format.Parse(file_utils.ReadFile(path), config)
  return config


def MergeConfigs(configs):
  result = config_bundle_pb2.ConfigBundle()
  for config in configs:
    result.MergeFrom(config)
  return result


class SKUConfigs:
  def __init__(self, program, project):
    self._project = project
    config_jsonproto_dir = os.path.join(paths.FACTORY_DIR, 'project_config')
    program_config_file = os.path.join(
        config_jsonproto_dir, '%s_config.jsonproto' % program)
    project_config_file = os.path.join(
        config_jsonproto_dir, '%s_%s_config.jsonproto' % (program, project))
    boxster_config = MergeConfigs(
        [ReadConfig(program_config_file), ReadConfig(project_config_file)])
    program_candidates = []
    for config in boxster_config.designs.value:
      program_id = config.id.value.lower()
      program_candidates.append(program_id)
      if program_id == program:
        self._program_config = config
        break
    else:
      raise ValueError('program is %s and must be one of %r.'
                       % (program, program_candidates))

  def GetSKUConfig(self, sku_id):
    project_key = ('%s:%d' % (self._project, sku_id)).lower()
    project_candidates = []
    for config in self._program_config.configs:
      project_id = config.id.value.lower()
      project_candidates.append(project_id)
      if project_id == project_key:
        return config
    raise ValueError('sku_id is %s and must be one of %r.'
                     % (project_key, project_candidates))
