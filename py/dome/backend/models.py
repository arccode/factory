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

import contextlib
import copy
import errno
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import time
import traceback
import xmlrpclib

import django
import rest_framework.exceptions
import rest_framework.status
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import resource as umpire_resource
from cros.factory.utils import file_utils


# TODO(littlecvr): pull out the common parts between umpire and dome, and put
#                  them into a config file (using the new config API).
UMPIRE_BASE_PORT = 8080
UMPIRE_RPC_PORT_OFFSET = 2
UMPIRE_RSYNC_PORT_OFFSET = 4
UMPIRE_INSTALOG_SOCKET_PORT_OFFSET = 6
UMPIRE_MATCH_KEY_MAP = {
    'macs': 'mac',
    'serial_numbers': 'sn',
    'mlb_serial_numbers': 'mlb_sn'}

# TODO(littlecvr): use volume container instead of absolute path.
# TODO(littlecvr): these constants are shared between here and cros_docker.sh,
#                  should be pulled out to common config.
FACTORY_SERVER_IMAGE_NAME = 'cros/factory_server'
DOCKER_SHARED_DIR = '/cros_docker'
UMPIRE_DOCKER_DIR = '/cros_docker/umpire'
UMPIRE_DEFAULT_PROJECT_FILE = '.default_project'
UMPIRE_BASE_DIR_IN_UMPIRE_CONTAINER = '/var/db/factory/umpire'

TFTP_DOCKER_DIR = '/cros_docker/tftp'
TFTP_BASE_DIR_IN_TFTP_CONTAINER = '/var/tftp'
TFTP_CONTAINER_NAME = 'dome_tftp'

# Mount point of the Umpire data folder in Dome's container. Note: this is not
# Umpire base directory in Umpire's container (which is also
# '/var/db/factory/umpire', but they have nothing to do with each other). This
# is also not Umpire's base directory on host (which is '/cros_docker/umpire'
# for now).
# TODO(littlecvr): shared between here and cros_docker.sh, should be pulled out
#                  to a common config.
UMPIRE_BASE_DIR = '/var/db/factory/umpire'

UMPIRED_FILEPATH = '/usr/local/factory/bin/umpired'


logger = logging.getLogger('django.%s' % __name__)


class DomeException(rest_framework.exceptions.APIException):
  """Virtual base class of all Dome exceptions."""

  def __init__(self, detail=None, status_code=None):
    self.status_code = status_code or self.status_code
    super(DomeException, self).__init__(detail)


class DomeClientException(DomeException):
  """Errors that can be fixed by the client."""

  status_code = rest_framework.status.HTTP_400_BAD_REQUEST


class DomeServerException(DomeException):
  """Errors that cannot be fixed by the client."""

  status_code = rest_framework.status.HTTP_500_INTERNAL_SERVER_ERROR


@contextlib.contextmanager
def UploadedFile(temporary_uploaded_file_id):
  """Get corresponding file object based on its ID."""
  f = TemporaryUploadedFile.objects.get(pk=temporary_uploaded_file_id)
  try:
    yield f.file
  finally:
    f.delete()  # delete the entry in database
    path = UploadedFilePath(f.file)
    try:
      os.unlink(path)  # once the file has been used it can be removed
    except OSError as e:
      if e.errno != errno.ENOENT:  # don't care if it's been removed already
        raise
    try:
      os.rmdir(os.path.dirname(path))  # also try to remove empty directory
    except OSError as e:
      if e.errno != errno.ENOTEMPTY:  # but don't care if it's not empty
        raise


def UploadedFilePath(uploaded_file):
  """Return path to the uploaded file."""
  return os.path.join(django.conf.settings.MEDIA_ROOT, uploaded_file.name)


