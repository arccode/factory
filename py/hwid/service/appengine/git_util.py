# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import hashlib
import httplib
import logging
import os
import time
import urllib
import urlparse

# pylint: disable=import-error, no-name-in-module
import certifi
from dulwich.client import HttpGitClient
from dulwich.objects import Blob
from dulwich.objects import Tree
from dulwich.pack import pack_objects_to_data
from dulwich.refs import strip_peeled_refs
from dulwich.repo import MemoryRepo as _MemoryRepo
import urllib3.exceptions
from urllib3 import PoolManager

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import json_utils


HEAD = 'HEAD'
DEFAULT_REMOTE_NAME = 'origin'
REF_HEADS_PREFIX = 'refs/heads/'
REF_REMOTES_PREFIX = 'refs/remotes/'


class GitUtilException(Exception):
  pass


class GitUtilNoModificationException(GitUtilException):
  """Raised if no modification is made for commit."""


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
          raise GitUtilException
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
          raise GitUtilException
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
             committer, commit_msg, reviewers=None, cc=None):
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
    reviewers: List of emails of reviewers
    cc: List of emails of cc's
  Returns:
    change id
  """

  def _generate_pack_data_wrapper(obj_store, new_obj_ids):
    """Patched generate_pack_data.

    In client.send_pack, we customize generate_pack_data instead of using
    object_store.generate_pack_data since we know what objects are needed in new
    commit instead of comparing commits between local and remote which is
    currently not supported if shallow clone is applied
    """

    def wrapper(*unused_args, **unused_kwargs):
      return pack_objects_to_data(obj_store.iter_shas(
          (id, None) for id in new_obj_ids))
    return wrapper

  repo = MemoryRepo(auth_cookie=auth_cookie)
  # only fetches last commit
  client = repo.shallow_clone(git_url, branch=branch)
  head_commit = repo[HEAD]
  original_tree_id = head_commit.tree
  updated_tree, new_obj_ids = repo.add_files(new_files)
  if updated_tree.id == original_tree_id:
    raise GitUtilNoModificationException

  change_id = _GetChangeId(
      updated_tree.id, repo.head(), author, committer, commit_msg)
  new_commit = repo.do_commit(
      commit_msg + '\n\nChange-Id: {change_id}'.format(change_id=change_id),
      author=author, committer=committer, tree=updated_tree.id)
  new_obj_ids.append(new_commit)

  notification = []
  if reviewers:
    notification += ['r=' + email for email in reviewers]
  if cc:
    notification += ['cc=' + email for email in cc]
  target_branch = 'refs/for/' + branch
  if notification:
    target_branch += '%' + ','.join(notification)

  client.send_pack(
      '/' + project,
      # returns the only branch:hash mapping needed
      lambda unused_refs: {target_branch: new_commit},
      _generate_pack_data_wrapper(repo.object_store, new_obj_ids))
  return change_id


def GetCommitId(git_url_prefix, project, branch, auth_cookie):
  '''Get branch commit.

  Use the gerrit API to get the commit id.  Note that the response starts with a
  magic prefix line )]}' which should be stripped.

  Args:
    git_url: HTTPS repo url
    project: Project name
    branch: Branch name
    auth_cookie: Auth cookie
  '''

  git_url = '{git_url_prefix}/projects/{project}/branches/{branch}'.format(
      git_url_prefix=git_url_prefix,
      project=urllib.quote(project, safe=''),
      branch=urllib.quote(branch, safe=''))
  pool_manager = PoolManager(ca_certs=certifi.where())
  pool_manager.headers['Cookie'] = auth_cookie
  pool_manager.headers['Content-Type'] = 'application/json'
  try:
    r = pool_manager.urlopen('GET', git_url)
  except urllib3.exceptions.HTTPError:
    raise GitUtilException('Invalid url %r' % (git_url,))

  if r.status != httplib.OK:
    raise GitUtilException('Request unsuccessfully with code %s' %
                           (r.status,))

  try:
    stripped_json = r.data.split('\n', 1)[1]
    branch_info = json_utils.LoadStr(stripped_json)
  except Exception:
    raise GitUtilException('Response format Error: %r' % (r.data,))

  try:
    commit_hash = branch_info['revision']
  except KeyError as ex:
    raise GitUtilException('KeyError: %r' % str(ex))

  return commit_hash


def AbandonCL(review_host, auth_cookie, change_id):
  """Abandon a CL

  Args:
    review_host: Review host of repo
    auth_cookie: Auth cookie
    change_id: Change ID
  """

  git_url = '{review_host}/a/changes/{change_id}/abandon'.format(
      review_host=review_host,
      change_id=change_id)

  pool_manager = PoolManager(ca_certs=certifi.where())
  pool_manager.headers['Cookie'] = auth_cookie
  fp = pool_manager.urlopen(method='POST', url=git_url)
  if fp.status != httplib.OK:
    logging.error('HTTP Status: %d', fp.status)
    raise GitUtilException('Abandon failed for change id: %r' % (change_id,))
