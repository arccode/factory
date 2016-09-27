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
import subprocess
import xmlrpclib

import yaml
from django.core import validators
from django.db import models


# TODO(littlecvr): pull out the common parts between umpire and dome, and put
#                  them into a config file (using the new config API).
UMPIRE_BASE_PORT = 8090
UMPIRE_RPC_PORT_OFFSET = 2
UMPIRE_RSYNC_PORT_OFFSET = 4
UMPIRE_CONFIG_BASENAME = 'umpire.yaml'
UMPIRE_RESOURCE_NAME_ALIAS = {
    'device_factory_toolkit': 'factory_toolkit',
    'rootfs_release': 'fsi',
    'server_factory_toolkit': 'factory_toolkit'}
UMPIRE_UPDATABLE_RESOURCE = set(['device_factory_toolkit',
                                 'firmware',
                                 'hwid',
                                 'rootfs_release',
                                 'server_factory_toolkit'])
UMPIRE_MATCH_KEY_MAP = {
    'macs': 'mac',
    'serial_numbers': 'sn',
    'mlb_serial_numbers': 'mlb_sn'}

# TODO(littlecvr): use volume container instead of absolute path.
# TODO(littlecvr): these constants are shared between here and umpire_docker.sh,
#                  should be pulled out to common config.
UMPIRE_IMAGE_NAME = 'cros/umpire'
DOCKER_SHARED_DIR = '/docker_shared'
UMPIRE_DOCKER_DIR = '/docker_umpire'
UMPIRE_BASE_DIR_IN_UMPIRE_CONTAINER = '/var/db/factory/umpire'

# Mount point of the Umpire data folder in Dome's container. Note: this is not
# Umpire base directory in Umpire's container (which is also
# '/var/db/factory/umpire', but they have nothing to do with each other). This
# is also not Umpire's base directory on host (which is '/docker_umpire' for
# now).
# TODO(littlecvr): shared between here and dome.sh, should be pulled out to a
#                  common config.
UMPIRE_BASE_DIR = '/var/db/factory/umpire'


