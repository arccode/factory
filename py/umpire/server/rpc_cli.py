# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpired RPC command class."""

import urllib.request
from cros.factory.umpire import common
from cros.factory.umpire.server.commands import deploy
from cros.factory.umpire.server.commands import export_log
from cros.factory.umpire.server.commands import export_payload
from cros.factory.umpire.server.commands import import_bundle
from cros.factory.umpire.server.commands import update
from cros.factory.umpire.server import config
from cros.factory.umpire.server import umpire_rpc
from cros.factory.umpire.server import umpire_env
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.umpire.server.service import umpire_sync


class CLICommand(umpire_rpc.UmpireRPC):
  """Container of Umpire RPC commands.

  Umpire CLI commands are decorated with '@RPCCall'. Requests are translated
  via Twisted XMLRPC resource.

  Command returns:
    defer.Deferred: The server waits for the callback/errback and returns
                    the what callback/errback function returns.
    xmlrpc.Fault(): The raised exception will be caught by umpire.web.xmlrpc
                    and translate to xmlrpc.Fault with exception info.
    Other values: return to caller.
  """

  @umpire_rpc.RPCCall
  def GetVersion(self):
    """Get the umpire image version."""
    return common.UMPIRE_VERSION

  @umpire_rpc.RPCCall
  def ExportLog(self, dst_dir, log_type, split_size, start_date, end_date):
    """Compress and export a specific log, such as factory log, DUT report,
    or csv files.

    Args:
      dst_dir: the destination directory to export the specific log.
      log_type: download type of the log, e.g. log, report, csv.
      split_size: maximum size of the archives.
                  (format: {'size': xxx, 'unit': 'MB'/'GB'})
      start_date: start date (format: yyyymmdd)
      end_date: end date (format: yyyymmdd)

    Returns:
      {
        'messages': array (messages of ExportLog)
        'log_paths': array (files paths of compressed files)
      }
    """
    exporter = export_log.LogExporter(self.env)
    return exporter.ExportLog(
        dst_dir, log_type, split_size, start_date, end_date)

  @umpire_rpc.RPCCall
  def ExportPayload(self, bundle_id, payload_type, file_path):
    """Export a specific resource from a bundle

    It reads active config, download the specific resource of a bundle,
    and install it at the specified file_path.

    Args:
      bundle_id: The ID of the bundle.
      payload_type: Payload type of the resource.
      file_path: File path to export the specific resource.
    """
    exporter = export_payload.PayloadExporter(self.env)
    exporter.ExportPayload(bundle_id, payload_type, file_path)

  @umpire_rpc.RPCCall
  def Update(self, resources_to_update, source_id=None, dest_id=None):
    """Updates resource(s) in a bundle.

    It modifies and deploys active config.

    Args:
      resources_to_update: list of (resource_type, resource_path) to update.
      source_id: source bundle's ID. If omitted, uses default bundle.
      dest_id: If specified, it copies source bundle with ID dest_id and
          replaces the specified resource(s). Otherwise, it replaces
          resource(s) in place.
    """
    update.ResourceUpdater(self.daemon).Update(
        resources_to_update, source_id, dest_id)

  @umpire_rpc.RPCCall
  def ImportBundle(self, bundle_path, bundle_id=None, note=None):
    """Imports a bundle.

    It reads a factory bundle and copies resources to Umpire.
    It also adds a bundle in UmpireConfig's bundles section and deploys the
    updated config.

    Args:
      bundle_path: A bundle's path (could be a directory or a zip file).
      bundle_id: The ID of the bundle. If omitted, use bundle_name in
          factory bundle's manifest.
      note: A note.
    """
    import_bundle.BundleImporter(self.daemon).Import(
        bundle_path, bundle_id, note)

  @umpire_rpc.RPCCall
  def AddPayload(self, file_path, type_name):
    """Adds a cros_payload component into <base_dir>/resources.

    Args:
      file_path: file to be added.
      type_name: An element of resource.PayloadTypeNames.

    Returns:
      The json dictionary generated by cros_payload.
    """
    return self.env.AddPayload(file_path, type_name)

  @umpire_rpc.RPCCall
  def AddConfig(self, file_path, type_name):
    """Adds a config file into <base_dir>/resources.

    Args:
      file_path: file to be added.
      type_name: An element of resource.ConfigTypeNames.

    Returns:
      Resource file name.
    """
    return self.env.AddConfig(file_path, type_name)

  @umpire_rpc.RPCCall
  def AddConfigFromBlob(self, blob, type_name):
    """Adds a config file into <base_dir>/resources.

    Args:
      blob: content of config file to be added.
      type_name: An element of resource.ConfigTypeNames.

    Returns:
      Resource file name.
    """
    return self.env.AddConfigFromBlob(blob, type_name)

  @umpire_rpc.RPCCall
  def GetPayloadsDict(self, payloads_name):
    """Gets a payload config.

    Args:
      payloads_name: filename of payload config in resources directory.

    Returns:
      A dictionary of specified cros_payload JSON config.
    """
    return self.env.GetPayloadsDict(payloads_name)

  @umpire_rpc.RPCCall
  def ValidateConfig(self, config_str):
    """Validates a config.

    Args:
      config_str: Umpire config in JSON string.

    Raises:
      TypeError: when 'services' is not a dict.
      KeyError: when top level key 'services' not found.
      SchemaException: on schema validation failed.
      UmpireError if there's any resources for active bundles missing.
    """
    config.ValidateResources(config.UmpireConfig(config_str), self.env)

  @umpire_rpc.RPCCall
  def Deploy(self, config_res):
    """Deploys a config file.

    It first verifies the config again, then tries reloading Umpire with the
    new config. If okay, active the config.

    Args:
      config_res: a config file (base name, in resource folder) to deploy.

    Returns:
      Twisted deferred object.

    Raises:
      Exceptions when config fails to validate. See ValidateConfig() for
      exception type.
    """
    deployer = deploy.ConfigDeployer(self.daemon)
    return deployer.Deploy(config_res)

  @umpire_rpc.RPCCall
  def StopUmpired(self):
    """Stops Umpire daemon."""
    self.daemon.Stop()

  @umpire_rpc.RPCCall
  def IsDeploying(self):
    """Returns if Umpire is now deploying a config."""
    return self.daemon.deploying

  @umpire_rpc.RPCCall
  def GetActiveConfig(self):
    """Returns the active config."""
    return file_utils.ReadFile(self.daemon.env.active_config_file)

  @umpire_rpc.RPCCall
  def ResourceGarbageCollection(self):
    """Resource garbage collection."""
    return self.env.ResourceGarbageCollection()

  @umpire_rpc.RPCCall
  def StartServices(self, services):
    """Starts a list of services."""
    return self.daemon.StartServices(services)

  @umpire_rpc.RPCCall
  def StopServices(self, services):
    """Stops a list of services."""
    return self.daemon.StopServices(services)

  @umpire_rpc.RPCCall
  def UpdateParameterComponent(self, comp_id, dir_id, comp_name, using_ver,
                               file_path=None):
    return self.env.parameters.UpdateParameterComponent(
        comp_id, dir_id, comp_name, using_ver, file_path)

  @umpire_rpc.RPCCall
  def GetParameterInfo(self):
    return self.env.parameters.GetParameterInfo()

  @umpire_rpc.RPCCall
  def UpdateParameterDirectory(self, dir_id, parent_id, name):
    return self.env.parameters.UpdateParameterDirectory(dir_id, parent_id, name)

  @umpire_rpc.RPCCall
  def GetActivePayload(self):
    return self.env.GetActivePayload(self.daemon.env.active_config_file)

  @umpire_rpc.RPCCall
  def CheckAndUpdate(self, target_payloads, target_url):
    """Update bundle if needed.

    A RPCCall compares it own payloads to the target payloads and downloads the
    resources that are different from its own, then it updates the active bundle
    if necessary.
    For the umpire_sync service, target is the Primary Umpire and itself is one
    of Secondary Umpires.

    Args:
      target_payloads: All target Umpire's payloads
      target_url: The endpoint to download payloads of the target Umpire

    Returns:
      A boolean whether the need to update the Umpire
    """
    self_payloads = self.env.GetActivePayload(
        self.daemon.env.active_config_file)
    update_config = self_payloads
    need_update = False
    for payload_type, target_payload_content in target_payloads.items():
      if payload_type not in self_payloads or self_payloads[payload_type][
          'version'] != target_payload_content['version']:
        need_update = True
        for file_name, file_content in target_payload_content.items():
          if file_name != 'version':
            url = f'{target_url}/res/{file_content}'
            path = f'/{umpire_env.DEFAULT_BASE_DIR}/resources/{file_content}'
            urllib.request.urlretrieve(url, path)
      update_config[payload_type] = target_payload_content
    if need_update:
      import_bundle.BundleImporter(self.daemon).UpdateBundle(
          update_config, None, 'Update by the service.')
    return need_update

  @umpire_rpc.RPCCall
  def GetUmpireSyncStatus(self):
    """Get secondary sync status.

    Returns:
      A dictionary of Umpire sync status.
      If the file doesn't exist or the service is inactive, return an empty
      dictionary.
    """
    try:
      self_active_config = json_utils.LoadFile(
          self.daemon.env.active_config_file)['services']
      if 'umpire_sync' in self_active_config:
        if self_active_config['umpire_sync']['active'] is False:
          return {}
      umpire_data_dir = f'/{umpire_env.DEFAULT_BASE_DIR}/umpire_data'
      status_file = f'{umpire_data_dir}/{umpire_sync.STATUS_FILENAME}'
      return json_utils.LoadFile(status_file)
    except Exception:
      return {}
