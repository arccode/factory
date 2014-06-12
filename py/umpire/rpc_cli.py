# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=E1101

"""Umpired RPC command class."""

import os

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands import deploy
from cros.factory.umpire.commands import import_bundle
from cros.factory.umpire.commands import update
from cros.factory.umpire import config
from cros.factory.umpire import daemon
from cros.factory.umpire import umpire_rpc


class CLICommand(umpire_rpc.UmpireRPC):

  """Container of Umpire RPC commands.

  Umpire CLI commands are decorated with '@RPCCall'. Requests are translated
  via Twisted XMLRPC resource.

  Command returns:
    defer.Deferred: The server waits for the callback/errback and returns
                    the what callback/errback function returns.
    xmlrpc.Fault(): The raised exception will be catched by umpire.web.xmlrpc
                    and translate to xmlrpc.Fault with exception info.
    Other values: return to caller.
  """

  @umpire_rpc.RPCCall
  def Update(self, resources_to_update, source_id=None, dest_id=None):
    """Updates resource(s) in a bundle.

    It modifies active config and saves the result to staging.

    Args:
      resources_to_update: list of (resource_type, resource_path) to update.
      source_id: source bundle's ID. If omitted, uses default bundle.
      dest_id: If specified, it copies source bundle with ID dest_id and
          replaces the specified resource(s). Otherwise, it replaces
          resource(s) in place.

    Returns:
      Path to updated Umpire config file, which is marked as staging.
    """
    updater = update.ResourceUpdater(self.env)
    return updater.Update(resources_to_update, source_id, dest_id)

  @umpire_rpc.RPCCall
  def ImportBundle(self, bundle_path, bundle_id=None, note=None):
    """Imports a bundle.

    It reads a factory bundle and copies resources to Umpire.
    It also adds a bundle in env.UmpireConfig's bundles section.

    Args:
      bundle_path: A bundle's path (could be a directory or a zip file).
      bundle_id: The ID of the bundle. If omitted, use bundle_name in
          factory bundle's manifest.
      note: A note.
    """
    importer = import_bundle.BundleImporter(self.env)
    importer.Import(bundle_path, bundle_id, note)

  @umpire_rpc.RPCCall
  def AddResource(self, file_name, res_type=None):
    """Adds a file into base_dir/resources.

    Args:
      file_name: file to be added.
      res_type: (optional) resource type. If specified, it is one of the enum
        ResourceType. It tries to get version and fills in resource file name
        <base_name>#<version>#<hash>.

    Returns:
      Resource file name (base name).
    """
    return os.path.basename(self.env.AddResource(file_name, res_type=res_type))

  @umpire_rpc.RPCCall
  def StageConfigFile(self, config_path, force=False):
    """Stages a config file.

    If a config file is not in resources directory, it will first add it
    to resources.

    Args:
      config_path: path to a config file to mark as staging.
    """
    res_name = (os.path.basename(config_path)
                if self.env.InResource(config_path) else
                self.AddResource(config_path))
    config_path = self.env.GetResourcePath(res_name)
    self.env.StageConfigFile(config_path, force=force)

  @umpire_rpc.RPCCall
  def UnstageConfigFile(self):
    """Unstages the current staging config file."""
    self.env.UnstageConfigFile()

  @umpire_rpc.RPCCall
  def ValidateConfig(self, config_path):
    """Validates a config file.

    Args:
      config_path: Path to config file to validate

    Raises:
      TypeError: when 'services' is not a dict.
      KeyError: when top level key 'services' not found.
      SchemaException: on schema validation failed.
      UmpireError if there's any resources for active bundles missing.
    """
    config_to_validate = config.UmpireConfig(config_path)
    config.ValidateResources(config_to_validate, self.env)

  @umpire_rpc.RPCCall
  def Deploy(self, config_res):
    """Deploys a config file.

    It first verifies the config again, then tries reloading Umpire with the
    new config. If okay, removes current staging file and active the config.

    Args:
      config_res: a config file (base name, in resource folder) to deploy.

    Returns:
      Twisted deferred object.

    Raises:
      Exceptions when config fails to validate. See ValidateConfig() for
      exception type.
    """
    deployer = deploy.ConfigDeployer(self.env)
    return deployer.Deploy(config_res)

  @umpire_rpc.RPCCall
  def StopUmpired(self):
    """Stops Umpire daemon."""
    daemon.UmpireDaemon().Stop()
