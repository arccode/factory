# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Reports Umpire server status."""


class StatusReporter(object):
  """Reports Umpire server status.

  Usage:
    reporter = StatusReporter(env)
    status = reporter.Report()
    # You can get active config from status['active_config'].
  """
  def __init__(self, env):
    """Constructor."""
    self._env = env

  def Report(self):
    """Gets Umpire status report.

    Returns:
      Umpire status in a dict.
    """
    result = dict()
    result['active_config'] = self.GetActiveConfig()
    result['staging_config'] = self.GetStagingConfig()
    result['shop_floor_mapping'] = self.GetShopFloorMapping()
    return result

  def GetActiveConfig(self):
    """Gets active config file.

    Returns:
      Active config file content (string).
    """
    return open(self._env.active_config_file).read()

  def GetStagingConfig(self):
    """Gets staging config file.

    Returns:
      Staging config file content (string).
      Empty string if file not found.
    """
    if not self._env.HasStagingConfigFile():
      return ''
    return open(self._env.staging_config_file).read()

  def GetShopFloorMapping(self):
    """Gets list of (bundle_id, handler) pairs.

    Returns:
      list of (bundle_id, handler) pairs.
    """
    return self._env.shop_floor_manager.GetBundleHandlerMapping()