@contextlib.contextmanager
def UmpireAccessibleFile(project, uploaded_file):
  """Make a file uploaded from Dome accessible by a specific Umpire container.

  This function:
  1. Creates a temporary folder in the 'temp' folder.
  2. Copies the uploaded file to the temporary folder.
  3. Runs chmod on the folder and file to make sure they are Umpire readable.
  4. Removes the temporary folder in the end.

  Note that we have to keep the original basename, or Umpire will have problem
  when extracting bundle archive files. Also, due to the way Umpire Docker is
  designed, it's not possible to move the file instead of copy now.

  TODO(b/31417203): provide an argument to choose from moving file instead of
                    copying (after the issue has been solved).

  Args:
    project: name of the project (used to construct Umpire container's name).
    uploaded_file: file field of TemporaryUploadedFile.
  """
  # TODO(b/31417203): Use volume container or named volume instead of
  #                   UMPIRE_BASE_DIR.
  with file_utils.TempDirectory(
      dir=os.path.join(UMPIRE_BASE_DIR, project, 'temp')) as temp_dir:
    old_path = UploadedFilePath(uploaded_file)
    new_path = os.path.join(temp_dir, os.path.basename(uploaded_file.name))
    logger.info('Making file accessible by Umpire, copying %r to %r',
                old_path, new_path)
    shutil.copy(old_path, new_path)

    # Make sure they're readable to Umpire.
    os.chmod(temp_dir, stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH)
    os.chmod(new_path, stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH)

    # The temp file:
    #   in Dome:   ${UMPIRE_BASE_DIR}/${project}/temp/${temp_dir}/${name}
    #   in Umpire: ${UMPIRE_BASE_DIR}/temp/${temp_dir}/${name}
    # so need to remove "${project}/"
    tokens = new_path.split('/')
    del tokens[-4]
    yield '/'.join(tokens)


def GetUmpireServer(project_name):
  # get URL of the project
  project = Project.objects.get(
      pk=project_name).ReplaceLocalhostWithDockerHostIP()
  url = 'http://%s:%d' % (project.umpire_host,
                          project.umpire_port + UMPIRE_RPC_PORT_OFFSET)
  return xmlrpclib.ServerProxy(url, allow_none=True)


def GetUmpireStatus(project_name):
  return GetUmpireServer(project_name).GetStatus()


def GenerateUploadToPath(unused_instance, filename):
  """Generate a unique file path string in django's media root.

  This callable is used by the file field of TemporaryUploadedFile. The main
  purpose of using a callable instead of a simple string is to preserve the
  original file name uploaded by the user. If using a simple string, and
  multiple files with the same name were uploaded at the same time, django would
  add a random suffix to the later one, making it losing its original file name.
  """
  # create media root if needed, or mkdtemp would fail
  try:
    os.makedirs(django.conf.settings.MEDIA_ROOT)
  except OSError as e:
    if e.errno != errno.EEXIST:
      raise

  # add a time string as prefix for better debugging experience
  temp_dir = tempfile.mkdtemp(prefix='%s-' % time.strftime('%Y%m%d%H%M%S'),
                              dir=django.conf.settings.MEDIA_ROOT)
  path = os.path.relpath(os.path.join(temp_dir, filename),
                         django.conf.settings.MEDIA_ROOT)
  logger.info('Uploading file to %r', path)
  return path


def DoesContainerExist(container_name):
  container_list = subprocess.check_output([
      'docker', 'ps', '--all', '--format', '{{.Names}}']).splitlines()
  return container_name in container_list


class DomeConfig(django.db.models.Model):

  id = django.db.models.IntegerField(default=0, primary_key=True, serialize=False)
  tftp_enabled = django.db.models.BooleanField(default=False)

  def CreateTFTPContainer(self):

    if DoesContainerExist(TFTP_CONTAINER_NAME):
      logger.info('TFTP container already exists')
      return self

    try:
      cmd = [
          'docker', 'run', '--detach',
          '--restart', 'unless-stopped',
          '--name', TFTP_CONTAINER_NAME,
          '--volume', '%s:%s' % (TFTP_DOCKER_DIR,
                                 TFTP_BASE_DIR_IN_TFTP_CONTAINER),
          '--net', 'host',
          FACTORY_SERVER_IMAGE_NAME,
          'dnsmasq', '--user=root', '--port=0',
          '--enable-tftp', '--tftp-root=%s' % TFTP_BASE_DIR_IN_TFTP_CONTAINER,
          '--no-daemon', '--no-resolv'
      ]
      logger.info('Running command %r', cmd)
      subprocess.check_call(cmd)
    except Exception:
      logger.error('Failed to create TFTP container')
      logger.exception(traceback.format_exc())
      self.DeleteTFTPContainer()
      raise

    self.tftp_enabled = True
    self.save()

    return self

  def DeleteTFTPContainer(self):
    logger.info('Deleting TFTP container')
    subprocess.call(['docker', 'rm', '-f', TFTP_CONTAINER_NAME])
    self.tftp_enabled = False
    self.save()
    return self

  def UpdateConfig(self, **kwargs):

    # enable or disable TFTP if necessary
    self.tftp_enabled = DoesContainerExist(TFTP_CONTAINER_NAME)
    if ('tftp_enabled' in kwargs and
        self.tftp_enabled != kwargs['tftp_enabled']):
      if kwargs['tftp_enabled']:
        self.CreateTFTPContainer()
      else:
        self.DeleteTFTPContainer()

    # update attributes assigned in kwargs
    for attr, value in kwargs.iteritems():
      if hasattr(self, attr):
        setattr(self, attr, value)
    self.save()

    return self


