# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire bundle wrapper

We don't take advantage of django's database functionality because this system
should ideally be stateless. In other words, all information should be kept in
umpire instead of the database. This may not be possible for now, since umpire
config still lacks some critical information such as the history record.

TODO(littlecvr): make umpire config complete such that it contains all the
                 information we need.
"""

import os
import re
import xmlrpclib

import yaml
from django.db import models


# TODO(littlecvr): pull out the common parts between umpire and dome, and put
#                  them into a config file (using the new config API).
UMPIRE_BASE_DIR = os.path.join('/', 'var', 'db', 'factory', 'umpire')
UMPIRE_ACTIVE_CONFIG_FILE_NAME = 'active_umpire.yaml'
UMPIRE_STAGING_CONFIG_FILE_NAME = 'staging_umpire.yaml'
UMPIRE_CLI_PORT_OFFSET = 2
UMPIRE_RESOURCE_NAME_ALIAS = {
    'device_factory_toolkit': 'factory_toolkit',
    'server_factory_toolkit': 'factory_toolkit'}
UMPIRE_UPDATABLE_RESOURCE = set(['device_factory_toolkit',
                                 'server_factory_toolkit'])


class BoardModel(models.Model):
  # TODO(littlecvr): pull max length to common config with Umpire
  # TODO(littlecvr): need a validator, no spaces allowed
  name = models.CharField(max_length=200, primary_key=True)
  url = models.URLField()

  class Meta(object):
    ordering = ['name']


class Resource(object):

  def __init__(self, res_type, res_version, res_hash, updatable):
    self.type = res_type
    self.version = res_version
    self.hash = res_hash
    self.updatable = updatable


class Bundle(object):
  """Represent a bundle in umpire."""

  def __init__(self, name, note, active, resources):
    self.name = name
    self.note = note
    self.active = active

    # Parse resources. A resource in umpire config is a simple key-value
    # mapping, with its value consists of {file_name}, {version}, and {hash}:
    #   {resource_type}: {file_name}#{version}#{hash}
    # We'll parse its value for the front-end:
    #   {resource_type}: {
    #       'version': {version},
    #       'hash': {hash},
    #       'updatable': whether or not the resource can be updated}
    self.resources = {}
    for res_type in resources:
      match = re.match(r'^[^#]*#([^#]*)#([^#]*)$', resources[res_type])
      if match and len(match.groups()) >= 2:
        self.resources[res_type] = Resource(
            res_type,  # type
            match.group(1),  # version
            match.group(2),  # hash
            res_type in UMPIRE_UPDATABLE_RESOURCE)  # updatable

    # TODO(littlecvr): add rulesets in umpire config.


class BundleModel(object):
  """Provide functions to manipulate bundles in umpire.

  Umpire RPC calls aren't quite complete. For example, they do not provide any
  function to list bundles. So this class assumes that umpire runs on the same
  machine and is stored at its default location.

  TODO(littlecvr): complete the umpire RPC calls, decouple dome and umpire.
  """

  def __init__(self, board):
    """Constructor.

    Args:
      board: a string for name of the board.
    """
    self.board = board

  def _GetConfig(self, config_path):
    with open(config_path) as f:
      return yaml.load(f.read())

  def _GetActiveConfig(self):
    return self._GetConfig(self._GetActiveConfigPath())

  def _GetActiveConfigPath(self):
    return os.path.join(
        UMPIRE_BASE_DIR, self.board, UMPIRE_ACTIVE_CONFIG_FILE_NAME)

  def _GetStagingConfig(self):
    return self._GetConfig(self._GetStagingConfigPath())

  def _GetStagingConfigPath(self):
    return os.path.join(
        UMPIRE_BASE_DIR, self.board, UMPIRE_STAGING_CONFIG_FILE_NAME)

  def _GetActiveConfigAndXMLRPCServer(self):
    umpire_active_config = self._GetActiveConfig()
    port = umpire_active_config['port'] + UMPIRE_CLI_PORT_OFFSET
    umpire_rpc_server = xmlrpclib.ServerProxy(
        'http://localhost:%d' % port, allow_none=True)
    return (umpire_active_config, umpire_rpc_server)

  def _NormalizeConfig(self, config):
    # We do not allow multiple rulesets referring to the same bundle, so
    # duplicate the bundle if we have found such cases.
    bundle_set = set()
    for b in config['rulesets']:
      if b['bundle_id'] not in bundle_set:
        bundle_set.add(b['bundle_id'])
      else:  # need to duplicate
        # generate a new name, may generate very long _copy_copy_copy... at the
        # end if there are many conflicts
        new_name = b['bundle_id']
        while True:
          new_name = '%s_copy' % new_name
          if new_name not in bundle_set:
            bundle_set.add(new_name)
            break

        # find the original bundle and duplicate it
        src_bundle = next(
            x for x in config['bundles'] if x['id'] == b['bundle_id'])
        dst_bundle = src_bundle.copy()
        dst_bundle['id'] = new_name
        config['bundles'].append(dst_bundle)

    # We do not allow bundles exist in 'bundles' section but not in 'ruleset'
    # section.
    for b in config['bundles']:
      if b['id'] not in bundle_set:
        config['rulesets'].append({'active': False,
                                   'bundle_id': b['id'],
                                   'note': b['note']})

    return config

  def Deploy(self):
    """Deploy umpire.

    This function should only be called when there is a staging config. See
    umpire's doc for more info.
    """
    _, server = self._GetActiveConfigAndXMLRPCServer()

    # validate and deploy
    umpire_status = server.GetStatus()
    config_to_deploy_text = umpire_status['staging_config']
    config_to_deploy_res = umpire_status['staging_config_res']
    server.ValidateConfig(config_to_deploy_text)
    server.Deploy(config_to_deploy_res)

  def Stage(self):
    """Stage a config file."""
    _, server = self._GetActiveConfigAndXMLRPCServer()
    server.StageConfigFile(None)

  def Unstage(self):
    """Unstage the config file."""
    _, server = self._GetActiveConfigAndXMLRPCServer()
    server.UnstageConfigFile()

  def DeleteOne(self, bundle_name):
    """Delete a bundle in Umpire config.

    Args:
      bundle_name: the bundle to delete.
    """
    self.Stage()

    config = self._NormalizeConfig(self._GetStagingConfig())
    config['rulesets'] = [
        r for r in config['rulesets'] if r['bundle_id'] != bundle_name]
    config['bundles'] = [
        b for b in config['bundles'] if b['id'] != bundle_name]

    with open(self._GetStagingConfigPath(), 'w') as f:
      yaml.dump(config, stream=f, default_flow_style=False)

    self.Deploy()

  def ListOne(self, bundle_name):
    """Return the bundle that matches the search criterion.

    Args:
      bundle_name: name of the bundle to find, this corresponds to the "id"
          field in umpire config.
    """
    config = self._GetActiveConfig()

    active = False
    for b in config['rulesets']:
      if bundle_name == b['bundle_id']:
        active = b['active']
        break

    bundle = None
    for b in config['bundles']:
      if bundle_name == b['id']:
        bundle = Bundle(
            b['id'],  # name
            b['note'],  # note
            active,  # active
            b['resources'])  # resources
        break

    return bundle

  def ListAll(self):
    """Return all bundles as a list.

    This function lists bundles in the following order:
    1. bundles in the 'rulesets' section
    2. bundles in the 'bunedles' section but not in the 'rulesets' section

    Return:
      A list of all bundles.
    """
    config = self._GetActiveConfig()

    bundle_set = set()  # to fast determine if a bundle has been added
    bundle_list = list()
    for b in config['rulesets']:
      bundle_set.add(b['bundle_id'])
      bundle_list.append(self.ListOne(b['bundle_id']))
    for b in config['bundles']:
      if b['id'] not in bundle_set:
        bundle_list.append(self.ListOne(b['id']))

    return bundle_list

  def ModifyOne(self, name, active=True):
    """Activate a bundle.

    Args:
      name: name of the bundle.
      active: True to make the bundle active, False to make the bundle inactive.
    """
    self.Stage()

    config = self._NormalizeConfig(self._GetStagingConfig())
    bundle = next(b for b in config['rulesets'] if b['bundle_id'] == name)
    bundle['active'] = active

    with open(self._GetStagingConfigPath(), 'w') as f:
      yaml.dump(config, stream=f, default_flow_style=False)

    self.Deploy()

    return self.ListOne(bundle['bundle_id'])

  def UpdateResource(self, src_bundle_name, dst_bundle_name, note,
                     resource_type, resource_file_path):
    """Update resource in a bundle.

    Args:
      src_bundle_name: the bundle to update.
      dst_bundle_name: if specified, make a copy of the original bundle and name
          it as dst_bundle_name first. Otherwise, update-in-place. (See umpire's
          Update function).
      note: if dst bundle is specified, this will be note of the dst bundle;
          otherwise, this will overwrite note of the src bundle.
      resource_type: type of resource to update.
      resource_file_path: path to the new resource file.
    """
    # Replace with the alias if needed.
    resource_type = UMPIRE_RESOURCE_NAME_ALIAS.get(resource_type, resource_type)

    _, server = self._GetActiveConfigAndXMLRPCServer()
    staging_config_file = server.Update(
        [(resource_type, resource_file_path)], src_bundle_name, dst_bundle_name)

    # Umpire does not allow the user to add bundle note directly via update. So
    # duplicate the source bundle first.
    with open(staging_config_file) as f:
      config = yaml.load(f.read())

    # find source bundle
    src_bundle = None
    for b in config['rulesets']:
      if src_bundle_name == b['bundle_id']:
        src_bundle = b

    if not dst_bundle_name:  # in-place update
      src_bundle['note'] = str(note)

      # also update note in the bundles section
      for b in config['bundles']:
        if src_bundle_name == b['id']:
          b['note'] = str(note)
    else:
      # copy source bundle
      dst_bundle = src_bundle.copy()
      dst_bundle['bundle_id'] = str(dst_bundle_name)
      dst_bundle['note'] = str(note)
      config['rulesets'].insert(0, dst_bundle)

      # also update note in the bundles section
      for b in config['bundles']:
        if dst_bundle_name == b['id']:
          b['note'] = str(note)

    # TODO(littlecvr): should respect umpire's default order
    with open(staging_config_file, 'w') as f:
      yaml.dump(config, stream=f, default_flow_style=False)

    self.Deploy()

    return {'bundle_name': dst_bundle_name or src_bundle_name,
            'resource_type': resource_type,
            'updatable': True}

  def UploadNew(self, name, note, file_path):
    """Upload a new bundle.

    Args:
      name: name of the new bundle, in string. This corresponds to the "id"
          field in umpire config.
      note: commit message. This corresponds to the "note" field in umpire
          config.
      file_path: path to the bundle file. If the file is a temporary file, the
          caller is responsible for removing it.

    Return:
      The newly created bundle.
    """
    _, server = self._GetActiveConfigAndXMLRPCServer()

    # import bundle
    staging_config_path = server.ImportBundle(
        os.path.realpath(file_path), name, note)

    # make the bundle active
    with open(staging_config_path) as f:
      config = yaml.load(f.read())
    for ruleset in config['rulesets']:
      if ruleset['bundle_id'] == name:
        ruleset['active'] = True
        break
    with open(staging_config_path, 'w') as f:
      yaml.dump(config, stream=f, default_flow_style=False)

    self.Deploy()

    # find and return the new bundle
    return self.ListOne(name)
