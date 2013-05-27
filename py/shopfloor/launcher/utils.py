# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Shopfloor launcher utility functions and system wide config holder."""

import base64
import hashlib
import os
import re
import shutil

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher import ShopFloorLauncherException
from cros.factory.shopfloor.launcher.yamlconf import LauncherYAMLConfig
from cros.factory.test.utils import TryMakeDirs


def StartServices():
  """Starts all services."""
  for service in env.launcher_services:
    if not service.subprocess:
      service.Start()

def StopServices():
  """Stops all services."""
  for service in env.launcher_services:
    if service.subprocess:
      service.Stop()

def UpdateConfig(yaml_config_file):
  """Loads new launcher config file and restarts all services."""
  StopServices()
  env.launcher_config = LauncherYAMLConfig(yaml_config_file)
  env.launcher_services = GenerateServices()
  StartServices()

def GenerateServices():
  """Generates service list."""
  return map((lambda module: __import__(module, fromlist=['Service']).Service(
             env.launcher_config)), env.launcher_config['services'])

def SearchFile(filename, folders):
  """Gets first match of filename in folders.

  Args:
    filename: the file basename to find.
    folders: list of folders to be searched.

  Returns:
    First found file's full path name. None if not found.
  """
  for folder in folders:
    fullpathname = os.path.join(folder, filename)
    if os.path.isfile(fullpathname):
      return fullpathname
  return None

def CreateConfigSymlink(launcher_config_file):
  """Creates symbolic link to default startup YAML config file."""
  if not launcher_config_file.startswith(env.GetResourcesDir()):
    raise ShopFloorLauncherException('Config file should be in %r' %
                             env.GetResourcesDir())
  dest_file = os.path.join(env.runtime_dir, 'shopfloor.yaml')
  if os.path.exist(dest_file):
    os.unlink(dest_file)
  os.symlink(launcher_config_file, dest_file)

def GetResourceChecksum(string):
  """Checks if a string represents a resource filename.

  A resource filename is a Unix filename with '#' followed by 8 hex-digits checksum.

  Args:
    string: a string to be checked.

  Returns:
    Checksum if string is a resource filename. None otherwise.
  """
  if not isinstance(string, str):
    return None

  match = re.match(r'^[\w.-]+#([0-9a-f]{8})$', string)
  return match.group(1) if match else None

def ListResources(launcher_config_file=None):
  """Collects all resource files from an YAML config file.

  Args:
    launcher_config_file: launcher YAML config file basename to check.
        None if the system default one to be used.

  Returns:
    List of resource file basenames indicated in the YAML config.
  """
  def _GetResourceLeaves(node):
    """Iterates through an YAML tree to get resources listed inside."""
    if isinstance(node, dict):
      for item in node.itervalues():
        _GetResourceLeaves(item)
    elif isinstance(node, (list, tuple)):
      for item in node:
        _GetResourceLeaves(item)
    else:
      if GetResourceChecksum(node):
        yield node

  if launcher_config_file:
    config = LauncherYAMLConfig(launcher_config_file)
  else:
    config = env.launcher_config

  return _GetResourceLeaves(config)

def Md5sum(filename):
  """Gets hex coded md5sum of input file."""
  return hashlib.md5(    # pylint: disable=E1101
      open(filename, 'rb').read()).hexdigest()

def B64Sha1(filename):
  """Gets standard base64 coded sha1 sum of input file."""
  return base64.standard_b64encode(hashlib.sha1(  # pylint: disable=E1101
      open(filename, 'rb').read()).digest())

def VerifyResource(resource_name):
  """Verifies resource file by checking the hashsum in the filename tail."""
  match = re.match(r'.+#([0-9a-f]{8})$', resource_name)
  if not match:
    raise ShopFloorLauncherException('Not a resource file: %r' % resource_name)
  hashsum = match.group(1)
  calculated_hashsum = Md5sum(resource_name)
  if not calculated_hashsum.startswith(hashsum):
    raise ShopFloorLauncherException('Hashsum mismatch %r' % resource_name)

def PrepareResources(resources):
  """Copies resource files to system resouce folder.

  Resources are static files with MD5 checksum appended in filename. This
  function verifies file integrity and copies them to system folder.

  Args:
    resources: list of full path name to resource files. If the sources
               file does not exist but already in system resource folder,
               this function verifies the target file integrity only.
  Raises:
    ShopFloorLauncherException: when the resource file does not exist,
    nor in system resource folder.
  """

  dest_dir = env.GetResourcesDir()
  for pathname in resources:
    if os.path.isfile(pathname):
      VerifyResource(pathname)
      # Copy the file and keep its state
      shutil.copy2(pathname, dest_dir)
    else:
      fname = os.path.basename(pathname)
      dest_resource_name = os.path.join(dest_dir, fname)
      if os.path.isfile(dest_resource_name):
        VerifyResource(dest_resource_name)
      else:
        raise ShopFloorLauncherException('File not found: %r' % fname)

def GetInfo():
  """Gets currunt running configuration info."""
  return '\n'.join([env.launcher_config['info']['version'],
                    env.launcher_config['info']['note']])

def CreateSystemFolders():
  """Creates folder for Uber ShopFloor installation."""
  dirs = ['', 'resources', 'run', 'log', 'dashboard']
  map((lambda folder: TryMakeDirs(os.path.join(constants.SHOPFLOOR_INSTALL_DIR,
      folder))), dirs)

