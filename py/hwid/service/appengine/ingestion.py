# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handler for ingestion."""

import cgi
import collections
import hashlib
import logging
import os
import traceback

# pylint: disable=import-error, no-name-in-module
from google.appengine.api.app_identity import app_identity
from google.appengine.api import mail
from google.appengine.api import taskqueue
from six import iteritems
import urllib3  # pylint: disable=import-error
import webapp2  # pylint: disable=import-error
import yaml

# pylint: disable=import-error
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import filesystem_adapter
from cros.factory.hwid.service.appengine import git_util
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import \
    verification_payload_generator as vpg_module
from cros.factory.utils import json_utils


GIT_NORMAL_FILE_MODE = 0o100644


def _AuthCheck(func):
  """Checks if requests are from known source.

  For /ingestion/refresh API, hwid service only allows cron job (via GET) and
  taskqueue (via POST) requests.  However, for e2e testing purpose, requests
  with API key are also allowed.
  """

  def wrapper(self, *args, **kwargs):
    if CONFIG.env == 'dev':  # for integration test
      return func(self, *args, **kwargs)

    from_cron = self.request.headers.get('X-AppEngine-Cron')
    if from_cron:
      logging.info('Allow cron job requests')
      return func(self, *args, **kwargs)

    from_taskqueue = self.request.headers.get('X-AppEngine-QueueName')
    if from_taskqueue:
      logging.info('Allow taskqueue requests')
      return func(self, *args, **kwargs)

    if CONFIG.ingestion_api_key:
      key = self.request.get('key')
      if key == CONFIG.ingestion_api_key:
        logging.info('Allow normal requests with API key')
        return func(self, *args, **kwargs)

    return self.abort(403, 'Permission denied')
  return wrapper


class DevUploadHandler(webapp2.RequestHandler):

  def __init__(self, request, response):  # pylint: disable=super-on-old-class
    super(DevUploadHandler, self).__init__(request, response)
    self._hwid_filesystem = CONFIG.hwid_filesystem

  def post(self):
    """Uploads a file to the cloud storage of the server."""
    if 'data' not in self.request.POST or 'path' not in self.request.POST:
      logging.warning('Required fields missing on request: %r',
                      self.request.POST)
      self.abort(400)

    data = self.request.POST['data']
    path = self.request.get('path')

    logging.debug('Got upload request: %r', self.request.POST)

    if not isinstance(data, cgi.FieldStorage):
      logging.warning('Got request without file in data field.')
      self.abort(400)

    self._hwid_filesystem.WriteFile(path, data.file.read())

    for filename in self._hwid_filesystem.ListFiles():
      self.response.write('%s\n' % filename)


