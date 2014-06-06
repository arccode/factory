# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Deploys an Umpire config file.

See ConfigDeployer for detail.
"""

import errno
import logging
import os

from twisted.python import failure as twisted_failure

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire import common
from cros.factory.umpire import daemon


class ConfigDeployer(object):
  """Deploys an Umpire config file."""
  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env
    self._original_config_path = self._env.config_path
    self._config_path_to_deploy = None

  def _ValidateConfigRes(self, config_res):
    """Validates config in resource directory.

    Once validated, self._config_path_to_deploy is set.

    Raises:
      Exception from umpire_config.ValidateResources() if validation failed.
      IOError if file not found.
    """
    config_path = self._env.GetResourcePath(config_res)
    if not os.path.isfile(config_path):
      raise IOError(errno.ENOENT, 'Config does not exist', config_path)

    config_to_validate = umpire_config.UmpireConfig(config_path)
    umpire_config.ValidateResources(config_to_validate, self._env)
    self._config_path_to_deploy = config_path

  def _HandleDeploySuccess(self, unused_result):
    """On deploy success, activates the new config and unstage staging file.

    Returns:
      A string indicating deploy success.
    """
    self._env.ActivateConfigFile(self._config_path_to_deploy)
    self._env.UnstageConfigFile()
    logging.info('Config %r deployed. Set it as activate config.',
                 self._config_path_to_deploy)
    return 'Deploy success'

  def _HandleDeployError(self, failure):
    """On deploy error, rollbacks config to the original one.

    Returns:
      Twisted deferred object Deploy() returns.
    """
    logging.error('Failed to deploy config %r. Reason: %s. Rollbacking...',
                  self._config_path_to_deploy, str(failure))
    self._env.LoadConfig(custom_path=self._original_config_path)
    deferred = daemon.UmpireDaemon().Deploy()
    deferred.addCallbacks(self._HandleRollbackSuccess,
                          self._HandleRollbackError)
    return deferred

  def _HandleRollbackSuccess(self, unused_result):
    """On rollback success.

    Returns:
      Failure object that indicates deploy failed but rollback success.
    """
    logging.error('Successfully rollbacked to config %r',
                  self._env.config_path)
    return twisted_failure.Failure('Deploy failed. Rollback success')

  def _HandleRollbackError(self, failure):
    """On rollback error, stops the daemon.

    Raises:
      UmpireError to its caller (CLI) as Umpire is in an unrecoverable state.
    """
    error = 'Rollback to config %r failed: %s. Stopping Umpire daemon' % (
        self._original_config_path, str(failure))
    logging.error(error)
    daemon.UmpireDaemon().Stop()
    raise common.UmpireError(error)

  def Deploy(self, config_res):
    """Deploys the config in resource directory.

    It validates the config first. Then it tries to deploy it by asking
    Umpire daemon to redeploy again using new config. If it fails, it tries
    rollback to the original config. And if unfortunately the rollback fails,
    Umpire daemon will stop.

    It should be used in Twisted server as it returns a deferred object. Once
    the deploy is okay, it activates the config and unstages the current staging
    config.

    Returns:
      Twisted deferred object. It eventually returns either a string for a
      successful deployment, or a Failure for a failed deployment but a
      successful rollback, or raises an UmpireError exception for a failure
      rollback.
    """
    self._ValidateConfigRes(config_res)
    self._env.LoadConfig(custom_path=self._config_path_to_deploy)

    logging.info('Config %r validated. Try deploying...',
                 self._config_path_to_deploy)
    deferred = daemon.UmpireDaemon().Deploy()
    deferred.addCallbacks(self._HandleDeploySuccess, self._HandleDeployError)
    return deferred
