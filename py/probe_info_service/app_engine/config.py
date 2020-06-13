# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import enum
import logging
import os

import yaml

from cros.factory.utils import file_utils
# TODO(yhong): Stop disabling unused-import check once the issue
#     https://github.com/PyCQA/pylint/issues/1630 is solved.
from cros.factory.utils import type_utils  # pylint: disable=unused-import


_CONFIGURATIONS_YAML_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'configurations.yaml')


@enum.unique
class EnvType(enum.Enum):
  LOCAL = 'local'
  STAGING = 'staging'
  PROD = 'prod'


_DEFAULT_CONFIG = {
    'env_type': EnvType.LOCAL.value,
    'log_level': logging.DEBUG,
}


class Config(metaclass=type_utils.Singleton):
  def __init__(self):
    gae_application = os.environ.get('GAE_APPLICATION')
    if gae_application:
      # We consider the configuration file missing the config set for the
      # current environment a vital error so not to catch the exceptions.
      env_configuration = yaml.safe_load(
          file_utils.ReadFile(_CONFIGURATIONS_YAML_PATH))[gae_application]
    else:
      env_configuration = _DEFAULT_CONFIG

    self.env_type = EnvType(env_configuration['env_type'])
    self.log_level = env_configuration['log_level']