class Board(models.Model):
  # TODO(littlecvr): max_length and validator should be shared with Umpire
  name = models.CharField(max_length=200, primary_key=True,
                          validators=[validators.RegexValidator(
                              regex=r'[^/]+',
                              message='Slashes are not allowed in board name')])
  umpire_enabled = models.BooleanField(default=False)
  umpire_host = models.GenericIPAddressField(null=True)
  umpire_port = models.PositiveIntegerField(null=True)

  # TODO(littlecvr): add TFTP and Overlord ports

  class Meta(object):
    ordering = ['name']

  def ReplaceLocalhostWithDockerHostIP(self):
    # Dome is inside a docker container. If umpire_host is 'localhost', it is
    # not actually 'localhost', it is the docker host instead of docker
    # container. So we need to transform it to the docker host's IP.
    if self.umpire_host in ['localhost', '127.0.0.1']:
      self.umpire_host = Board._GetHostIP()
    return self

  def AddExistingUmpireContainer(self, host, port):
    """Add an existing Umpire container to the database."""
    self.umpire_enabled = True
    self.umpire_host = host
    self.umpire_port = port
    self.save()
    return self

  def CreateUmpireContainer(self, port, factory_toolkit_path):
    """Create a local Umpire container from a factory toolkit."""
    # make sure the container does not exist
    container_name = Board.GetUmpireContainerName(self.name)
    container_exists = subprocess.check_output([
        'docker', 'ps', '--all', '--format={{.Names}}',
        '--filter=name=%s' % container_name])
    if container_exists:
      raise EnvironmentError('Container %s already exists, Dome will not try '
                             'to create a new one, please add the existing '
                             'Umpire instance instead of create a new one ' %
                             container_name)

    # Umpire port mapping
    port_mapping = [
        '--publish', '%d:%d' % (port, UMPIRE_BASE_PORT),
        '--publish', '%d:%d' % (port + UMPIRE_RPC_PORT_OFFSET,
                                UMPIRE_BASE_PORT + UMPIRE_RPC_PORT_OFFSET),
        '--publish', '%d:%d' % (port + UMPIRE_RSYNC_PORT_OFFSET,
                                UMPIRE_BASE_PORT + UMPIRE_RSYNC_PORT_OFFSET)]

    try:
      # create and start a new container
      # TODO(littlecvr): this is almost identical to umpire_docker.sh's
      #                  do_start() function, when merging dome.sh and
      #                  umpire_docker.sh, we should remove this function in
      #                  that script because this job should be done by Dome
      #                  only
      subprocess.check_call(
          ['docker', 'run', '--detach', '--privileged',
           # TODO(littlecvr): remove hard-coded port mapping.
           '--publish', '4455:4455',  # for Overlord
           '--publish', '9000:9000',  # for Overlord
           '--publish', '69:69/udp'] +  # for TFTP
          port_mapping +
          ['--volume', '/etc/localtime:/etc/localtime:ro',
           '--volume', '%s:/mnt' % DOCKER_SHARED_DIR,
           '--volume', '%s/%s:%s' % (UMPIRE_DOCKER_DIR,
                                     container_name,
                                     UMPIRE_BASE_DIR_IN_UMPIRE_CONTAINER),
           '--restart', 'unless-stopped',
           '--name', container_name,
           UMPIRE_IMAGE_NAME])

      # install factory toolkit
      # TODO(b/31281536): no need to install factory toolkit after the issue
      #                   has been solved.
      subprocess.check_call([
          'docker', 'cp', factory_toolkit_path,
          '%s:/tmp/install_factory_toolkit.run' % container_name])
      subprocess.check_call([
          'docker', 'exec', container_name,
          'chmod', '755', '/tmp/install_factory_toolkit.run'])
      subprocess.check_call([
          'docker', 'exec', container_name,
          '/tmp/install_factory_toolkit.run',
          '--', '--init-umpire-board=%s' % self.name])
      subprocess.check_call([
          'docker', 'exec', container_name,
          'rm', '/tmp/install_factory_toolkit.run'])
    except Exception:
      # remove container
      subprocess.call(['docker', 'stop', container_name])
      subprocess.call(['docker', 'rm', container_name])
      raise

    # push into the database
    return self.AddExistingUmpireContainer('localhost', port)

  def DeleteUmpireContainer(self):
    container_name = Board.GetUmpireContainerName(self.name)
    subprocess.call(['docker', 'stop', container_name])
    subprocess.call(['docker', 'rm', container_name])
    self.umpire_enabled = False
    self.save()
    return self

  @staticmethod
  def _GetHostIP():
    # An easy way to get IP of the host. It's possible to install python
    # packages such as netifaces or pynetinfo into the container, but that
    # requires gcc to be installed and will thus increase the size of the
    # container (which we don't want).
    ip = subprocess.check_output(
        'route | grep default | tr -s " " | cut -d " " -f 2', shell=True)
    return ip.strip()  # remove the trailing newline

  @staticmethod
  def GetUmpireContainerName(name):
    return 'umpire_%s' % name

  @staticmethod
  def CreateOne(name, **kwargs):
    board = Board.objects.create(name=name)
    return Board.UpdateOne(board, **kwargs)

  @staticmethod
  def UpdateOne(board, **kwargs):
    # enable or disable Umpire if necessary
    if ('umpire_enabled' in kwargs and
        board.umpire_enabled != kwargs['umpire_enabled']):
      if not kwargs['umpire_enabled']:
        board.DeleteUmpireContainer()
      else:
        if kwargs.get('umpire_add_existing_one', False):
          board.AddExistingUmpireContainer(
              kwargs['umpire_host'], kwargs['umpire_port'])
        else:  # create a new local instance
          board.CreateUmpireContainer(
              kwargs['umpire_port'],
              kwargs['umpire_factory_toolkit_file'].temporary_file_path())

    # update attributes assigned in kwargs
    for attr, value in kwargs.iteritems():
      if hasattr(board, attr):
        setattr(board, attr, value)
    board.save()

    return board


class Resource(object):

  def __init__(self, res_type, res_version, res_hash, updatable):
    self.type = res_type
    self.version = res_version
    self.hash = res_hash
    self.updatable = updatable


