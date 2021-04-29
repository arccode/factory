# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Handler for ingestion."""

import collections
import json
import logging
import os
import os.path

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import urllib3
import yaml
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.factory.hwid.service.appengine import auth
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import git_util
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_repo
from cros.factory.hwid.service.appengine import memcache_adapter
from cros.factory.hwid.service.appengine import \
    verification_payload_generator as vpg_module
from cros.factory.hwid.v3 import filesystem_adapter
# pylint: disable=import-error, no-name-in-module
from cros.factory.hwid.service.appengine.proto import ingestion_pb2
# pylint: enable=import-error, no-name-in-module
from cros.factory.probe_info_service.app_engine import protorpc_utils


GOLDENEYE_MEMCACHE_NAMESPACE = 'SourceGoldenEye'


class PayloadGenerationException(protorpc_utils.ProtoRPCException):
  """Exception to group similar exceptions for error reporting."""

  def __init__(self, msg):
    super(PayloadGenerationException, self).__init__(
        protorpc_utils.RPCCanonicalErrorCode.INTERNAL, detail=msg)


class ProtoRPCService(protorpc_utils.ProtoRPCServiceBase):
  SERVICE_DESCRIPTOR = ingestion_pb2.DESCRIPTOR.services_by_name[
      'HwidIngestion']

  NAME_PATTERN_FOLDER = 'name_pattern'
  AVL_NAME_MAPPING_FOLDER = 'avl_name_mapping'

  def __init__(self, *args, **kwargs):
    super(ProtoRPCService, self).__init__(*args, **kwargs)
    self.hwid_filesystem = CONFIG.hwid_filesystem
    self.hwid_manager = CONFIG.hwid_manager
    self.vpg_targets = CONFIG.vpg_targets
    self.dryrun_upload = CONFIG.dryrun_upload
    self.hwid_repo_manager = CONFIG.hwid_repo_manager

  @protorpc_utils.ProtoRPCServiceMethod
  @auth.RpcCheck
  def SyncNamePattern(self, request):
    """Sync name pattern from chromeos-hwid repo

    In normal circumstances the cron job triggers the refresh hourly, however it
    can be triggered by admins.  The actual work is done by the default
    background task queue.

    The task queue POSTs back into this handler to do the actual work.

    This handler will copy the name_pattern directory under chromeos-hwid dir to
    cloud storage.
    """

    del request  # unused
    live_hwid_repo = self.hwid_repo_manager.GetLiveHWIDRepo()

    folder = self.NAME_PATTERN_FOLDER
    existing_files = set(self.hwid_filesystem.ListFiles(folder))
    for name, content in live_hwid_repo.IterNamePatterns():
      self.hwid_filesystem.WriteFile(f'{folder}/{name}',
                                     content.encode('utf-8'))
      existing_files.discard(name)
    # remove files not existed on repo but still on cloud storage
    for name in existing_files:
      self.hwid_filesystem.DeleteFile(f'{folder}/{name}')

    category_set = self.hwid_manager.ListExistingAVLCategories()

    for name, content in live_hwid_repo.IterAVLNameMappings():
      category, unused_ext = os.path.splitext(name)
      mapping = yaml.load(content)
      self.hwid_manager.SyncAVLNameMapping(category, mapping)
      category_set.discard(category)

    self.hwid_manager.RemoveAVLNameMappingCategories(category_set)

    return ingestion_pb2.SyncNamePatternResponse()

  @protorpc_utils.ProtoRPCServiceMethod
  @auth.RpcCheck
  def IngestHwidDb(self, request):
    """Handle update of possibly new yaml files.

    In normal circumstances the cron job triggers the refresh hourly, however it
    can be triggered by admins.  The actual work is done by the default
    background task queue.

    The task queue POSTs back into this handler to do the actual work.

    Refreshing the data regularly take just over the 60 second timeout for
    interactive requests.  Using a task process extends this deadline to 10
    minutes which should be more than enough headroom for the next few years.
    """

    # Limit projects for ingestion (e2e test only).
    limit_models = set(request.limit_models)
    do_limit = bool(limit_models)
    force_push = request.force_push

    live_hwid_repo = self.hwid_repo_manager.GetLiveHWIDRepo()
    # TODO(yllin): Reduce memory footprint.
    # Get projects.yaml
    try:
      hwid_db_metadata_list = live_hwid_repo.ListHWIDDBMetadata()

      if do_limit:
        # only process required models
        hwid_db_metadata_list = [
            x for x in hwid_db_metadata_list if x.name in limit_models
        ]
      self.hwid_manager.UpdateProjects(live_hwid_repo, hwid_db_metadata_list,
                                       delete_missing=not do_limit)

    except hwid_repo.HWIDRepoError as ex:
      logging.error('Got exception from HWID repo: %r.', ex)
      raise protorpc_utils.ProtoRPCException(
          protorpc_utils.RPCCanonicalErrorCode.INTERNAL,
          detail='Got exception from HWID repo.') from None

    self.hwid_manager.ReloadMemcacheCacheFromFiles(
        limit_models=list(limit_models))

    # Skip if env is local (dev)
    if CONFIG.env == 'dev':
      return ingestion_pb2.IngestHwidDbResponse(msg='Skip for local env')

    response = self._UpdatePayloadsAndSync(force_push, do_limit)
    logging.info('Ingestion complete.')
    return response

  @protorpc_utils.ProtoRPCServiceMethod
  @auth.RpcCheck
  def IngestDevicesVariants(self, request):
    """Retrieve the file, parse and save the project to HWID regexp mapping."""
    del request  # unused

    try:
      memcache = memcache_adapter.MemcacheAdapter(
          namespace=GOLDENEYE_MEMCACHE_NAMESPACE)
      all_devices_json = CONFIG.goldeneye_filesystem.ReadFile(
          'all_devices.json')
      parsed_json = json.loads(all_devices_json)

      regexp_to_device = []

      for device in parsed_json['devices']:
        regexp_to_project = []
        for board in device.get('boards', []):
          regexp_to_project.append(
              (board['hwid_match'], board['public_codename']))
          logging.info('Board: %s',
                       (board['hwid_match'], board['public_codename']))

        if device['hwid_match']:  # only allow non-empty patterns
          regexp_to_device.append(
              (device['hwid_match'], device['public_codename'],
               regexp_to_project))

          logging.info('Device: %s',
                       (device['hwid_match'], device['public_codename']))
        else:
          logging.warning('Empty pattern: %s',
                          (device['hwid_match'], device['public_codename']))

      memcache.Put('regexp_to_device', regexp_to_device)
    except filesystem_adapter.FileSystemAdapterException:
      logging.exception('Missing all_devices.json file during refresh.')
      raise protorpc_utils.ProtoRPCException(
          protorpc_utils.RPCCanonicalErrorCode.INTERNAL,
          detail='Missing all_devices.json file during refresh.')

    return ingestion_pb2.IngestDevicesVariantsResponse()

  def _GetPayloadDBLists(self):
    """Get payload DBs specified in config.

    Returns:
      A dict in form of {board: list of database instances}
    """

    db_lists = collections.defaultdict(list)
    for model_name, model_info in self.vpg_targets.items():
      hwid_data = self.hwid_manager.GetProjectDataFromCache(model_name)
      if hwid_data is not None:
        db_lists[model_info.board].append(
            (hwid_data.database, model_info.waived_comp_categories))
      else:
        logging.error('Cannot get board data from cache for %r', model_name)
    return db_lists

  def _GetMainCommitIfChanged(self, force_update):
    """Get main commit of repo if it differs from cached commit on datastore.

    Args:
      force_update: True for always returning commit id for testing purpose.
    Returns:
      latest commit id if it differs from cached commit id, None if not
    """

    hwid_main_commit = self.hwid_repo_manager.GetMainCommitID()
    latest_commit = self.hwid_manager.GetLatestHWIDMainCommit()

    if latest_commit == hwid_main_commit and not force_update:
      logging.debug('The HWID main commit %s is already processed, skipped',
                    hwid_main_commit)
      return None
    return hwid_main_commit

  def _ShouldUpdatePayload(self, board, result, force_update):
    """Get payload hash if it differs from cached hash on datastore.

    Args:
      board: Board name
      result: Instance of `VerificationPayloadGenerationResult`.
      force_update: True for always returning payload hash for testing purpose.
    Returns:
      A boolean which indicates if updating verification payload is needed.
    """

    if force_update:
      logging.info('Forcing an update as hash %s', result.payload_hash)
      return True

    latest_hash = self.hwid_manager.GetLatestPayloadHash(board)
    if latest_hash == result.payload_hash:
      logging.debug('Payload is not changed as %s, skipped', latest_hash)
      return False
    return True

  def _TryCreateCL(self, force_push, service_account_name, board, new_files,
                   hwid_main_commit):
    """Try to create a CL if possible.

    Use git_util to create CL in repo for generated payloads.  If something goes
    wrong, email to the hw-checker group.

    Args:
      force_push: True to always push to git repo.
      service_account_name: Account name as email
      board: board name
      new_files: A path-content mapping of payload files
      hwid_main_commit: Commit of main branch of target repo
    Returns:
      None
    """

    dryrun_upload = self.dryrun_upload

    # force push, set dryrun_upload to False
    if force_push:
      dryrun_upload = False
    author = 'chromeoshwid <{account_name}>'.format(
        account_name=service_account_name)

    setting = hwid_manager.HwidManager.GetVerificationPayloadSettings(board)
    review_host = setting['review_host']
    repo_host = setting['repo_host']
    repo_path = setting['repo_path']
    git_url = repo_host + repo_path
    project = setting['project']
    branch = setting['branch'] or git_util.GetCurrentBranch(
        review_host, project, git_util.GetGerritAuthCookie())
    prefix = setting['prefix']
    reviewers = self.hwid_manager.GetCLReviewers()
    ccs = self.hwid_manager.GetCLCCs()
    new_git_files = []
    for filepath, filecontent in new_files.items():
      new_git_files.append((os.path.join(
          prefix, filepath), git_util.NORMAL_FILE_MODE, filecontent))

    commit_msg = ('verification payload: update payload from hwid\n'
                  '\n'
                  'From chromeos/chromeos-hwid: %s\n' % (hwid_main_commit, ))

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
                                project=project, git_url=git_url, branch=branch,
                                reviewers=reviewers, ccs=ccs,
                                commit_msg=commit_msg,
                                file_paths='\n'.join(file_paths))
      logging.debug(dryrun_upload_info)
    else:
      auth_cookie = git_util.GetGerritAuthCookie()
      try:
        change_id = git_util.CreateCL(git_url, auth_cookie, branch,
                                      new_git_files, author, author, commit_msg,
                                      reviewers, ccs)
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

  def _UpdatePayloads(self, force_push, force_update):
    """Update generated payloads to repo.

    Also return the hash of main commit and payloads to skip unnecessary
    actions.

    Args:
      force_push: True to always push to git repo.
      force_update: True for always returning payload_hash_mapping for testing
                    purpose.
    Returns:
      tuple (commit_id, {board: payload_hash,...}), possibly None for commit_id
    """

    payload_hash_mapping = {}
    service_account_name, unused_token = git_util.GetGerritCredentials()
    hwid_main_commit = self._GetMainCommitIfChanged(force_update)
    if hwid_main_commit is None and not force_update:
      return None, payload_hash_mapping

    db_lists = self._GetPayloadDBLists()

    for board, db_list in db_lists.items():
      result = vpg_module.GenerateVerificationPayload(db_list)
      if result.error_msgs:
        logging.error('Generate Payload fail: %s', ' '.join(result.error_msgs))
        raise PayloadGenerationException('Generate Payload fail')
      new_files = result.generated_file_contents
      if self._ShouldUpdatePayload(board, result, force_update):
        payload_hash_mapping[board] = result.payload_hash
        self._TryCreateCL(force_push, service_account_name, board, new_files,
                          hwid_main_commit)
      self.hwid_manager.UpdatePrimaryIdentifiers(result.primary_identifiers)

    return hwid_main_commit, payload_hash_mapping

  def _UpdatePayloadsAndSync(self, force_push, force_update):
    """Update generated payloads to private overlays.

    This method will handle the payload creation request as follows:

      1. Check if the main commit of HWID DB is the same as cached one on
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
      force_push: True to always push to git repo.
      force_update: True for always getting payload_hash_mapping for testing
                    purpose.
    """

    response = ingestion_pb2.IngestHwidDbResponse()
    commit_id, payload_hash_mapping = self._UpdatePayloads(
        force_push, force_update)
    if commit_id:
      self.hwid_manager.SetLatestHWIDMainCommit(commit_id)
    if force_update:
      response.payload_hash.update(payload_hash_mapping)
    for board, payload_hash in payload_hash_mapping.items():
      self.hwid_manager.SetLatestPayloadHash(board, payload_hash)
    return response
