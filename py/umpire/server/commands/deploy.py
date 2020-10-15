# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Deploys an Umpire config file.

See ConfigDeployer for detail.
"""

import logging

from twisted.python import failure as twisted_failure

from cros.factory.umpire import common
from cros.factory.umpire.server import config as umpire_config
from cros.factory.utils import file_utils


class ConfigDeployer:
  """Deploys an Umpire config file."""

  def __init__(self, daemon):
    """Constructor.

    Args:
      daemon: UmpireDaemon object.
    """
    self._daemon = daemon
    self._env = daemon.env
    self._original_config_path = self._env.config_path
    self._config_path_to_deploy = None
    self._config_to_deploy = None

  def _ValidateConfigToDeploy(self):
    """Validates config to deploy.

    Once validated, self._config_to_deploy is set.

    Raises:
      Exception from umpire_config.ValidateResources() if validation failed.
      IOError if file not found.
    """
    file_utils.CheckPath(self._config_path_to_deploy, 'config')

    config_to_validate = umpire_config.UmpireConfig(
        file_path=self._config_path_to_deploy)
    umpire_config.ValidateResources(config_to_validate, self._env)
    self._config_to_deploy = config_to_validate

  def _HandleDeploySuccess(self, result):
    """Handles deploy success.

    Activates the new config.

    Returns:
      A string indicating deploy success.
    """
    del result  # Unused.

    self._env.ActivateConfigFile(self._config_path_to_deploy)
    logging.info('Config %r deployed. Set it as activate config.',
                 self._config_path_to_deploy)
    return 'Deploy success'

  def _HandleDeployError(self, failure):
    """On deploy error, rollbacks config to the original one.

    Returns:
      Twisted deferred object Deploy() returns.
    """
    logging.error('Failed to deploy config %r. Reason: %s. Rollbacking...',
                  self._config_path_to_deploy, failure)
    self._env.LoadConfig(custom_path=self._original_config_path)
    deferred = self._daemon.Deploy()
    deferred.addCallbacks(
        lambda unused_result: self._HandleRollbackSuccess(failure),
        self._HandleRollbackError)
    return deferred

  def _HandleRollbackSuccess(self, original_failure):
    """On rollback success.

    Returns:
      Failure object that indicates deploy failed but rollback success.
    """
    error = ('Deploy failed. Successfully rollbacked to config %r.\n'
             'The original error was: %s' % (self._env.config_path,
                                             original_failure))
    logging.error(error)
    return twisted_failure.Failure(common.UmpireError(error))

  def _HandleRollbackError(self, failure):
    """On rollback error, stops the daemon.

    Raises:
      UmpireError to its caller (CLI) as Umpire is in an unrecoverable state.
    """
    error = 'Rollback to config %r failed: %s. Stopping Umpire daemon' % (
        self._original_config_path, failure)
    logging.error(error)
    self._daemon.Stop()
    raise common.UmpireError(error)

  def Deploy(self, config_res):
    """Deploys the config in resource directory.

    It validates the config first. Then it tries to deploy it by asking
    Umpire daemon to redeploy again using new config. If it fails, it tries
    rollback to the original config. And if unfortunately the rollback fails,
    Umpire daemon will stop.

    It should be used in Twisted server as it returns a deferred object. Once
    the deploy is okay, it activates the config.

    Args:
      config_res: config file in resources.

    Returns:
      Twisted deferred object. It eventually returns either a string for a
      successful deployment, or a Failure for a failed deployment but a
      successful rollback, or raises an UmpireError exception for a failure
      rollback.
    """
    self._config_path_to_deploy = self._env.GetResourcePath(config_res)
    self._ValidateConfigToDeploy()

    # Load new config and let daemon deploy it.
    self._env.LoadConfig(custom_path=self._config_path_to_deploy)
    logging.info('Config %r validated. Try deploying...',
                 self._config_path_to_deploy)
    deferred = self._daemon.Deploy()
    deferred.addCallbacks(self._HandleDeploySuccess, self._HandleDeployError)
    return deferred
