# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Deploys an Umpire config file.

See ConfigDeployer for detail.
"""

import datetime
import errno
import logging
import os

from twisted.python import failure as twisted_failure

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire import common
from cros.factory.umpire import daemon
from cros.factory.umpire import utils
from cros.factory.utils import file_utils


class ConfigDeployer(object):
  """Deploys an Umpire config file."""
  _RESOURCE_FOR_DOWNLOAD_CONF = (
      ('rootfs_release', 'rootfs-release.gz'),  # RELEASE
      ('oem_partition', 'oem.gz'),              # OEM
      ('hwid', 'hwid.gz'),                      # HWID
      ('efi_partition', 'efi.gz'),              # EFI
      ('stateful_partition', 'state.gz'),       # STATE
      ('complete_script', 'complete.gz'),       # COMPLETE
      ('firmware', 'firmware.gz'),              # FIRMWARE
      ('rootfs_test', 'rootfs-test.gz'))        # FACTORY

  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env
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
    if not os.path.isfile(self._config_path_to_deploy):
      raise IOError(errno.ENOENT, 'Config does not exist',
                    self._config_path_to_deploy)

    config_to_validate = umpire_config.UmpireConfig(
        self._config_path_to_deploy)
    umpire_config.ValidateResources(config_to_validate, self._env)
    self._config_to_deploy = config_to_validate

  def _ComposeDownloadConf(self, resources):
    """Composes download_conf body.

    First checks if all files needed by download_conf exist in resources.

    Returns:
      download_conf content (multi-line string).

    Raises:
      UmpireError if resource is missing.
    """
    download_files = []
    error_message = []
    for res_key, filename_prefix in self._RESOURCE_FOR_DOWNLOAD_CONF:
      res_filename = resources.get(res_key)
      if res_filename and res_filename.startswith(filename_prefix):
        download_files.append(self._env.GetResourcePath(res_filename))
      else:
        error_message.append(
            'Resource %s filename should be %s, but found %r' %
            (res_key, filename_prefix, res_filename))

    if error_message:
      raise common.UmpireError(error_message)
    return utils.ComposeDownloadConfig(download_files)

  def _UpdateDownloadConf(self):
    """May update download_conf.

    Resources of a bundle in config might be changed by "umpire edit" or
    "umpire update". We need to regenerate download_conf to reflect the
    change.
    """
    if not self._config_to_deploy:
      raise common.UmpireError('Unable to get config_to_deploy. It should fail '
                               'in _ValidateConfigToDeploy')
    bundles = self._config_to_deploy['bundles']
    if not bundles:
      return

    board = self._config_to_deploy['board']
    need_update_config = False

    logging.debug('Refreshing download_conf')
    for bundle in bundles:
      resources = bundle['resources']
      new_conf = self._ComposeDownloadConf(resources)
      new_conf_lines = new_conf.split('\n')
      original_conf = open(
          self._env.GetResourcePath(resources['download_conf'])).read()
      original_conf_lines = original_conf.split('\n')

      if original_conf_lines[2:] != new_conf_lines:
        logging.info('download-conf differ for bundle %s',  bundle['id'])
        header = '# date:   %s\n# bundle: %s_%s\n' % (
            datetime.datetime.utcnow(), board, bundle['id'])
        with file_utils.TempDirectory() as temp_dir:
          temp_conf_path = os.path.join(temp_dir, '%s.conf' % board)
          with open(temp_conf_path, 'w') as f:
            f.write(header)
            f.write(new_conf)
          new_download_conf_path = self._env.AddResource(temp_conf_path)
          resources['download_conf'] = os.path.basename(new_download_conf_path)
          logging.info('Composes new download_conf in %r',
                       new_download_conf_path)
          need_update_config = True

    # If UmpireConfig needs update, add it to resources and use it.
    if need_update_config:
      with file_utils.TempDirectory() as temp_dir:
        temp_config_path = os.path.join(temp_dir, 'umpire.yaml')
        self._config_to_deploy.WriteFile(temp_config_path)
        self._config_path_to_deploy = self._env.AddResource(temp_config_path)
      logging.info('Updated UmpireConfig %r', self._config_path_to_deploy)
      # Validate again.
      self._ValidateConfigToDeploy()
      self._env.StageConfigFile(config_path=self._config_path_to_deploy,
                                force=True)
      logging.info('Updated UmpireConfig validated and staged.')

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
    self._env.LoadConfig(custom_path=self._original_config_path,
                         init_shop_floor_manager=False)
    deferred = daemon.UmpireDaemon().Deploy()
    deferred.addCallbacks(self._HandleRollbackSuccess,
                          self._HandleRollbackError)
    return deferred

  def _HandleRollbackSuccess(self, unused_result):
    """On rollback success.

    Returns:
      Failure object that indicates deploy failed but rollback success.
    """
    error = ('Deploy failed. Successfully rollbacked to config %r' %
             self._env.config_path)
    logging.error(error)
    return twisted_failure.Failure(common.UmpireError(error))

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
    self._UpdateDownloadConf()

    # Load new config and let daemon deploy it.
    # Note that it shall not init ShopFloorManager here.
    self._env.LoadConfig(custom_path=self._config_path_to_deploy,
                         init_shop_floor_manager=False)
    logging.info('Config %r validated. Try deploying...',
                 self._config_path_to_deploy)
    deferred = daemon.UmpireDaemon().Deploy()
    deferred.addCallbacks(self._HandleDeploySuccess, self._HandleDeployError)
    return deferred
