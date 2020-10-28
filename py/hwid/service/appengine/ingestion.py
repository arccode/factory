# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handler for ingestion."""

import collections
import hashlib
import http
import logging
import os
import os.path

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import flask
import flask.views
import google.auth
from google.auth.transport.requests import Request
from google.cloud import tasks
import urllib3
import werkzeug
import yaml
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import git_util
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import \
    verification_payload_generator as vpg_module
from cros.factory.hwid.v3 import filesystem_adapter
from cros.factory.utils import json_utils


INTERNAL_REPO_URL = 'https://chrome-internal-review.googlesource.com'
CHROMEOS_HWID_PROJECT = 'chromeos/chromeos-hwid'
CHROMEOS_HWID_REPO_URL = INTERNAL_REPO_URL + '/' + CHROMEOS_HWID_PROJECT


class PayloadGenerationException(Exception):
  """Exception to group similar excetpions for error reporting."""


def _GetCredentials():
  credential, unused_project_id = google.auth.default(scopes=[
      'https://www.googleapis.com/auth/gerritcodereview'])
  credential.refresh(Request())
  service_account_name = credential.service_account_email
  token = credential.token
  return service_account_name, token


def _GetAuthCookie():
  service_account_name, token = _GetCredentials()
  return 'o=git-{service_account_name}={token}'.format(
      service_account_name=service_account_name,
      token=token)


def _GetHwidRepoFilesystemAdapter():
  return git_util.GitFilesystemAdapter.FromGitUrl(CHROMEOS_HWID_REPO_URL,
                                                  _GetAuthCookie(),
                                                  CONFIG.hwid_repo_branch)


class DevUploadHandler(flask.views.MethodView):

  def __init__(self, *args, **kwargs):
    super(DevUploadHandler, self).__init__(*args, **kwargs)
    self._hwid_filesystem = CONFIG.hwid_filesystem

  def post(self):
    """Uploads a file to the cloud storage of the server."""
    if 'data' not in flask.request.files or 'path' not in flask.request.values:
      logging.warning('Required fields missing on request: %r',
                      flask.request.values)
      flask.abort(flask.Response(status=http.HTTPStatus.BAD_REQUEST))

    data = flask.request.files.get('data')
    path = flask.request.values.get('path')

    if not isinstance(data, werkzeug.datastructures.FileStorage):
      logging.warning('Got request without file in data field.')
      flask.abort(flask.Response(status=http.HTTPStatus.BAD_REQUEST))

    self._hwid_filesystem.WriteFile(path, data.read())

    def processFiles():
      for filename in self._hwid_filesystem.ListFiles():
        yield '%s\n' % filename
    return flask.Response(response=processFiles(), status=http.HTTPStatus.OK)


