#!/usr/bin/python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A reference demos uploading archives to Google."""

import argparse
import logging
import os
import sys
import threading
import time
import yaml

from common import (CheckAndLockFile, GetMetadataPath, GetOrCreateMetadata,
                    IsValidYAMLFile, RegenerateUploaderMetadataFile,
                    TimeString, UPLOADER_METADATA_DIRECTORY)
from importlib import import_module
from uploader_exception import UploaderError, UploaderFieldError

# Global variable to keep locked file open during process life-cycle
lock = None
# Supported protocol
PROTOCOL_MAPPING = {'SFTP': 'uploader_sftp'}

UPLOADER_LOCK_FILE = '.uploader.lock'
PARSING_ERROR_REST_SECS = 0.2
LOOP_DELAY = 1


class _Status(object):
  """Represents the status returned by _DetermineMetadataStatus."""
  RACING = 'Racing'
  UPLOADED_GREATER_THAN_EXPECTED = (
      'Uploaded bytes are greater than expected')
  DOWNLOADED_GREATER_THAN_EXPECTED = (
      'Downloaded bytes are greater than expected')
  UNKNOWN = 'Unknown'
  DOWNLOADING = 'Downloading'
  UPLOADING = 'Uploading'
  UPLOADED = 'Uploaded'


def _Uploader(config_path):
  """The starter of the uploader.

  config_path: The path to the uploader configuration.
  """
  global lock  # pylint: disable=W0603
  with open(config_path, 'r') as fd:
    uploader_config = yaml.load(fd.read())

  # Making sure we are the only one looking over file_pool.
  if 'uploader' not in uploader_config:
    raise UploaderFieldError(
        'No uploader information found in %r' % config_path)
  if 'file_pool' not in uploader_config['uploader']:
    raise UploaderFieldError(
        'No file_pool location under uploader section in configuration.' %
        config_path)
  file_pool = uploader_config['uploader']['file_pool']
  if not os.path.isdir(file_pool):
    raise UploaderFieldError(
        'file_pool %r is not a directory or does not exist.' % file_pool)
  # Try to lock the file_pool directory
  lock_file_path = os.path.join(file_pool, UPLOADER_LOCK_FILE)
  lock_ret = CheckAndLockFile(lock_file_path)
  if not isinstance(lock_ret, file):
    running_pid = lock_ret
    error_msg = (
        'file_pool[%r] is already monitored by another uploader.'
        'Lock %r cannot be acquired. Another uploader\'s PID '
        'might be %s' % (file_pool, lock_file_path, running_pid))
    logging.error(error_msg)
    raise UploaderFieldError(error_msg)
  # Add to global variable to live until this process ends.
  lock = (lock_ret, lock_file_path)
  logging.info('Successfully acquire advisory lock on %r, PID[%d]',
               lock_file_path, os.getpid())
  # TODO(itspeter): Clean up the locks when exiting process.

  # Load and establish sources and target.
  sources = []
  target = None
  # Validate each fields.
  if 'source' not in uploader_config:
    raise UploaderFieldError('No source information found in %r' % config_path)
  if 'target' not in uploader_config:
    raise UploaderFieldError('No target information found in %r' % config_path)

  # Establish sources
  for source_name, source_config in uploader_config['source'].iteritems():
    logging.info('Parsing source config [%r]', source_name)
    # Check its protocol.
    protocol = source_config.get('protocol', None)
    if protocol not in PROTOCOL_MAPPING:
      raise UploaderFieldError(
          'Protocol [%r] not supported at this time.' % protocol)
    source_module = import_module(PROTOCOL_MAPPING[protocol])
    source_obj = source_module.FetchSource()
    source_obj.LoadConfiguration(source_config, config_name=source_name)
    sources.append(source_obj)
    logging.info('Source config [%r] added', source_name)
  if len(sources) == 0:
    raise UploaderFieldError('source field contains zero sub-source config.')

  # Establish target
  logging.info('Parsing target config.')
  target_config = uploader_config['target']
  # Check its protocol.
  protocol = target_config.get('protocol', None)
  if protocol not in PROTOCOL_MAPPING:
    raise UploaderFieldError(
        'Protocol [%r] not supported at this time.' % protocol)
  target_module = import_module(PROTOCOL_MAPPING[protocol])
  target = target_module.UploadTarget()
  target.LoadConfiguration(target_config)
  logging.info('Target config loaded')

  # Start threads
  for source in sources:
    t = threading.Thread(target=_FetchSourceThread, args=(source, file_pool))
    t.daemon = True
    t.start()
  t = threading.Thread(target=_UploadTargetThread, args=(target, file_pool))
  t.daemon = True
  t.start()
  t.join()