class TemporaryUploadedFile(django.db.models.Model):
  """Model to hold temporary uploaded files from user.

  The API of Dome is designed as: if a request contains N files, split it into
  (N+1) requests, with first N request uploading each file (encoded in
  multipart/form-data), and the last request sending other fields (encoded in
  JSON). Each file uploading request gets a file ID, in the last request, we
  refer to a file using its ID we got before.

  For example, if we want to send a request:
  {
    "foo": "bar",
    "hello": "world",
    "file01": a file object,
    "file02": another file object
  }
  We split it into 3 requests:
  1. Send {"file": a file object} in multipart/form-data, suppose we got ID
     1005.
  2. Send {"file": another file object} in multipart/form-data, suppose we got
     ID 1008.
  3. Send
     {
       "foo": "bar",
       "hello": "world",
       "file01": 1005,
       "file02": 1008
     }
     in JSON.
  """

  file = django.db.models.FileField(upload_to=GenerateUploadToPath)
  created = django.db.models.DateTimeField(auto_now_add=True)


class Project(django.db.models.Model):

  # TODO(littlecvr): max_length should be shared with Umpire and serializer
  name = django.db.models.CharField(max_length=200, primary_key=True)
  umpire_enabled = django.db.models.BooleanField(default=False)
  umpire_host = django.db.models.GenericIPAddressField(null=True)
  umpire_port = django.db.models.PositiveIntegerField(null=True)

  # TODO(littlecvr): add TFTP and Overlord ports

  class Meta(object):
    ordering = ['name']

  def ReplaceLocalhostWithDockerHostIP(self):
    # Dome is inside a docker container. If umpire_host is 'localhost', it is
    # not actually 'localhost', it is the docker host instead of docker
    # container. So we need to transform it to the docker host's IP.
    if self.umpire_host in ['localhost', '127.0.0.1']:
      self.umpire_host = Project._GetHostIP()
    return self

  def AddExistingUmpireContainer(self, host, port):
    """Add an existing Umpire container to the database."""
    container_name = Project.GetUmpireContainerName(self.name)
    logger.info('Adding Umpire container %r', container_name)
    if not DoesContainerExist(container_name):
      error_message = (
          'Container %s does not exist, Dome will not add a non-existing '
          'container into the database, please create a new one instead' %
          container_name)
      logger.error(error_message)
      raise DomeClientException(error_message)
    self.umpire_enabled = True
    self.umpire_host = host
    self.umpire_port = port
    self.save()
    return self

  def CreateUmpireContainer(self, port):
    """Create a local Umpire container from a factory toolkit."""
    # make sure the container does not exist
    container_name = Project.GetUmpireContainerName(self.name)
    logger.info('Creating Umpire container %r', container_name)
    if DoesContainerExist(container_name):
      error_message = (
          'Container %s already exists, Dome will not try to create a new one, '
          'please add the existing one instead' % container_name)
      logger.error(error_message)
      raise DomeClientException(error_message)

    try:
      # create and start a new container
      # TODO(littlecvr): this is almost identical to cros_docker.sh's
      #                  do_umpire_run() function, we should remove this
      #                  function in that script because this job should be
      #                  done by Dome only
      cmd = [
          'docker', 'run', '--detach', '--privileged',
          '--tmpfs', '/run:rw,size=16384k',
          '--volume', '/etc/localtime:/etc/localtime:ro',
          '--volume', '%s:/mnt' % DOCKER_SHARED_DIR,
          '--volume', '%s/%s:%s' % (UMPIRE_DOCKER_DIR,
                                    self.name,
                                    UMPIRE_BASE_DIR_IN_UMPIRE_CONTAINER),
          '--publish', '%d:%d' % (port, UMPIRE_BASE_PORT),
          '--publish', '%d:%d' % (port + UMPIRE_RPC_PORT_OFFSET,
                                  UMPIRE_BASE_PORT + UMPIRE_RPC_PORT_OFFSET),
          '--publish', '%d:%d' % (port + UMPIRE_RSYNC_PORT_OFFSET,
                                  UMPIRE_BASE_PORT + UMPIRE_RSYNC_PORT_OFFSET),
          '--publish', '%d:%d' % (port + UMPIRE_INSTALOG_SOCKET_PORT_OFFSET,
                                  UMPIRE_BASE_PORT +
                                  UMPIRE_INSTALOG_SOCKET_PORT_OFFSET),
          '--restart', 'unless-stopped',
          '--name', container_name,
          FACTORY_SERVER_IMAGE_NAME, UMPIRED_FILEPATH]
      logger.info('Running command %r', cmd)
      subprocess.check_call(cmd)
      # Update default project for 'cros_docker.sh umpire' commands.
      with open(os.path.join(UMPIRE_BASE_DIR,
                             UMPIRE_DEFAULT_PROJECT_FILE), 'w') as f:
        f.write(self.name)
    except Exception:
      logger.error('Failed to create Umpire container %r', container_name)
      logger.exception(traceback.format_exc())
      # remove container
      subprocess.call(['docker', 'stop', container_name])
      subprocess.call(['docker', 'rm', container_name])
      raise

    # push into the database
    return self.AddExistingUmpireContainer('localhost', port)

  def DeleteUmpireContainer(self):
    logger.info('Deleting Umpire container %r', self.name)
    container_name = Project.GetUmpireContainerName(self.name)
    subprocess.call(['docker', 'stop', container_name])
    subprocess.call(['docker', 'rm', container_name])
    self.umpire_enabled = False
    self.umpire_host = None
    self.umpire_port = None
    self.save()
    return self

  @staticmethod
  def _GetHostIP():
    # An easy way to get IP of the host. It's possible to install python
    # packages such as netifaces or pynetinfo into the container, but that
    # requires gcc to be installed and will thus increase the size of the
    # container (which we don't want). Alpine itself provides the package as
    # well, but it's on the edge branch and cannot be easily installed using the
    # apk command.
    ip = subprocess.check_output(
        'ip route | grep "^default"', shell=True).split()[2]
    return ip.strip()  # remove the trailing newline

  @staticmethod
  def GetUmpireContainerName(name):
    return 'umpire_%s' % name

  @staticmethod
  def CreateOne(name, **kwargs):
    logger.info('Creating new project %r', name)
    project = Project.objects.create(name=name)
    try:
      return Project.UpdateOne(project, **kwargs)
    except Exception:
      logger.error('Failed to create project %r', name)
      logger.exception(traceback.format_exc())
      # delete the entry if anything goes wrong
      try:
        Project.objects.get(pk=name).delete()
      except django.core.exceptions.ObjectDoesNotExist:
        pass
      except Exception:
        raise

  @staticmethod
  def UpdateOne(project, **kwargs):
    logger.info('Updating project %r', project.name)
    # enable or disable Umpire if necessary
    if ('umpire_enabled' in kwargs and
        project.umpire_enabled != kwargs['umpire_enabled']):
      if not kwargs['umpire_enabled']:
        project.DeleteUmpireContainer()
      else:
        if kwargs.get('umpire_add_existing_one', False):
          project.AddExistingUmpireContainer(kwargs['umpire_host'],
                                             kwargs['umpire_port'])
        else:  # create a new local instance
          project.CreateUmpireContainer(kwargs['umpire_port'])

    # update attributes assigned in kwargs
    for attr, value in kwargs.iteritems():
      if hasattr(project, attr):
        setattr(project, attr, value)
    project.save()

    return project


