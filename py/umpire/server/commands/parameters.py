# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Action on parameter.

See Parameters for detail.
"""

import logging
import os

from cros.factory.umpire import common
from cros.factory.umpire.server import utils
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils


class _ParameterObject:
  """Provides operation on parameter objects.

  Properties:
    data: including files and dirs.
    files: parmeter component files.
    dirs: parameter directory.
  """
  def __init__(self, data):
    self.data = data

  @property
  def files(self):
    return self.data['files']

  @property
  def dirs(self):
    return self.data['dirs']

  def _FindComponentsByName(self, dir_id, name):
    """Return List of component(s) in given directory and component name.

    If name is None, return all components in this directory.
    """
    fs = [f for f in self.files if f['dir_id'] == dir_id]
    if name is not None:
      fs = [f for f in fs if f['name'] == name]
    return fs

  def _FindChildDirByName(self, parent_id, dir_name):
    """Return directory in given parent directory and directory name."""
    return next((d for d in self.dirs
                 if d['name'] == dir_name and d['parent_id'] == parent_id),
                None)

  def _FindComponentById(self, comp_id):
    """Return component with given id."""
    return next((c for c in self.files if c['id'] == comp_id), None)

  def _FindDirectoryById(self, dir_id):
    """Return directory with given id."""
    return next((d for d in self.dirs if d['id'] == dir_id), None)

  def _UpdateExistingComponent(self, component, rename, using_ver, dst_path):
    """Update existing component: revision, update new version, and rename."""
    if sum(attr is not None for attr in [rename, using_ver, dst_path]) > 1:
      raise common.UmpireError(
          'Intend to do multiple operations at the same time.')
    if dst_path:
      # update component to new version
      version_count = len(component['revisions'])
      component['revisions'].append(dst_path)
      component['using_ver'] = version_count
    elif using_ver is not None:
      # rollback component to existed version
      if not 0 <= using_ver < len(component['revisions']):
        raise common.UmpireError(
            'Intend to use invalid version of parameter %d.' % component['id'])
      component['using_ver'] = using_ver
    elif rename is not None:
      # rename component
      component['name'] = rename
    return component

  def _CreateComponent(self, dir_id, comp_name, dst_path):
    """Create new component."""
    comp_id = len(self.files)
    component = {
        'id': comp_id,
        'dir_id': dir_id,
        'name': comp_name,
        'using_ver': 0,
        'revisions': [dst_path]
    }
    self.files.append(component)
    return component

  def UpdateComponent(self, comp_id, dir_id, comp_name, using_ver, dst_path):
    """See UmpireEnv.UpdateParameterComponent for detail"""
    if comp_id is not None:
      component = self._FindComponentById(comp_id)
      rename = comp_name if comp_name != component['name'] else None
      if rename and self._FindComponentsByName(component['dir_id'], rename):
        raise common.UmpireError('Intend to rename to existing component.')
      return self._UpdateExistingComponent(component, rename, using_ver,
                                           dst_path)

    # check if same name component already existed in same dir
    existed_comp = self._FindComponentsByName(dir_id, comp_name)
    if existed_comp:
      # create file but name existed in same dir, view as updating version
      return self._UpdateExistingComponent(existed_comp[0], None,
                                           using_ver, dst_path)
    if using_ver is not None:
      raise common.UmpireError(
          'Intend to create component but assigned using_ver.')
    return self._CreateComponent(dir_id, comp_name, dst_path)

  def _UpdateExistingDirectory(self, directory, rename):
    """Update existing directory: rename."""
    if rename is not None:
      directory['name'] = rename
    return directory

  def _CreateDirectory(self, parent_id, dir_name):
    """Create new directory"""
    dir_id = len(self.dirs)
    new_dir = {
        'id': dir_id,
        'parent_id': parent_id,
        'name': dir_name
    }
    self.dirs.append(new_dir)
    return new_dir

  def UpdateDirectory(self, dir_id, parent_id, dir_name):
    """See UmpireEnv.UpdateParameterDirectory for detail."""
    if dir_id is not None:
      directory = self._FindDirectoryById(dir_id)
      rename = dir_name if dir_name != directory['name'] else None
      if rename and self._FindChildDirByName(directory['parent_id'], rename):
        raise common.UmpireError('Intend to rename to existing directory.')
      return self._UpdateExistingDirectory(directory, rename)

    existed_dir = self._FindChildDirByName(parent_id, dir_name)
    if existed_dir:
      # create dir but name existed in parent dir, directly return
      return existed_dir
    return self._CreateDirectory(parent_id, dir_name)

  def _GetDirIdByNameSpace(self, namespace):
    """Retrieve directory by given namespace."""
    if namespace is None:
      return None
    namespace = namespace.split('/')
    current_id = None
    for name in namespace:
      next_dir = self._FindChildDirByName(current_id, name)
      if next_dir is None:
        raise common.UmpireError('Directory namespace not exists.')
      current_id = next_dir['id']
    return current_id

  def GetComponentsAbsPath(self, namespace, name):
    """See UmpireEnv.QueryParameters for detail."""
    try:
      dir_id = self._GetDirIdByNameSpace(namespace)
    except common.UmpireError:
      logging.error('Intend to request non-existent namespace.')
      return []
    fs = self._FindComponentsByName(dir_id, name)
    return [(f['name'], f['revisions'][f['using_ver']]) for f in fs]


class Parameters:
  """Wraps ParameterObject and synchronize the data to parameter_json_file.

  Properties:
    env: UmpireEnv object.
  """

  def __init__(self, env):
    self._parameter_json_file = env.parameter_json_file
    self._parameters_dir = env.parameters_dir
    self._parameter = _ParameterObject(
        json_utils.LoadFile(self._parameter_json_file))

  def _DumpParameter(self):
    """Dump parameter to json file."""
    json_utils.DumpFile(self._parameter_json_file, self._parameter.data)

  def GetParameterDstPath(self, src_path):
    """Prepend file MD5 sum to file path"""
    original_filename = os.path.basename(src_path)
    md5sum = file_utils.MD5InHex(src_path)
    new_filemame = '.'.join([original_filename, md5sum])
    return os.path.join(self._parameters_dir, new_filemame)

  def _AddParameter(self, src_path):
    dst_path = self.GetParameterDstPath(src_path)
    utils.CheckAndMoveFile(src_path, dst_path, False)
    return dst_path

  def UpdateParameterComponent(self, comp_id, dir_id, comp_name, using_ver,
                               src_path):
    """Update a parameter component file.

    Support following types of actions:
      1) Create new component.
      2) Rollback component to existed version.
      3) Update component to new version.
      4) Rename component.

    Args:
      comp_id: component id. None if intend to create a new component.
      dir_id: directory id where the component will be created.
              None if component is at root directory.
      comp_name: new component name.
      using_ver: file version component will use.
      src_path: uploaded file path.

    Returns:
      Updated component dictionary.
    """
    dst_path = self._AddParameter(src_path) if src_path else None
    component = self._parameter.UpdateComponent(comp_id, dir_id, comp_name,
                                                using_ver, dst_path)
    self._DumpParameter()
    return component

  def GetParameterInfo(self):
    """Dump parameter info.

    Returns:
      Parameter dictionary, which contains component files and directories.
      {
        "files": FileComponent[],
        "dirs": Directory[]
      }
      FileComponent = {
        "id": number, // index
        "dir_id": number | null, // directory index
        "name": string, // component name
        "using_ver": number, // version to use, range: [0, len(revisions))
        "revisions": string[], // file paths
      }
      Directory = {
        "id": number, // index
        "parent_id": number | null, // parent directory index
        "name": string, // directory name
      }
    """
    return self._parameter.data

  def UpdateParameterDirectory(self, dir_id, parent_id, name):
    """Update a parameter directory.

    Support following types of actions:
      1) Create new directory.
      2) Rename directory.

    Args:
      parent_id: parent directory id where the dir will be created.
                 None if parent is root directory.
      name: new directory name.

    Returns:
      Updated directory dictionary.
    """
    directory = self._parameter.UpdateDirectory(dir_id, parent_id, name)
    self._DumpParameter()
    return directory

  def QueryParameters(self, namespace, name):
    """Gets file path of queried component(s).

    Args:
      namespace: relative directory path(separate by '/') of queried
                 component(s). None if they are in root directory.
      name: component name of queried component. None if queries all components
            under namespace.

    Returns:
      List of tuple(component name, file path)
    """
    return self._parameter.GetComponentsAbsPath(namespace, name)
