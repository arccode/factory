# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import hashlib
import os
import time
import urlparse

# pylint: disable=import-error, no-name-in-module
import certifi
from dulwich.client import HttpGitClient
from dulwich.objects import Blob
from dulwich.objects import Tree
from dulwich.refs import strip_peeled_refs
from dulwich.repo import MemoryRepo as _MemoryRepo
from urllib3 import PoolManager

import factory_common  # pylint: disable=unused-import


HEAD = 'HEAD'
DEFAULT_REMOTE_NAME = 'origin'
REF_HEADS_PREFIX = 'refs/heads/'
REF_REMOTES_PREFIX = 'refs/remotes/'


class GitUtilException(Exception):
  pass


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

    parsed = urlparse.urlparse(remote_location)

    pool_manager = PoolManager(ca_certs=certifi.where())
    pool_manager.headers['Cookie'] = self.auth_cookie

    client = HttpGitClient.from_parsedurl(parsed,
                                          config=self.get_config_stack(),
                                          pool_manager=pool_manager)
    fetch_result = client.fetch(
        parsed.path, self,
        determine_wants=lambda mapping: [mapping[REF_HEADS_PREFIX + branch]],
        depth=1)
    stripped_refs = strip_peeled_refs(fetch_result.refs)
    branches = {
        n[len(REF_HEADS_PREFIX):]: v for (n, v) in stripped_refs.items()
        if n.startswith(REF_HEADS_PREFIX)}
    self.refs.import_refs(
        REF_REMOTES_PREFIX + DEFAULT_REMOTE_NAME, branches)
    self[HEAD] = self[
        REF_REMOTES_PREFIX + '{remote_name}/{branch}'.format(
            remote_name=DEFAULT_REMOTE_NAME, branch=branch)]
    return client

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

    if path_splits:
      child_name = path_splits[0]
      if child_name in cur:
        unused_mode, sha = cur[child_name]
        sub = self[sha]
        if not isinstance(sub, Tree):  # if child_name exists but not a dir
          raise GitUtilException()
      else:
        # not exists, create a new tree
        sub = Tree()
      new_ids = self.recursively_add_file(
          sub, path_splits[1:], file_name, mode, blob)
      # 0o040000 is the mode of directory in git object pool
      cur.add(child_name, 0o040000, sub.id)
    else:
      # reach the directory of the target file
      if file_name in cur:
        unused_mod, sha = cur[file_name]
        existed_obj = self[sha]
        if not isinstance(existed_obj, Blob):
          # if file_name exists but not a Blob(file)
          raise GitUtilException()
      self.object_store.add_object(blob)
      new_ids = [blob.id]
      cur.add(file_name, mode, blob.id)

    self.object_store.add_object(cur)
    new_ids.append(cur.id)
    return new_ids

  def add_files(self, new_files, tree=None):
    """Add files to repository.

    Args:
      new_files: List of (file path, mode, file content)
      tree: Optional tree obj
    Returns:
      (updated tree, sha1 id strs of new objects)
    """

    if tree is None:
      head_commit = self[HEAD]
      tree = self[head_commit.tree]
    all_new_obj_ids = []
    for (file_path, mode, content) in new_files:
      path, filename = os.path.split(file_path)
      # os.path.normpath('') returns '.' which is unexpected
      paths = [x for x in os.path.normpath(path).split(os.sep)
               if x and x != '.']
      try:
        new_obj_ids = self.recursively_add_file(tree, paths, filename, mode,
                                                Blob.from_string(content))
      except GitUtilException:
        raise GitUtilException('Invalid filepath %r' % file_path)
      all_new_obj_ids += new_obj_ids

    return tree, all_new_obj_ids


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

  now = int(time.mktime(datetime.datetime.now().timetuple()))
  change_msg = ('tree {tree_id}\n'
                'parent {parent_commit}\n'
                'author {author} {now}\n'
                'committer {committer} {now}\n'
                '\n'
                '{commit_msg}').format(
                    tree_id=tree_id, parent_commit=parent_commit,
                    author=author, committer=committer, now=now,
                    commit_msg=commit_msg)
  change_id_input = 'commit {size}\x00{change_msg}'.format(
      size=len(change_msg), change_msg=change_msg)
  return 'I{}'.format(hashlib.sha1(change_id_input).hexdigest())


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