class SyncNamePatternHandler(flask.views.MethodView):
  """Sync name pattern from chromeos-hwid repo

  In normal circumstances the cron job triggers the refresh hourly, however it
  can be triggered by admins.  The actual work is done by the default
  background task queue.

  The task queue POSTS back into this hander to do the actual work.

  This handler will copy the name_pattern directory under chromeos-hwid dir to
  cloud storage.
  """
  NAME_PATTERN_FOLDER = 'name_pattern'
  AVL_NAME_MAPPING_FOLDER = 'avl_name_mapping'

  def __init__(self, *args, **kwargs):
    super(SyncNamePatternHandler, self).__init__(*args, **kwargs)
    self.hwid_filesystem = CONFIG.hwid_filesystem
    self.hwid_manager = CONFIG.hwid_manager

  # Cron jobs are always GET requests, we are not acutally doing the work
  # here just queuing a task to be run in the background.
  def get(self):
    client = tasks.CloudTasksClient()
    parent = client.queue_path(CONFIG.cloud_project, CONFIG.project_region,
                               CONFIG.queue_name)
    client.create_task(parent, {
        'app_engine_http_request': {
            'http_method': 'POST',
            'relative_uri': '/ingestion/sync_name_pattern'}})
    return flask.Response(status=http.HTTPStatus.OK)

  # Task queue executions are POST requests.
  def post(self):
    """Refreshes the ingestion from staging files to live."""
    git_fs = _GetHwidRepoFilesystemAdapter()

    folder = self.NAME_PATTERN_FOLDER
    existing_files = set(self.hwid_filesystem.ListFiles(folder))
    for name in git_fs.ListFiles(folder):
      path = '%s/%s' % (folder, name)
      content = git_fs.ReadFile(path)
      self.hwid_filesystem.WriteFile(path, content)
      existing_files.discard(name)
    # remove files not existed on repo but still on cloud storage
    for name in existing_files:
      path = '%s/%s' % (folder, name)
      self.hwid_filesystem.DeleteFile(path)

    category_set = self.hwid_manager.ListExistingAVLCategories()

    folder = self.AVL_NAME_MAPPING_FOLDER
    for name in git_fs.ListFiles(folder):
      path = '%s/%s' % (folder, name)
      category, unused_ext = os.path.splitext(name)
      content = git_fs.ReadFile(path)
      mapping = yaml.load(content)
      self.hwid_manager.SyncAVLNameMapping(category, mapping)
      category_set.discard(category)

    self.hwid_manager.RemoveAVLNameMappingCategories(category_set)

    return flask.Response(status=http.HTTPStatus.OK)