class Bundle(object):
  """Represent a bundle in umpire."""

  def __init__(self, name, note, active, resources, rules):
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

    self.rules = {}
    for umpire_key in rules:
      key = next(
          k for (k, v) in UMPIRE_MATCH_KEY_MAP.iteritems() if v == umpire_key)
      self.rules[key] = rules[umpire_key]


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

    # get URL of the board
    board = Board.objects.get(pk=board).ReplaceLocalhostWithDockerHostIP()
    url = 'http://%s:%d' % (board.umpire_host,
                            board.umpire_port + UMPIRE_RPC_PORT_OFFSET)
    self.umpire_server = xmlrpclib.ServerProxy(url, allow_none=True)
    self.umpire_status = self.umpire_server.GetStatus()

  def _GetNormalizedActiveConfig(self):
    """Return the normalized version of Umpire active config."""
    config = yaml.load(self.umpire_status['active_config'])
    return self._NormalizeConfig(config)

  def _UploadAndDeployConfig(self, config, force=False):
    """Upload and deploy config atomically."""
    staging_config_path = self.umpire_server.UploadConfig(
        UMPIRE_CONFIG_BASENAME, yaml.dump(config, default_flow_style=False))

    try:
      self.umpire_server.StageConfigFile(staging_config_path, force)
    except Exception as e:
      raise EnvironmentError('Cannot stage config file, make sure no one is '
                             'editing Umpire config at the same time, and '
                             'there is no staging config exists. Error '
                             'message: %r' % e)

    try:
      self.umpire_server.Deploy(staging_config_path)
    except Exception as e:
      self.umpire_server.UnstageConfigFile()
      raise RuntimeError('Cannot deploy Umpire config, error message: %r' % e)

    # refresh status
    self.umpire_status = self.umpire_server.GetStatus()

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

  def DeleteOne(self, bundle_name):
    """Delete a bundle in Umpire config.

    Args:
      bundle_name: the bundle to delete.
    """
    config = self._GetNormalizedActiveConfig()
    config['rulesets'] = [
        r for r in config['rulesets'] if r['bundle_id'] != bundle_name]
    config['bundles'] = [
        b for b in config['bundles'] if b['id'] != bundle_name]

    self._UploadAndDeployConfig(config)

  def ListOne(self, bundle_name):
    """Return the bundle that matches the search criterion.

    Args:
      bundle_name: name of the bundle to find, this corresponds to the "id"
          field in umpire config.
    """
    config = self._GetNormalizedActiveConfig()

    active = False
    for b in config['rulesets']:
      if bundle_name == b['bundle_id']:
        active = b['active']
        rules = b.get('match', {})
        break

    bundle = None
    for b in config['bundles']:
      if bundle_name == b['id']:
        bundle = Bundle(
            b['id'],  # name
            b['note'],  # note
            active,  # active
            b['resources'],  # resources
            rules)  # matching rules
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
    config = self._GetNormalizedActiveConfig()

    bundle_set = set()  # to fast determine if a bundle has been added
    bundle_list = list()
    for b in config['rulesets']:
      bundle_set.add(b['bundle_id'])
      # TODO(littlecvr): not an efficient way since ListOne() scans through all
      #                  bundles
      bundle_list.append(self.ListOne(b['bundle_id']))
    for b in config['bundles']:
      if b['id'] not in bundle_set:
        # TODO(littlecvr): not an efficient way since ListOne() scans through
        #                  all bundles
        bundle_list.append(self.ListOne(b['id']))

    return bundle_list

  def ModifyOne(self, name, active=None, rules=None):
    """Modify a bundle.

    Args:
      name: name of the bundle.
      active: True to make the bundle active, False to make the bundle inactive.
          None means no change.
      rules: rules to replace, this corresponds to Umpire's "match", see
          Umpire's doc for more info, None means no change.
    """
    config = self._GetNormalizedActiveConfig()
    bundle = next(b for b in config['rulesets'] if b['bundle_id'] == name)

    if active is not None:
      bundle['active'] = active

    if rules is not None:
      bundle['match'] = {}
      for key in rules:
        if rules[key]:  # add non-empty key only
          bundle['match'][UMPIRE_MATCH_KEY_MAP[key]] = map(str, rules[key])
    else:
      bundle.pop('match', None)

    self._UploadAndDeployConfig(config)

    return self.ListOne(bundle['bundle_id'])

  def ReorderBundles(self, new_order):
    """Reorder the bundles in Umpire config.

    TODO(littlecvr): make sure this also works if multiple users are using at
                     the same time.

    Args:
      new_order: a list of bundle names.
    """
    old_config = self._GetNormalizedActiveConfig()

    # make sure all names are in current config
    old_bundle_set = set(b['id'] for b in old_config['bundles'])
    new_bundle_set = set(new_order)
    if old_bundle_set != new_bundle_set:
      raise ValueError('When reordering, all bundles must be listed')

    new_config = old_config.copy()
    new_config['rulesets'] = []
    for name in new_order:
      new_config['rulesets'].append(
          next(r for r in old_config['rulesets'] if r['bundle_id'] == name))

    self._UploadAndDeployConfig(new_config)

    return self.ListAll()

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

    self.umpire_server.Update(
        [(resource_type, resource_file_path)], src_bundle_name, dst_bundle_name)

    # Umpire does not allow the user to add bundle note directly via update. So
    # duplicate the source bundle first.
    self.umpire_status = self.umpire_server.GetStatus()
    config = yaml.load(self.umpire_status['staging_config'])

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

    # config staged before, need the force argument or Umpire will complain
    self._UploadAndDeployConfig(config, force=True)

    return self.ListOne(dst_bundle_name or src_bundle_name)

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
    self.umpire_server.ImportBundle(os.path.realpath(file_path), name, note)

    self.umpire_status = self.umpire_server.GetStatus()
    config = yaml.load(self.umpire_status['staging_config'])
    for ruleset in config['rulesets']:
      if ruleset['bundle_id'] == name:
        ruleset['active'] = True
        break

    self._UploadAndDeployConfig(config, force=True)

    # find and return the new bundle
    return self.ListOne(name)
