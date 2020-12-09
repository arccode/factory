# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import datetime
import hashlib
import http.client
import logging
import os
import time
import urllib.parse

# pylint: disable=wrong-import-order, import-error
import certifi
from dulwich.client import HttpGitClient
from dulwich.objects import Blob
from dulwich.objects import Tree
from dulwich import porcelain
from dulwich.refs import strip_peeled_refs
from dulwich.repo import MemoryRepo as _MemoryRepo
import urllib3.exceptions
from urllib3 import PoolManager
# pylint: enable=wrong-import-order, import-error

from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.utils import json_utils


HEAD = b'HEAD'
DEFAULT_REMOTE_NAME = b'origin'
REF_HEADS_PREFIX = b'refs/heads/'
REF_REMOTES_PREFIX = b'refs/remotes/'
NORMAL_FILE_MODE = 0o100644
EXEC_FILE_MODE = 0o100755
DIR_MODE = 0o040000


def _B(s):
  """Convert str to bytes if needed."""
  return s if isinstance(s, bytes) else s.encode()


class GitUtilException(Exception):
  pass


class GitUtilNoModificationException(GitUtilException):
  """Raised if no modification is made for commit."""


class GitFilesystemAdapter(filesystem_adapter.FileSystemAdapter):
  def __init__(self, memory_repo):
    self._memory_repo = memory_repo

  class ExceptionMapper(contextlib.AbstractContextManager):

    def __exit__(self, value_type, value, traceback):
      if isinstance(value, GitUtilException):
        raise KeyError(value)
      if isinstance(value, Exception):
        raise filesystem_adapter.FileSystemAdapterException(str(value))

  EXCEPTION_MAPPER = ExceptionMapper()

  @classmethod
  def FromGitUrl(cls, url, branch, auth_cookie=''):
    repo = MemoryRepo(auth_cookie)
    repo.shallow_clone(url, branch)
    return cls(repo)

  @classmethod
  def GetExceptionMapper(cls):
    return cls.EXCEPTION_MAPPER

  def _ReadFile(self, path):
    head_commit = self._memory_repo[HEAD]
    root = self._memory_repo[head_commit.tree]
    mode, sha = root.lookup_path(self._memory_repo.get_object, _B(path))
    if mode != NORMAL_FILE_MODE:
      raise GitUtilException('Path %r is not a file' % (path,))
    return self._memory_repo[sha].data

  def _WriteFile(self, path, content):
    raise NotImplementedError('GitFilesystemAdapter is read-only.')

  def _DeleteFile(self, path):
    raise NotImplementedError('GitFilesystemAdapter is read-only.')

  def _ListFiles(self, prefix=None):
    if prefix is None:
      prefix = ''

    ret = []
    for name, mode, unused_data in self._memory_repo.list_files(prefix):
      if mode == NORMAL_FILE_MODE:
        ret.append(name)
    return ret


class MemoryRepo(_MemoryRepo):
  """Enhance MemoryRepo with push ability."""

  def __init__(self, auth_cookie, *args, **kwargs):
    """Init with auth_cookie."""
    _MemoryRepo.__init__(self, *args, **kwargs)
    self.auth_cookie = auth_cookie

  def shallow_clone(self, remote_location, branch):
    """Shallow clone objects of a branch from a remote server.

    Args:
      remote_location: String identifying a remote server
      branch: Branch
    """

    parsed = urllib.parse.urlparse(remote_location)

    pool_manager = PoolManager(ca_certs=certifi.where())
    pool_manager.headers['Cookie'] = self.auth_cookie
    # Suppress ResourceWarning
    pool_manager.headers['Connection'] = 'close'

    client = HttpGitClient.from_parsedurl(parsed,
                                          config=self.get_config_stack(),
                                          pool_manager=pool_manager)
    fetch_result = client.fetch(
        parsed.path, self,
        determine_wants=lambda mapping: [mapping[REF_HEADS_PREFIX +
                                                 _B(branch)]], depth=1)
    stripped_refs = strip_peeled_refs(fetch_result.refs)
    branches = {
        n[len(REF_HEADS_PREFIX):]: v for (n, v) in stripped_refs.items()
        if n.startswith(REF_HEADS_PREFIX)}
    self.refs.import_refs(
        REF_REMOTES_PREFIX + DEFAULT_REMOTE_NAME, branches)
    self[HEAD] = self[
        REF_REMOTES_PREFIX + DEFAULT_REMOTE_NAME + b'/' + _B(branch)]

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
      self.recursively_add_file(
          sub, path_splits[1:], file_name, mode, blob)
      cur.add(child_name, DIR_MODE, sub.id)
    else:
      # reach the directory of the target file
      if file_name in cur:
        unused_mod, sha = cur[file_name]
        existed_obj = self[sha]
        if not isinstance(existed_obj, Blob):
          # if file_name exists but not a Blob(file)
          raise GitUtilException
      self.object_store.add_object(blob)
      cur.add(file_name, mode, blob.id)

    self.object_store.add_object(cur)

  def add_files(self, new_files, tree=None):
    """Add files to repository.

    Args:
      new_files: List of (file path, mode, file content)
      tree: Optional tree obj
    Returns:
      updated tree
    """

    if tree is None:
      head_commit = self[HEAD]
      tree = self[head_commit.tree]
    for (file_path, mode, content) in new_files:
      path, filename = os.path.split(file_path)
      # os.path.normpath('') returns '.' which is unexpected
      paths = [_B(x) for x in os.path.normpath(path).split(os.sep)
               if x and x != '.']
      try:
        self.recursively_add_file(tree, paths, _B(filename), mode,
                                  Blob.from_string(_B(content)))
      except GitUtilException:
        raise GitUtilException('Invalid filepath %r' % file_path)

    return tree

  def list_files(self, path):
    """List files under specific path.

    Args:
      path: the path of dir
    Returns:
      A generator that generates (name, mode, content) of files under the
      path.  if the entry is a directory, content will be None instead.
    """

    head_commit = self[HEAD]
    root = self[head_commit.tree]
    try:
      mode, sha = root.lookup_path(self.get_object, _B(path))
    except KeyError:
      raise GitUtilException('Path %r not found' % (path,))
    if mode not in (None, DIR_MODE):  # None for root directory
      raise GitUtilException('Path %r is not a directory' % (path,))
    tree = self[sha]
    for name, mode, file_sha in tree.items():
      obj = self[file_sha]
      yield (name.decode(), mode, obj.data
             if obj.type_name == b'blob' else None)


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
  return 'I{}'.format(hashlib.sha1(change_id_input.encode('utf-8')).hexdigest())