def _DetermineMetadataStatus(file_pool, path_from_pool):
  """Determines a status in file_pool.

  Args:
    file_pool: The path of file_pool in local file system.
    path_from_pool:
      The path where the file we want to determine relative to file_pool. If
      the file doesn't exist, _Status.UNKNOWN will be returned.

  Returns:
    Returns the status listed in the class _Status.
  """
  local_full_path = os.path.join(file_pool, path_from_pool)
  metadata_path = GetMetadataPath(local_full_path, UPLOADER_METADATA_DIRECTORY)
  logging.debug('Determine status of %r.', local_full_path)

  if os.path.isfile(metadata_path):
    # Determine the file's status
    metadata = None
    metadata_last_modified = os.lstat(metadata_path).st_mtime
    with open(metadata_path, 'r') as fd:
      raw_metadata = fd.read()
      logging.debug('Raw content of %r=\n%s\n', metadata_path, raw_metadata)
    try:
      metadata = yaml.load(raw_metadata)
      if not isinstance(metadata, dict):
        raise UploaderError('Metadata %r is not a dict' % metadata_path)
      if not isinstance(metadata.get('file', None), dict):
        raise UploaderError(
            'Metadata %r does not contain file or file is not a dict' %
            metadata_path)
      expected_file_size = metadata['file'].get('size')
      if not expected_file_size:
        raise UploaderError(
            'Metadata %r does not contain size in file field' % metadata_path)

      # Check if file is downloaded.
      download_metadata = metadata.get('download', {})
      downloaded_bytes = download_metadata.get('downloaded_bytes', 0)

      if downloaded_bytes < expected_file_size:
        logging.debug('File %r is downloading.', local_full_path)
        return _Status.DOWNLOADING
      elif downloaded_bytes == expected_file_size:
        # Check if file is uploaded
        upload_metadata = metadata.get('upload', {})
        uploaded_bytes = upload_metadata.get('uploaded_bytes', 0)

        if uploaded_bytes < expected_file_size:
          logging.debug('File %r is uploading.', local_full_path)
          return _Status.UPLOADING
        elif uploaded_bytes == expected_file_size:
          logging.debug('File %r is uploaded.', local_full_path)
          return _Status.UPLOADED
        else:
          logging.debug(
              'File %r is abnormal. Uploaded %d bytes.'
              'More than expected %d bytes.',
              local_full_path, uploaded_bytes, expected_file_size)
          return _Status.UPLOADED_GREATER_THAN_EXPECTED

        # Will not actually able to determine precisely between a file
        # is downloaded or uploading solely on the metadata.
      else:
        logging.debug(
            'File %r is abnormal. Downloaded %d bytes.'
            'More than expected %d bytes.',
            local_full_path, downloaded_bytes, expected_file_size)
        return _Status.DOWNLOADED_GREATER_THAN_EXPECTED

    except UploaderError:
      logging.exception(
          'File %r\'s metadata is unlikely valid.', local_full_path)
      return _Status.UNKNOWN

    except yaml.YAMLError:
      # There are two possibility. One is the metadata is really a
      # corrupted one. Another is the reading racing with another
      # writing. To tackle the later one, we will look into the mtime
      # to see if this parsing error is a false alarm.
      time.sleep(PARSING_ERROR_REST_SECS)
      if metadata_last_modified == os.lstat(metadata_path).st_mtime:
        logging.exception(
            'File %r\'s metadata is unlikely valid.', local_full_path)
        return _Status.UNKNOWN
      else:
        # Leave the caller to determine further action.
        return _Status.RACING
  else:
    logging.debug('File %r\'s metadata doesn\'t exist.', local_full_path)
    return _Status.UNKNOWN