class RefreshHandler(flask.views.MethodView):
  """Handle update of possibley new yaml files.

  In normal circumstances the cron job triggers the refresh hourly, however it
  can be triggered by admins.  The actual work is done by the default
  background task queue.

  The task queue POSTS back into this hander to do the
  actual work.

  Refresing the data regularly take just over the 60 second timeout for
  interactive requests.  Using a task process extends this deadline to 10
  minutes which should be more than enough headroom for the next few years.
  """

  def __init__(self, *args, **kwargs):
    super(RefreshHandler, self).__init__(*args, **kwargs)
    self.hwid_filesystem = CONFIG.hwid_filesystem
    self.hwid_manager = CONFIG.hwid_manager
    self.vpg_targets = CONFIG.vpg_targets
    self.dryrun_upload = CONFIG.dryrun_upload
    self.hw_checker_mail = CONFIG.hw_checker_mail

  # Cron jobs are always GET requests, we are not acutally doing the work
  # here just queuing a task to be run in the background.
  def get(self):
    client = tasks.CloudTasksClient()
    parent = client.queue_path(CONFIG.cloud_project, CONFIG.project_region,
                               CONFIG.queue_name)
    client.create_task(parent, {
        'app_engine_http_request': {
            'http_method': 'POST',
            'relative_uri': '/ingestion/refresh'}})
    return flask.Response(status=http.HTTPStatus.OK)

  # Task queue executions are POST requests.
  def post(self):
    """Refreshes the ingestion from staging files to live."""

    # Limit boards for ingestion (e2e test only).
    limit_models = set()
    if flask.request.is_json:
      limit_models.update(flask.request.json.get('limit_models'))
    do_limit = bool(limit_models)

    git_fs = _GetHwidRepoFilesystemAdapter()
    # TODO(yllin): Reduce memory footprint.
    # Get projects.yaml
    try:
      metadata_yaml = git_fs.ReadFile('projects.yaml')

      # parse it
      metadata = yaml.safe_load(metadata_yaml)

      if do_limit:
        # only process required models
        metadata = {k: v for (k, v) in metadata.items() if k in limit_models}
      self.hwid_manager.UpdateBoards(git_fs, metadata,
                                     delete_missing=not do_limit)

    except filesystem_adapter.FileSystemAdapterException:
      logging.error('Missing file during refresh.')
      flask.abort(flask.Response('Missing file during refresh.',
                                 http.HTTPStatus.INTERNAL_SERVER_ERROR))

    self.hwid_manager.ReloadMemcacheCacheFromFiles(
        limit_models=list(limit_models))

    # Skip if env is local (dev)
    if CONFIG.env == 'dev':
      return flask.Response(response='Skip for local env',
                            status=http.HTTPStatus.OK)

    response = self.UpdatePayloadsAndSync(do_limit)
    logging.info('Ingestion complete.')
    return flask.Response(response=response, status=http.HTTPStatus.OK)

  def GetPayloadDBLists(self):
    """Get payload DBs specified in config.

    Returns:
      A dict in form of {board: list of database instances}
    """

    db_lists = collections.defaultdict(list)
    for model_name, model_info in self.vpg_targets.items():
      hwid_data = self.hwid_manager.GetBoardDataFromCache(model_name)
      if hwid_data is not None:
        db_lists[model_info.board].append(
            (hwid_data.database, model_info.waived_comp_categories))
      else:
        logging.error('Cannot get board data from cache for %r', model_name)
    return db_lists

  def GetMasterCommitIfChanged(self, force_update=False):
    """Get master commit of repo if it differs from cached commit on datastore.

    Args:
      force_update: True for always returning commit id for testing purpose.
    Returns:
      latest commit id if it differs from cached commit id, None if not
    """

    hwid_master_commit = git_util.GetCommitId(
        INTERNAL_REPO_URL, CHROMEOS_HWID_PROJECT, 'master', _GetAuthCookie())
    latest_commit = self.hwid_manager.GetLatestHWIDMasterCommit()

    if latest_commit == hwid_master_commit and not force_update:
      logging.debug('The HWID master commit %s is already processed, skipped',
                    hwid_master_commit)
      return None
    return hwid_master_commit

  def GetPayloadHashIfChanged(self, board, payload_dict, force_update=False):
    """Get payload hash if it differs from cached hash on datastore.

    Args:
      board: Board name
      payload_dict: A path-content mapping of payload files
      force_update: True for always returning payload hash for testing purpose.
    Returns:
      hash if it differs from cached hash, None if not
    """

    payload = json_utils.DumpStr(payload_dict, sort_keys=True)
    payload_hash = hashlib.sha1(payload.encode('utf-8')).hexdigest()
    latest_hash = self.hwid_manager.GetLatestPayloadHash(board)

    if latest_hash == payload_hash and not force_update:
      logging.debug('Payload is not changed as %s, skipped', latest_hash)
      return None
    return payload_hash

  def TryCreateCL(self, service_account_name, board, new_files,
                  hwid_master_commit):
    """Try to create a CL if possible.

    Use git_util to create CL in repo for generated payloads.  If something goes
    wrong, email to the hw-checker group.

    Args:
      service_account_name: Account name as email
      board: board name
      new_files: A path-content mapping of payload files
      hwid_master_commit: Commit of master branch of target repo
    Returns:
      None
    """

    dryrun_upload = self.dryrun_upload
    force_push = flask.request.values.get('force_push', '')

    # force push, set dryrun_upload to False
    if force_push.lower() == 'true':
      dryrun_upload = False
    author = 'chromeoshwid <{account_name}>'.format(
        account_name=service_account_name)

    setting = hwid_manager.HwidManager.GetVerificationPayloadSettings(board)
    review_host = setting['review_host']
    repo_host = setting['repo_host']
    repo_path = setting['repo_path']
    git_url = repo_host + repo_path
    project = setting['project']
    branch = setting['branch']
    prefix = setting['prefix']
    reviewers = self.hwid_manager.GetCLReviewers()
    ccs = self.hwid_manager.GetCLCCs()
    new_git_files = []
    for filepath, filecontent in new_files.items():
      new_git_files.append((os.path.join(prefix, filepath),
                            git_util.NORMAL_FILE_MODE, filecontent))

    commit_msg = (
        'verification payload: update payload from hwid\n'
        '\n'
        'From chromeos/chromeos-hwid: %s\n' % (hwid_master_commit,))

    if dryrun_upload:
      # file_info = (file_path, mode, content)
      file_paths = ['  ' + file_info[0] for file_info in new_git_files]
      dryrun_upload_info = ('Dryrun upload to {project}\n'
                            'git_url: {git_url}\n'
                            'branch: {branch}\n'
                            'reviewers: {reviewers}\n'
                            'ccs: {ccs}\n'
                            'commit msg:\n'
                            '{commit_msg}\n'
                            'update file paths:\n'
                            '{file_paths}\n').format(
                                project=project,
                                git_url=git_url,
                                branch=branch,
                                reviewers=reviewers,
                                ccs=ccs,
                                commit_msg=commit_msg,
                                file_paths='\n'.join(file_paths))
      logging.debug(dryrun_upload_info)
    else:
      auth_cookie = _GetAuthCookie()
      try:
        change_id = git_util.CreateCL(
            git_url, auth_cookie, branch, new_git_files,
            author, author, commit_msg, reviewers, ccs)
        if CONFIG.env != 'prod':  # Abandon the test CL to prevent confusion
          try:
            git_util.AbandonCL(review_host, auth_cookie, change_id)
          except (git_util.GitUtilException,
                  urllib3.exceptions.HTTPError) as ex:
            logging.error('Cannot abandon CL for %r: %r', change_id, str(ex))
      except git_util.GitUtilNoModificationException:
        logging.debug('No modification is made, skipped')
      except git_util.GitUtilException as ex:
        logging.error('CL is not created: %r', str(ex))
        raise PayloadGenerationException('CL is not created') from ex

  def UpdatePayloads(self, force_update=False):
    """Update generated payloads to repo.

    Also return the hash of master commit and payloads to skip unnecessary
    actions.

    Args:
      force_update: True for always returning payload_hash_mapping for testing
                    purpose.

    Returns:
      tuple (commit_id, {board: payload_hash,...}), possibly None for commit_id
    """

    payload_hash_mapping = {}
    service_account_name, unused_token = _GetCredentials()
    hwid_master_commit = self.GetMasterCommitIfChanged(force_update)
    if hwid_master_commit is None and not force_update:
      return None, payload_hash_mapping

    db_lists = self.GetPayloadDBLists()

    for board, db_list in db_lists.items():
      result = vpg_module.GenerateVerificationPayload(db_list)
      if result.error_msgs:
        logging.error('Generate Payload fail: %s', ' '.join(result.error_msgs))
        raise PayloadGenerationException('Generate Payload fail')
      new_files = result.generated_file_contents
      payload_hash = self.GetPayloadHashIfChanged(board, new_files,
                                                  force_update)
      if payload_hash is not None:
        payload_hash_mapping[board] = payload_hash
        self.TryCreateCL(
            service_account_name, board, new_files, hwid_master_commit)

    return hwid_master_commit, payload_hash_mapping

  def UpdatePayloadsAndSync(self, force_update=False):
    """Update generated payloads to private overlays.

    This method will handle the payload creation request as follows:

      1. Check if the master commit of HWID DB is the same as cached one on
         Datastore and exit if they match.
      2. Generate a dict of board->payload_hash by vpg_module.
      3. Check if the cached payload hashs of boards in Datastore and generated
         ones match.
      4. Create a CL for each board if the generated payload hash differs from
         cached one.

    To prevent duplicate error notification or unnecessary check next time, this
    method will store the commit hash and payload hash in Datastore once
    generated.

    Args:
      force_update: True for always getting payload_hash_mapping for testing
                    purpose.
    """

    response = ''
    commit_id, payload_hash_mapping = self.UpdatePayloads(force_update)
    if commit_id:
      self.hwid_manager.SetLatestHWIDMasterCommit(commit_id)
    if force_update:
      response = json_utils.DumpStr(payload_hash_mapping, sort_keys=True)
    for board, payload_hash in payload_hash_mapping.items():
      self.hwid_manager.SetLatestPayloadHash(board, payload_hash)
    return response
