# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utils for accessing configuration of goofy plugin."""

import os

from cros.factory.test.env import paths
from cros.factory.test import state
from cros.factory.utils import config_utils


def GetPluginArguments(plugin_name):
  """Get current arguments for a Goofy plugin.

  Return None if the plugin is not found.
  """
  config_name = state.DataShelfGetValue('test_list_options.plugin_config_name')
  config = config_utils.LoadConfig(
      config_name=config_name, schema_name='plugins',
      allow_inherit=True, default_config_dirs=os.path.join(
          paths.FACTORY_PYTHON_PACKAGE_DIR, 'goofy', 'plugins'))
  try:
    return config['plugins'][plugin_name].get('args', {})
  except KeyError:
    return None
