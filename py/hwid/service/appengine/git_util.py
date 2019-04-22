# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=import-error, no-name-in-module
from dulwich.repo import MemoryRepo as _MemoryRepo

import factory_common  # pylint: disable=unused-import


class MemoryRepo(_MemoryRepo):
  """Enhance MemoryRepo with push ability."""

  def __init__(self, auth_cookie, *args, **kwargs):
    """Init with auth_cookie."""
    _MemoryRepo.__init__(self, *args, **kwargs)
    self.auth_cookie = auth_cookie

  def shallow_clone(self, remote_location, branch='master'):
    """Shallow clone objects of a branch from a remote server.

    Args:
      remote_location: String identifying a remote server
      branch: Branch
    Returns:
      client
    """

    raise NotImplementedError

  def recursively_add_file(self, cur, path_splits, file_name, mode, blob):
    """Add files in object store.

    Since we need to collect all tree objects with modified children, a
    recursively approach is applied

    Args:
      cur: Current tree obj
      path_splits: Directories between cur and file
      file_name: File name
      mode: File mode in git
      blob: Blob obj of the file
    Returns:
      A list of new object ids
    """

    raise NotImplementedError

  def add_files(self, new_files, tree=None):
    """Add files to repository.

    Args:
      new_files: List of (file path, mode, file content)
      tree: Optional tree obj
    Returns:
      (updated tree, sha1 id strs of new objects)
    """

    raise NotImplementedError


def _GetChangeId(tree_id, parent_commit, author, committer, commit_msg):
  """Get change id from information of commit.

  Implemented by referencing common .git/hooks/commit-msg script with some
  modification, this function is used to generate hash as a Change-Id based on
  the execution time and the information of the commit.  Since the commit-msg
  script may change, this function does not guarantee the consistency of the
  Change-Id with the commit-msg script in the future.

  Args:
    tree_id: Tree hash
    parent_commit: Parent commit
    author: Author in form of "Name <email@domain>"
    committer: Committer in form of "Name <email@domain>"
    commit_msg: Commit message
  Returns:
    hash of information as change id
  """

  raise NotImplementedError


def CreateCL(git_url, auth_cookie, project, branch, new_files, author,
             committer, commit_msg):
  """Create a CL from adding files in specified location.

  Args:
    git_url: HTTPS repo url
    auth_cookie: Auth_cookie
    project: Project name
    branch: Branch needs adding file
    new_files: List of (filepath, mode, bytes)
    author: Author in form of "Name <email@domain>"
    committer: Committer in form of "Name <email@domain>"
    commit_msg: Commit message
  Returns:
    change id
  """

  raise NotImplementedError
