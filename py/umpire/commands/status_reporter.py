# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Reports Umpire server status."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils


class StatusReporter(object):
  """Reports Umpire server status.

  Usage:
    reporter = StatusReporter(daemon)
    status = reporter.Report()
    # You can get active config from status['active_config'].
  """

  def __init__(self, daemon):
    """Constructor."""
    self._daemon = daemon
    self._env = daemon.env

  def Report(self):
    """Gets Umpire status report.

    Returns:
      Umpire status in a dict.
    """
    result = {}
    result['active_config'] = self.GetActiveConfig()
    result['active_config_res'] = os.path.basename(os.path.realpath(
        self._env.active_config_file))
    result['staging_config'] = self.GetStagingConfig() or ''
    if result['staging_config']:
      result['staging_config_res'] = os.path.basename(os.path.realpath(
          self._env.staging_config_file))
    else:
      result['staging_config_res'] = ''
    result['deploying'] = self._daemon.deploying
    return result

  def GetActiveConfig(self):
    """Gets active config file.

    Returns:
      Active config file content (string).
    """
    return file_utils.ReadFile(self._env.active_config_file)

  def GetStagingConfig(self):
    """Gets staging config file.

    Returns:
      Staging config file content (string).
      None if file not found.
    """
    if not self._env.HasStagingConfigFile():
      return None
    return file_utils.ReadFile(self._env.staging_config_file)