def CreateCL(git_url, auth_cookie, branch, new_files, author,
             committer, commit_msg, reviewers=None, cc=None):
  """Create a CL from adding files in specified location.

  Args:
    git_url: HTTPS repo url
    auth_cookie: Auth_cookie
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

  repo = MemoryRepo(auth_cookie=auth_cookie)
  # only fetches last commit
  repo.shallow_clone(git_url, branch=_B(branch))
  head_commit = repo[HEAD]
  original_tree_id = head_commit.tree
  updated_tree = repo.add_files(new_files)
  if updated_tree.id == original_tree_id:
    raise GitUtilNoModificationException

  change_id = _GetChangeId(
      updated_tree.id, repo.head(), author, committer, commit_msg)
  repo.do_commit(
      _B(commit_msg + '\n\nChange-Id: {change_id}'.format(change_id=change_id)),
      author=_B(author), committer=_B(committer),
      tree=updated_tree.id)

  notification = []
  if reviewers:
    notification += [b'r=' + email for email in reviewers]
  if cc:
    notification += [b'cc=' + email for email in cc]
  target_branch = b'refs/for/' + _B(branch)
  if notification:
    target_branch += b'%' + b','.join(notification)

  pool_manager = PoolManager(ca_certs=certifi.where())
  pool_manager.headers['Cookie'] = repo.auth_cookie
  porcelain.push(repo, git_url, HEAD + b':' + target_branch,
                 pool_manager=pool_manager)
  return change_id


def GetCurrentBranch(git_url_prefix, project, auth_cookie=''):
  '''Get the branch HEAD tracks.

  Use the gerrit API to get the branch name HEAD tracks.

  Args:
    git_url_prefix: HTTPS repo url
    project: Project name
    auth_cookie: Auth cookie
  '''

  git_url = '{git_url_prefix}/projects/{project}/HEAD'.format(
      git_url_prefix=git_url_prefix, project=urllib.parse.quote(
          project, safe=''))
  pool_manager = PoolManager(ca_certs=certifi.where())
  pool_manager.headers['Cookie'] = auth_cookie
  pool_manager.headers['Content-Type'] = 'application/json'
  # Suppress ResourceWarning
  pool_manager.headers['Connection'] = 'close'
  try:
    r = pool_manager.urlopen('GET', git_url)
  except urllib3.exceptions.HTTPError:
    raise GitUtilException('Invalid url %r' % (git_url, ))

  if r.status != http.client.OK:
    raise GitUtilException('Request unsuccessfully with code %s' % (r.status, ))

  try:
    # the response starts with a magic prefix line for preventing XSSI which
    # should be stripped.
    stripped_json = r.data.split(b'\n', 1)[1]
    branch_name = json_utils.LoadStr(stripped_json)
  except Exception:
    raise GitUtilException('Response format Error: %r' % (r.data, ))

  if branch_name.startswith(REF_HEADS_PREFIX.decode()):
    branch_name = branch_name[len(REF_HEADS_PREFIX.decode()):]
  return branch_name


def GetCommitId(git_url_prefix, project, branch=None, auth_cookie=''):
  '''Get branch commit.

  Use the gerrit API to get the commit id.

  Args:
    git_url_prefix: HTTPS repo url
    project: Project name
    branch: Branch name, use the branch HEAD tracks if set to None.
    auth_cookie: Auth cookie
  '''
  branch = branch or GetCurrentBranch(git_url_prefix, project, auth_cookie)

  git_url = '{git_url_prefix}/projects/{project}/branches/{branch}'.format(
      git_url_prefix=git_url_prefix,
      project=urllib.parse.quote(project, safe=''),
      branch=urllib.parse.quote(branch, safe=''))
  pool_manager = PoolManager(ca_certs=certifi.where())
  pool_manager.headers['Cookie'] = auth_cookie
  pool_manager.headers['Content-Type'] = 'application/json'
  # Suppress ResourceWarning
  pool_manager.headers['Connection'] = 'close'
  try:
    r = pool_manager.urlopen('GET', git_url)
  except urllib3.exceptions.HTTPError:
    raise GitUtilException('Invalid url %r' % (git_url,))

  if r.status != http.client.OK:
    raise GitUtilException('Request unsuccessfully with code %s' %
                           (r.status,))

  try:
    # the response starts with a magic prefix line for preventing XSSI which
    # should be stripped.
    stripped_json = r.data.split(b'\n', 1)[1]
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
  if fp.status != http.client.OK:
    logging.error('HTTP Status: %d', fp.status)
    raise GitUtilException('Abandon failed for change id: %r' % (change_id,))
