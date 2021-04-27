# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Provide functionalities to access the HWID DB repository."""

from typing import NamedTuple

import yaml

from cros.factory.hwid.service.appengine import git_util
from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.utils import type_utils


class HWIDDBMetadata(NamedTuple):
  """A placeholder for metadata of a HWID DB."""
  name: str
  board_name: str
  version: int
  path: str


_INTERNAL_REPO_URL = 'https://chrome-internal-review.googlesource.com'
_CHROMEOS_HWID_PROJECT = 'chromeos/chromeos-hwid'


class HWIDRepoError(Exception):
  """Root exception class for reporting unexpected error in HWID repo."""


class HWIDRepo:
  _NAME_PATTERN_FOLDER = 'name_pattern'
  _AVL_NAME_MAPPING_FOLDER = 'avl_name_mapping'
  _PROJECTS_YAML_PATH = 'projects.yaml'

  def __init__(self, git_fs):
    """Constructor.

    Args:
      git_fs: The git file system adapter to the HWID repo.
    """
    self._git_fs = git_fs

  def IterNamePatterns(self):
    """Iterate through the name patterns recorded in the HWID repo.

    Yields:
      A tuple of (pattern name, pattern content).

    Raises:
      HWIDRepoError
    """
    try:
      for name in self._git_fs.ListFiles(self._NAME_PATTERN_FOLDER):
        content = self._git_fs.ReadFile(
            f'{self._NAME_PATTERN_FOLDER}/{name}').decode('utf-8')
        yield name, content
    except (KeyError, ValueError,
            filesystem_adapter.FileSystemAdapterException) as ex:
      raise HWIDRepoError(f'unable to retrieve name patterns: {ex}') from None

  def IterAVLNameMappings(self):
    """Iterate through the AVL name mappings recorded in the HWID repo.

    Yields:
      A tuple of (mapping file name, mapping file content).

    Raises:
      HWIDRepoError
    """
    try:
      for name in self._git_fs.ListFiles(self._AVL_NAME_MAPPING_FOLDER):
        content = self._git_fs.ReadFile(
            f'{self._AVL_NAME_MAPPING_FOLDER}/{name}').decode('utf-8')
        yield name, content
    except (KeyError, ValueError,
            filesystem_adapter.FileSystemAdapterException) as ex:
      raise HWIDRepoError(
          f'unable to retrive AVL name mappings: {ex}') from None

  def ListHWIDDBMetadata(self):
    """Returns a list of metadata of HWID DBs recorded in the HWID repo."""
    return list(self._hwid_db_metadata_of_name.values())

  def LoadHWIDDBByName(self, name):
    """Reads out the specific HWID DB content.

    Args:
      name: The project name of the HWID DB.  One can get the available names
          from the HWIDDBMetadata instances.

    Returns:
      A string of HWID DB content.

    Raises:
      ValueError if the given HWID DB name is invalid.
      HWIDRepoError for other unexpected errors.
    """
    try:
      path = self._hwid_db_metadata_of_name[name].path
    except KeyError:
      raise ValueError(f'invalid HWID DB name: {name}') from None
    try:
      return self._git_fs.ReadFile(path).decode('utf-8')
    except (KeyError, ValueError,
            filesystem_adapter.FileSystemAdapterException) as ex:
      raise HWIDRepoError(
          f'failed to load the HWID DB (name={name}): {ex}') from None

  @type_utils.LazyProperty
  def _hwid_db_metadata_of_name(self):
    try:
      raw_metadata = self._git_fs.ReadFile(self._PROJECTS_YAML_PATH)
    except (KeyError, ValueError,
            filesystem_adapter.FileSystemAdapterException) as ex:
      raise HWIDRepoError(
          f'failed to load {self._PROJECTS_YAML_PATH}: {ex}') from None
    try:
      metadata_yaml = yaml.safe_load(raw_metadata)
      hwid_db_metadata_of_name = {}
      for name, hwid_db_info in metadata_yaml.items():
        hwid_db_metadata_of_name[name] = HWIDDBMetadata(
            name, hwid_db_info['board'], hwid_db_info['version'],
            hwid_db_info['path'])
      return hwid_db_metadata_of_name
    except Exception as ex:
      raise HWIDRepoError(f'invalid {self._PROJECTS_YAML_PATH}: {ex}') from None


class HWIDRepoManager:

  def __init__(self, repo_branch):
    """Constructor.

    Args:
      repo_branch: The git branch name of the HWID repo to access.  Assigning
          `None` to use the default "main" branch.
    """
    self._repo_branch = repo_branch

  def GetLiveHWIDRepo(self):
    """Returns an HWIDRepo instance for accessing the up-to-date HWID repo."""
    if self._repo_branch is None:
      repo_branch = git_util.GetCurrentBranch(_INTERNAL_REPO_URL,
                                              _CHROMEOS_HWID_PROJECT,
                                              git_util.GetGerritAuthCookie())
    else:
      repo_branch = self._repo_branch
    git_fs = git_util.GitFilesystemAdapter.FromGitUrl(
        f'{_INTERNAL_REPO_URL}/{_CHROMEOS_HWID_PROJECT}', repo_branch,
        git_util.GetGerritAuthCookie())
    return HWIDRepo(git_fs)

  def GetMainCommitID(self):
    """Fetch the latest commit ID of the main branch on the upstream."""
    return git_util.GetCommitId(_INTERNAL_REPO_URL, _CHROMEOS_HWID_PROJECT,
                                auth_cookie=git_util.GetGerritAuthCookie())