class Resource(object):

  def __init__(self, type_name, version):
    self.type = type_name
    self.version = version

  @staticmethod
  def CreateOne(project_name, type_name, file_id):
    umpire_server = GetUmpireServer(project_name)
    with UploadedFile(file_id) as f:
      with UmpireAccessibleFile(project_name, f) as p:
        payloads = umpire_server.AddPayload(p, type_name)
    return Resource(type_name, payloads[type_name]['version'])


class Bundle(object):
  """Represent a bundle in umpire."""

  def __init__(self, name, note, active, payloads, rules):
    self.name = name
    self.note = note
    self.active = active

    self.resources = {type_name: Resource(type_name, 'N/A')
                      for type_name in umpire_resource.PayloadTypeNames}
    for type_name in payloads:
      self.resources[type_name] = Resource(type_name,
                                           payloads[type_name]['version'])

    self.rules = {}
    for umpire_key in rules:
      key = next(
          k for (k, v) in UMPIRE_MATCH_KEY_MAP.iteritems() if v == umpire_key)
      self.rules[key] = rules[umpire_key]

  @staticmethod
  def _GetNormalizedActiveConfig(project_name):
    """Return the normalized version of Umpire active config."""
    umpire_status = GetUmpireStatus(project_name)
    config = yaml.load(umpire_status['active_config'])
    return Bundle._NormalizeConfig(config)

  @staticmethod
  def _UploadAndDeployConfig(project_name, config, force=False):
    """Upload and deploy config atomically."""
    umpire_server = GetUmpireServer(project_name)

    logger.info('Uploading Umpire config')
    staging_config_path = umpire_server.AddConfigFromBlob(
        yaml.dump(config, default_flow_style=False),
        umpire_resource.ConfigTypeNames.umpire_config)

    logger.info('Staging Umpire config')
    try:
      umpire_server.StageConfigFile(staging_config_path, force)
    except Exception as e:
      raise DomeServerException(
          'Cannot stage config file, make sure no one is editing Umpire config '
          'at the same time, and there is no staging config exists. Error '
          'message: %r' % e)

    logger.info('Deploying Umpire config')
    try:
      umpire_server.Deploy(staging_config_path)
    except xmlrpclib.Fault as e:
      logger.error('Deploying failed, will unstage Umpire config now, '
                   'error message from Umpire: %r', e.faultString)
      try:
        umpire_server.UnstageConfigFile()
      except xmlrpclib.Fault as e:
        logger.warning("Unstaging failed, doesn't matter, ignored, "
                       'error message from Umpire: %r', e.faultString)

      # TODO(littlecvr): we should probably refine Umpire's error message so
      #                  Dome has to forward the message to the user only
      #                  without knowing what's really happened
      if 'Missing default bundle' in e.faultString:
        raise DomeClientException(
            detail='Cannot remove or deactivate default bundle')
      else:
        raise DomeServerException(detail=e.faultString)

  @staticmethod
  def _NormalizeConfig(config):
    bundle_id_set = set(b['id'] for b in config['bundles'])

    # We do not allow multiple rulesets referring to the same bundle, so
    # duplicate the bundle if we have found such cases.
    ruleset_id_set = set()
    for r in config['rulesets']:
      # TODO(littlecvr): how to deal with a ruleset that refers to a
      #                  non-existing bundle?

      if r['bundle_id'] not in ruleset_id_set:
        ruleset_id_set.add(r['bundle_id'])
      else:  # need to duplicate
        # generate a new name, may generate very long _copy_copy_copy... at the
        # end if there are many conflicts
        new_name = r['bundle_id']
        while True:
          new_name = '%s_copy' % new_name
          if new_name not in ruleset_id_set and new_name not in bundle_id_set:
            ruleset_id_set.add(new_name)
            bundle_id_set.add(new_name)
            break

        # find the original bundle and duplicate it
        src_bundle = next(
            b for b in config['bundles'] if b['id'] == r['bundle_id'])
        dst_bundle = copy.deepcopy(src_bundle)
        dst_bundle['id'] = new_name
        config['bundles'].append(dst_bundle)

        # update the ruleset
        r['bundle_id'] = new_name

    # sort 'bundles' section by their IDs
    config['bundles'].sort(key=lambda b: b['id'])

    # We do not allow bundles exist in 'bundles' section but not in 'ruleset'
    # section.
    for b in config['bundles']:
      if b['id'] not in ruleset_id_set:
        ruleset_id_set.add(b['id'])
        config['rulesets'].append({'active': False,
                                   'bundle_id': b['id'],
                                   'note': b['note']})

    return config

  @staticmethod
  def _FromUmpireBundleAndRuleset(project_name, bundle, ruleset):
    """Take the target entry in the "bundles" and "rulesets" sections in Umpire
    config, and turns them into the Bundle entity in Dome.

    Args:
      bundle: the target bundle in the "bundles" section in Umpire config.
      ruleset: ruleset that refers the the target bundle in Umpire config.
    """
    payloads = GetUmpireServer(project_name).GetPayloadsDict(bundle['payloads'])
    return Bundle(bundle['id'],  # name
                  ruleset['note'],  # note
                  ruleset['active'],  # active
                  payloads,  # payloads
                  ruleset.get('match', {}))  # matching rules

  @staticmethod
  def DeleteOne(project_name, bundle_name):
    """Delete a bundle in Umpire config.

    Args:
      project_name: name of the project.
      bundle_name: name of the bundle to delete.
    """
    config = Bundle._GetNormalizedActiveConfig(project_name)
    if not any(b['id'] == bundle_name for b in config['bundles']):
      raise DomeClientException(
          detail='Bundle %s not found' % bundle_name,
          status_code=rest_framework.status.HTTP_404_NOT_FOUND)

    config['rulesets'] = [
        r for r in config['rulesets'] if r['bundle_id'] != bundle_name]
    config['bundles'] = [
        b for b in config['bundles'] if b['id'] != bundle_name]

    Bundle._UploadAndDeployConfig(project_name, config)

  @staticmethod
  def ListOne(project_name, bundle_name):
    """Return the bundle that matches the search criterion.

    Args:
      project_name: name of the project.
      bundle_name: name of the bundle to find, this corresponds to the "id"
          field in umpire config.
    """
    config = Bundle._GetNormalizedActiveConfig(project_name)

    logger.info('Finding bundle %r in project %r', bundle_name, project_name)
    try:
      ruleset = next(
          r for r in config['rulesets'] if r['bundle_id'] == bundle_name)
      bundle = next(b for b in config['bundles'] if b['id'] == bundle_name)
    except StopIteration:
      logger.exception(traceback.format_exc())
      error_message = 'Bundle %r does not exist' % bundle_name
      logger.error(error_message)
      raise DomeClientException(error_message)

    return Bundle._FromUmpireBundleAndRuleset(project_name, bundle, ruleset)

  @staticmethod
  def ListAll(project_name):
    """Return all bundles as a list.

    This function lists bundles in the following order:
    1. bundles in the 'rulesets' section
    2. bundles in the 'bunedles' section but not in the 'rulesets' section

    Args:
      project_name: name of the project.

    Return:
      A list of all bundles.
    """
    config = Bundle._GetNormalizedActiveConfig(project_name)

    bundle_dict = dict((b['id'], b) for b in config['bundles'])

    bundle_list = []
    for r in config['rulesets']:
      b = bundle_dict[r['bundle_id']]
      bundle_list.append(Bundle._FromUmpireBundleAndRuleset(project_name, b, r))

    return bundle_list

  @staticmethod
  def ModifyOne(project_name, src_bundle_name, dst_bundle_name=None,
                note=None, active=None, rules=None, resources=None):
    """Modify a bundle.

    Args:
      project_name: name of the project.
      src_bundle_name: name of the bundle to update.
      dst_bundle_name: if None, do an in-place update; otherwise, duplicate the
          bundle, name it dst_bundle_name, then update it.
      note: note of the bundle.
      active: True to make the bundle active, False to make the bundle inactive.
          None means no change.
      rules: rules to replace, this corresponds to Umpire's "match", see
          Umpire's doc for more info, None means no change.
      resources: a dict deserialized by ResourceSerializer, listing all
          resources that should be updated. If a resource is not listed, nothing
          would be changed to the particular resource, so the client can do
          partial update without listing all resources.
    """
    config = Bundle._GetNormalizedActiveConfig(project_name)

    try:
      src_bundle = next(
          b for b in config['bundles'] if b['id'] == src_bundle_name)
      src_ruleset = next(
          r for r in config['rulesets'] if r['bundle_id'] == src_bundle_name)
    except StopIteration:
      logger.exception(traceback.format_exc())
      error_message = 'Bundle %r does not exist' % src_bundle_name
      logger.error(error_message)
      raise DomeClientException(error_message)

    if not dst_bundle_name:
      # in-place update
      bundle = src_bundle
      ruleset = src_ruleset
    else:
      # not in-place update, duplicate the source bundle
      bundle = copy.deepcopy(src_bundle)
      # TODO(b/34264367): support unicode.
      bundle['id'] = str(dst_bundle_name)
      config['bundles'].insert(0, bundle)
      ruleset = copy.deepcopy(src_ruleset)
      # TODO(b/34264367): support unicode.
      ruleset['bundle_id'] = str(dst_bundle_name)
      config['rulesets'].insert(0, ruleset)
      config = Bundle._NormalizeConfig(config)

    if note is not None:
      # TODO(b/34264367): support unicode.
      # TODO(littlecvr): unit tests for unicode.
      bundle['note'] = str(note)
      ruleset['note'] = str(note)

    if active is not None:
      ruleset['active'] = active

    if rules is not None:
      # completely remove rules if it's not None but considered "False"
      if not rules:
        ruleset.pop('match', None)  # completely remove this key
      else:
        ruleset['match'] = {}
        for key, rule in rules.iteritems():
          if rule:  # add non-empty rule only
            ruleset['match'][UMPIRE_MATCH_KEY_MAP[key]] = map(str, rule)

    # only deploy if at least one thing has changed
    if (dst_bundle_name or note is not None or
        active is not None or rules is not None):
      Bundle._UploadAndDeployConfig(project_name, config)

    # update resources
    if resources is not None:
      for resource_key, resource in resources.iteritems():
        Bundle._UpdateResource(project_name, bundle['id'], resource_key,
                               resource['file_id'])

    return Bundle.ListOne(project_name, bundle['id'])

  @staticmethod
  def ReorderBundles(project_name, new_order):
    """Reorder the bundles in Umpire config.

    TODO(littlecvr): make sure this also works if multiple users are using at
                     the same time.

    Args:
      new_order: a list of bundle names.
    """
    old_config = Bundle._GetNormalizedActiveConfig(project_name)

    # make sure all names are in current config
    old_bundle_set = set(b['id'] for b in old_config['bundles'])
    new_bundle_set = set(new_order)
    if old_bundle_set != new_bundle_set:
      raise DomeClientException('All bundles must be listed when reordering')

    # build a map for fast query later
    rulesets = dict((r['bundle_id'], r) for r in old_config['rulesets'])

    # reorder bundles
    new_config = copy.deepcopy(old_config)
    new_config['rulesets'] = [rulesets[n] for n in new_order]

    Bundle._UploadAndDeployConfig(project_name, new_config)

    return Bundle.ListAll(project_name)

  @staticmethod
  def _UpdateResource(project_name, bundle_name, type_name, resource_file_id):
    """Update resource in a bundle.

    Args:
      project_name: name of the project.
      bundle_name: the bundle to update.
      type_name: An element of umpire_resource.PayloadTypeNames.
      resource_file_id: id of the resource file (id of TemporaryUploadedFile).
    """
    umpire_server = GetUmpireServer(project_name)
    with UploadedFile(resource_file_id) as f:
      with UmpireAccessibleFile(project_name, f) as p:
        umpire_server.Update([(type_name, p)], bundle_name)

    config = yaml.load(umpire_server.GetStatus()['staging_config'])

    # config staged before, need the force argument or Umpire will complain
    # TODO(littlecvr): we can actually deploy directly here
    Bundle._UploadAndDeployConfig(project_name, config, force=True)

  @staticmethod
  def UploadNew(project_name, bundle_name, bundle_note, bundle_file_id):
    """Upload a new bundle.

    Args:
      project_name: name of the project.
      bundle_name: name of the new bundle, in string. This corresponds to the
          "id" field in umpire config.
      bundle_note: commit message. This corresponds to the "note" field in
          umpire config.
      bundle_file_id: id of the bundle file (id of TemporaryUploadedFile).

    Return:
      The newly created bundle.
    """
    umpire_server = GetUmpireServer(project_name)

    with UploadedFile(bundle_file_id) as f:
      with UmpireAccessibleFile(project_name, f) as p:
        try:
          umpire_server.ImportBundle(p, bundle_name, bundle_note)
        except xmlrpclib.Fault as e:
          if 'already in use' in e.faultString:
            raise DomeClientException(
                detail='Bundle "%s" already exists' % bundle_name,
                status_code=rest_framework.status.HTTP_409_CONFLICT)
          else:
            raise DomeServerException(detail=e.faultString)

    config = yaml.load(umpire_server.GetStatus()['staging_config'])
    for ruleset in config['rulesets']:
      if ruleset['bundle_id'] == bundle_name:
        # TODO(b/34264367): support unicode.
        ruleset['note'] = str(bundle_note)
        ruleset['active'] = True
        break

    Bundle._UploadAndDeployConfig(project_name, config, force=True)

    # find and return the new bundle
    return Bundle.ListOne(project_name, bundle_name)