def _FetchSourceThread(source, file_pool):
  def _UpdateFileInMetadata(metadata_path, file_name, file_size, file_mtime):
    # Overwrite whatever metadata.
    metadata = GetOrCreateMetadata(
        metadata_path, RegenerateUploaderMetadataFile)
    file_metadata = metadata.setdefault('file', {})
    file_metadata.update({'name': file_name,
                          'size': file_size,
                          'last_modified': TimeString(file_mtime)})
    with open(metadata_path, 'w') as metadata_fd:
      metadata_fd.write(yaml.dump(metadata, default_flow_style=False))
    logging.debug('Metadata %r is re-generated.', metadata_path)

  while True:  # Run forever.
    time.sleep(LOOP_DELAY)
    # Getting basic data of files from the source.
    files = source.ListFiles()
    for source_rel_path, file_size, mtime in files:
      start_download = False
      resume = True

      local_full_path = os.path.join(file_pool, source_rel_path)
      status = _DetermineMetadataStatus(file_pool, source_rel_path)
      if status == _Status.UNKNOWN:
        # Re-generate the metadata and re-download. One of the common case
        # is the metadata is not existed and created the first time.
        _UpdateFileInMetadata(
            GetMetadataPath(local_full_path, UPLOADER_METADATA_DIRECTORY),
            source_rel_path, file_size, mtime)
        start_download = True
        resume = False
      elif status == _Status.DOWNLOADING:
        # According to the design, at any time, only one thread will be
        # responsible for downloading a file. This might be closed
        # unexpectedly in last session.
        start_download = True
        resume = True
      elif status == _Status.UPLOADING:
        pass  # Action only when upload is completed.
      elif status == _Status.UPLOADED:
        pass  # TODO(itspeter): Move the file into recycle bin.
      elif status == _Status.RACING:
        pass  # The file is uploading.
      else:
        logging.error('Unexpected status in FetchSourceThread: %d.', status)

      # Download the file based on the flag.
      if start_download:
        logging.info(
            'Start fetching %r with resume flag [%s].', source_rel_path, resume)
        source.FetchFile(source_rel_path, local_full_path, resume=resume)


def _UploadTargetThread(target, file_pool):
  """Traverse over the file_pool and find stuff to upload."""
  while True:  # Run forever.
    time.sleep(LOOP_DELAY)
    # Scanning the file_pool
    for current_dir, _, filenames in os.walk(file_pool):
      if os.path.basename(current_dir) == UPLOADER_METADATA_DIRECTORY:
        logging.debug(
            'Metadata directory %r found, skipped for uploading.', current_dir)
        continue
      for filename in filenames:
        if filename == UPLOADER_LOCK_FILE:
          continue  # Skip the lock file.

        start_upload = False
        resume = False
        local_full_path = os.path.join(current_dir, filename)
        local_rel_path = os.path.relpath(local_full_path, file_pool)

        status = _DetermineMetadataStatus(file_pool, local_rel_path)
        if status == _Status.UNKNOWN:
          pass  # Do nothing because FetchSource thread should fix it.
        elif status == _Status.DOWNLOADING:
          pass  # Action only when download is completed.
        elif status == _Status.UPLOADING:
          # Action when upload is not completed yet.
          start_upload = True
          resume = True
        elif status == _Status.UPLOADED_GREATER_THAN_EXPECTED:
          # Upload will start over from beginning.
          start_upload = True
          resume = False
        elif status == _Status.UPLOADED:
          pass  # FetchSource threading should take care of recycling.
        elif status == _Status.RACING:
          pass  # The file is downloading.
        else:
          logging.error('Unexpected status in UploadTargetThread: %d.', status)

        # Upload the file based on the flag.
        if start_upload:
          # TODO(itspeter):
          #   We should determine if a resume is feasible based on the
          #   checksum on remote side. Should add so after checksum is
          #   implemented.
          logging.info(
              'Start uploading %r with resume flag [%s].',
              local_full_path, resume)
          target.UploadFile(local_full_path, local_rel_path, resume=resume)


def main(argv):
  top_parser = argparse.ArgumentParser(description='Uploader')
  sub_parsers = top_parser.add_subparsers(
      dest='sub_command', help='available sub-actions')

  parser_start = sub_parsers.add_parser('start', help='start the uploader')
  parser_status = sub_parsers.add_parser(   # pylint: disable=W0612
      'status', help='Show all the activities')
  parser_clean = sub_parsers.add_parser(  # pylint: disable=W0612
      'clean', help='Clear completed history')
  # TODO(itspeter):
  #  Add arguments for status and clean which are running without
  #  an YAML configuration file.

  parser_start.add_argument(
      'yaml_config', action='store', type=IsValidYAMLFile,
      help='start uploader with the YAML configuration file')
  args = top_parser.parse_args(argv)

  # Check fields.
  if args.sub_command == 'start':
    _Uploader(args.yaml_config)
  elif args.sub_command == 'status':
    # TODO(itspeter): Implement the logic as design in docs.
    pass
  elif args.sub_command == 'clean':
    # TODO(itspeter): Implement the logic as design in docs.
    pass


if __name__ == '__main__':
  # TODO(itspeter): Consider expose the logging level as an argument.
  logging.basicConfig(
      format=('[%(levelname)s] %(filename)s:'
              '%(lineno)d %(asctime)s %(message)s'),
      level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
  main(sys.argv[1:])