class RefreshHandler(webapp2.RequestHandler):
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

  def __init__(self, request, response):  # pylint: disable=super-on-old-class
    super(RefreshHandler, self).__init__(request, response)
    self.hwid_filesystem = CONFIG.hwid_filesystem
    self.hwid_manager = CONFIG.hwid_manager
    self.vpg_targets = CONFIG.vpg_targets
    self.dryrun_upload = CONFIG.dryrun_upload
    self.hw_checker_mail = CONFIG.hw_checker_mail

  # Cron jobs are always GET requests, we are not acutally doing the work
  # here just queuing a task to be run in the background.
  @_AuthCheck
  def get(self):
    taskqueue.add(url='/ingestion/refresh')

  # Task queue executions are POST requests.
  @_AuthCheck
  def post(self):
    """Refreshes the ingestion from staging files to live."""

    # Limit boards for ingestion (e2e test only).
    limit_models = self.request.get('limit_models')
    do_limit = False
    if limit_models:
      limit_models = set(json_utils.LoadStr(limit_models))
      do_limit = True

    # TODO(yllin): Reduce memory footprint.
    # Get board.yaml
    try:
      metadata_yaml = self.hwid_filesystem.ReadFile('/staging/boards.yaml')

      # parse it
      metadata = yaml.safe_load(metadata_yaml)

      if limit_models:
        # only process required models
        metadata = {k: v for (k, v) in iteritems(metadata) if k in limit_models}
      self.hwid_manager.UpdateBoards(metadata, delete_missing=not do_limit)

    except filesystem_adapter.FileSystemAdaptorException:
      logging.error('Missing file during refresh.')
      self.abort(500, 'Missing file during refresh.')

    self.hwid_manager.ReloadMemcacheCacheFromFiles(
        limit_models=list(limit_models))

    # Skip if env is local (dev)
    if CONFIG.env == 'dev':
      self.response.write('Skip for local env')
      return

    self.UpdatePayloadsAndSync(do_limit)
    logging.info('Ingestion complete.')

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

  def GetMasterCommitIfChanged(self, auth_cookie, force_update=False):
    """Get master commit of repo if it differs from cached commit on datastore.

    Args:
      auth_cookie: Auth cookie for accessing repo.
      force_update: True for always returning commit id for testing purpose.
    Returns:
      latest commit id if it differs from cached commit id, None if not
    """

    hwid_master_commit = git_util.GetCommitId(
        'https://chrome-internal-review.googlesource.com',
        'chromeos/chromeos-hwid',
        'master',
        auth_cookie)
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

    payload_hash = hashlib.sha1(
        json_utils.DumpStr(payload_dict, sort_keys=True)).hexdigest()
    latest_hash = self.hwid_manager.GetLatestPayloadHash(board)

    if latest_hash == payload_hash and not force_update:
      logging.debug('Payload is not changed as %s, skipped', latest_hash)
      return None
    return payload_hash

  def TryCreateCL(
      self, service_account_name, auth_cookie, board, new_files,
      hwid_master_commit):
    """Try to create a CL if possible.

    Use git_util to create CL in repo for generated payloads.  If something goes
    wrong, email to the hw-checker group.

    Args:
      service_account_name: Account name as email
      auth_cookie: Auth cookie
      board: board name
      new_files: A path-content mapping of payload files
      hwid_master_commit: Commit of master branch of target repo
    Returns:
      None
    """

    dryrun_upload = self.dryrun_upload
    force_push = self.request.get('force_push', '')

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
    for filepath, filecontent in iteritems(new_files):
      new_git_files.append((
          os.path.join(prefix, filepath), GIT_NORMAL_FILE_MODE, filecontent))

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
      try:
        change_id = git_util.CreateCL(
            git_url, auth_cookie, project, branch, new_git_files,
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
        mail.send_mail(
            sender='ChromeOS HW Checker Bot <{}>'.format(self.hw_checker_mail),
            to=self.hw_checker_mail,
            subject=('[HW Checker] Cannot create CL of verification payload for'
                     ' board {board}'.format(board=board)),
            body=('Hi all,\n'
                  '\n'
                  'The CL of verification payloads is failed to create.\n'
                  'HWID DB commit: {commit}\n'
                  'Board: {board}\n'
                  '\n'
                  '{stack}\n').format(
                      board=board,
                      commit=hwid_master_commit,
                      stack=traceback.format_exc()))

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
    service_account_name = app_identity.get_service_account_name()
    token, unused_expiresAt = app_identity.get_access_token(
        'https://www.googleapis.com/auth/gerritcodereview')
    auth_cookie = 'o=git-{service_account_name}={token}'.format(
        service_account_name=service_account_name,
        token=token)

    hwid_master_commit = self.GetMasterCommitIfChanged(auth_cookie,
                                                       force_update)
    if hwid_master_commit is None and not force_update:
      return None, payload_hash_mapping

    db_lists = self.GetPayloadDBLists()

    for board, db_list in iteritems(db_lists):
      result = vpg_module.GenerateVerificationPayload(db_list)
      if result.error_msgs:
        logging.error('Generate Payload fail: %s', ' '.join(result.error_msgs))
        mail.send_mail(
            sender='ChromeOS HW Checker Bot <{}>'.format(self.hw_checker_mail),
            to=self.hw_checker_mail,
            subject=('[HW Checker] Cannot generate verification payload from'
                     ' board {board}'.format(board=board)),
            body=('Hi all,\n'
                  '\n'
                  'Verification payloads are failed to generate.\n'
                  'HWID DB commit: {commit}\n'
                  'Board: {board}\n'
                  '\n'
                  '{stack}\n').format(
                      board=board,
                      commit=hwid_master_commit,
                      stack=traceback.format_exc()))
      else:
        new_files = result.generated_file_contents
        payload_hash = self.GetPayloadHashIfChanged(board, new_files,
                                                    force_update)
        if payload_hash is not None:
          payload_hash_mapping[board] = payload_hash
          self.TryCreateCL(
              service_account_name, auth_cookie, board, new_files,
              hwid_master_commit)

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

    commit_id, payload_hash_mapping = self.UpdatePayloads(force_update)
    if commit_id:
      self.hwid_manager.SetLatestHWIDMasterCommit(commit_id)
    if force_update:
      self.response.write(json_utils.DumpStr(payload_hash_mapping,
                                             sort_keys=True))
    for board, payload_hash in iteritems(payload_hash_mapping):
      self.hwid_manager.SetLatestPayloadHash(board, payload_hash)
