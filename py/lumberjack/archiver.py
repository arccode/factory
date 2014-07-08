#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Main logics for archiving raw logs into unified archives."""

import hashlib
import logging
import os
import pprint
import re
import shutil
import tempfile
import time
import uuid
import yaml

from archiver_exception import ArchiverFieldError
from subprocess import PIPE, Popen
from twisted.internet import reactor

import common
from common import EncryptFile, GetMetadataPath, ARCHIVER_METADATA_DIRECTORY

SNAPSHOT = '.snapshot'
# These suffix indicate another process is using.
SKIP_SUFFIX = ['.part', '.inprogress', '.lock', '.swp']
ARCHIVER_SOURCE_FILES = ['archiver.py', 'archiver_exception.py',
                         'archiver_cli.py', 'archiver_config.py']
# Global variable to postpone the time (i.e. give few more archiving cycle
# a chance to recover automatically) of raising exception
archive_failures = []
MAX_ALOOWED_FAILURES = 5


def _ListEligibleFiles(dir_path):
  """Returns a list of files consider to be archived.

  Corrupted or missing metadata will be fixed during the travesal process.

  Args:
    dir_path: direcotry path wehre to search eligible files.

  Returns:
    A list contains tuples for eligible files, having appended bytes since
    last archiving cycle. The tuple consist of three fields, namely
    (last_completed_bytes, current_size, full path of the file).
  """
  ret = []
  for current_dir, _, filenames in os.walk(dir_path):
    # The second arguments is sub-directories that we don't care because
    # we focus on files and os.walk will traverse all of them eventually.
    if os.path.basename(current_dir) == ARCHIVER_METADATA_DIRECTORY:
      logging.debug('Metadata directory %r found, skipped.', current_dir)
      continue
    logging.debug('Scanning directory %r...', current_dir)
    for filename in filenames:
      # Check its suffix.
      if any(filename.endswith(x) for x in SKIP_SUFFIX):
        logging.debug(
            'File %r is possibily been used by other process, skipped.',
            filename)
        continue
      # Get the bytes information
      full_path = os.path.join(current_dir, filename)
      appended_range = _GetRangeOfAppendedBytes(full_path, current_dir)
      if (appended_range[1] - appended_range[0]) <= 0:
        logging.debug(
            'No bytes appended to file %r since last archiving. Skipped.',
            full_path)
      else:
        ret.append((appended_range[0], appended_range[1], full_path))
  return ret


def _GetRangeOfAppendedBytes(file_path, dir_path=None):
  """Returns a tuple indicating range of appended bytes.

  Regenerate metadata if
    1) completed_bytes field is unreasonable (completed_bytes > filesize).
    2) completed_bytes field is missing.

  Args:
    file_path: The path to the file of interested.
    dir_path:
      The directory path of the file_path. If the caller has the infomation
      of its directory name in place, we can save a call of calling
      os.path.dirname() by assigning this.

  Returns:
    A tuple indicates the appended range [start_pos, end_pos).
    The start_pos is included but not the end_pos. It doesn't garantee to be
    reasonable (i.e. end_pos > start_pos). It levaes to caller to decide
    how to cope with these tuple.
  """
  metadata_path = GetMetadataPath(
      file_path, ARCHIVER_METADATA_DIRECTORY, dir_path)
  metadata = common.GetOrCreateMetadata(
      metadata_path, common.RegenerateArchiverMetadataFile)

  current_size = os.path.getsize(file_path)
  # current_size+1 to trigger if completed_bytes is not in the dictionary.
  completed_bytes = metadata.get('completed_bytes', current_size + 1)
  if completed_bytes > current_size:
    logging.info(
        'Metadata %r seems corrupted. Either completed_bytes cannot '
        'be found or is larger than current file size. Reconstruct it.',
        metadata_path)
    common.RegenerateArchiverMetadataFile(metadata_path)
    completed_bytes = 0
  return (completed_bytes, current_size)


def _UpdateArchiverMetadata(new_metadatas, config):
  """Updates the metadata of files.

  Args:
    new_metadatas:
      A dictionary from the archive's metadata under key 'files', which
      indicated the successful archvied files. The value of 'files' is in
      format like below:
      {
        'filename1: {'start': start position, 'end': end position},
        'filename2: {'start': start position, 'end': end position},
      }
      filename is the relative path from config.source_dir or
      dirname(config.source_file). End and start position are archived range
      of filename.
  """
  root_dir = (os.path.dirname(config.source_file) if
      config.source_file else config.source_dir)

  for filename, archived_range in new_metadatas.iteritems():
    full_path = os.path.join(root_dir, filename)
    metadata_path = GetMetadataPath(full_path, ARCHIVER_METADATA_DIRECTORY)
    logging.info('Updating %s', metadata_path)
    with open(metadata_path, 'w') as fd:
      fd.write(common.GenerateArchiverMetadata(
          completed_bytes=archived_range['end']))

def _IdentifyContentForArchiving(files, tmp_dir, config):
  """Identifies chunks and prepare them into tmp_dir if necessary.

  For in-place compression (config.compress_in_place is True), this will
  generates the proper metdata for zip compression.

  While config.compress_in_place is False, it will prepare content into
  tmp_dir, copying the non archived, completed chunks into temporary
  directory for later processing. If no delimiter assigned in config, all
  non archived bytes will be treated as a complete chunk.

  The structure of the files will be preserved. For example
    abcd/foo.txt -> /tmp_dir/abcd/foo.txt

  Args:
    files:
      A list of tuple about non archived bytes in the form (start position,
      end position, full path of the file).
    tmp_dir:
      Path to the temporary directory where new files are created. Will be
      ignored if config.compress_in_place is True.
    config:
      An ArchiverConfig to indicate delimiter and compress_in_place
      information.

  Returns:
    The metadata contains the copied bytes. In the form of a dictionary
    {'files':
       'filename1: {'start': start position, 'end': end position},
       'filename2: {'start': start position, 'end': end position},
       ....
     'archiver': dictionary form of ArchiverConfig
     'umpire': {}
    }
  """
  archive_metadata = {'files': {},
                      'archiver': config.ToDictionary(),
                      'umpire': {}}
  source_dir = (
      os.path.dirname(config.source_file) if config.source_file else
      config.source_dir)

  if config.compress_in_place:
    logging.debug('Start propagate the list for compressing')
    for start, end, filename in files:
      # Every range for compress_in_place should be a complete file.
      if start != 0 or end != os.path.getsize(filename):
        error_msg = ('File %r got appended bytes detected as start:%d, '
                     'end:%d. We expect start:0 end:%d as a completed file' %
                     (filename, start, end, os.path.getsize(filename)))
        logging.error(error_msg)
        archive_failures.append(error_msg)
        raise ArchiverFieldError(error_msg)

      relative_path = os.path.relpath(filename, source_dir)
      # Add to the metadata
      archive_metadata['files'][relative_path] = {'start': start, 'end': end}
      logging.debug('%r for archiving prepared.', filename)

  else:  # Data for compression need to prepare into temporary directory
    for start, end, filename in files:
      logging.debug(
          'Identifying appended bytes of %r into temporary directory %r',
          filename, tmp_dir)
      last_complete_chunk_pos = appended_length = end - start
      with open(filename, 'r') as fd:
        fd.seek(start)
        appended = fd.read(appended_length)
        # Search for the complete chunk
        if config.delimiter:
          matches = list(config.delimiter.finditer(appended, re.MULTILINE))
          if not len(matches):
            logging.debug(
                'No complete chunk in appended bytes for %r', filename)
            continue
          last_complete_chunk_pos = matches[-1].end()
          if (start + last_complete_chunk_pos) < end:
            logging.debug('One incomplete chunk will be skipped: %r',
                          appended[last_complete_chunk_pos:])
          end = start + last_complete_chunk_pos

      relative_path = os.path.relpath(filename, source_dir)

      # Create related sub-directories
      tmp_full_path = os.path.join(tmp_dir, relative_path)
      try:
        common.TryMakeDirs(os.path.dirname(tmp_full_path),
                           raise_exception=True)
      except Exception:
        error_msg = ('Failed to create sub-directory for %r in temporary'
                     'folder %r' % (tmp_full_path, tmp_dir))
        logging.error(error_msg)
        archive_failures.append(error_msg)
        raise ArchiverFieldError(error_msg)

      with open(tmp_full_path, 'w') as output_fd:
        output_fd.write(appended[:last_complete_chunk_pos])
      # Add to the metadata
      archive_metadata['files'][relative_path] = {'start': start, 'end': end}
      logging.debug('%r for archiving prepared.', filename)
  return archive_metadata

def _GenerateArchiveName(config):
  """Returns an archive name based on the ArchiverConfig.

  The name follows the format:
    <project>,<data_types>,<formatted_time>,<hash>.<compress_format>

  For example:
    spring,report,20130205T1415Z,c7c62ea462.zip
    spring,eventlog,20130307T1945Z,c7a462c5a4.tar.xz

  The hash has 10 hex digits. The 10 digits will separate into two parts,
  first 2 digits for identifying host (Umpire) and following 8 digits are
  generated randomly.
  """
  # For hashlib, pylint: disable=E1101
  prefix = '~'.join(
      [config.project, config.data_type,
       time.strftime('%Y%m%dT%H%MZ', time.gmtime(time.time())),
       (hashlib.sha256(str(uuid.getnode())).hexdigest()[:2] +
        str(uuid.uuid4())[:8])])
  suffix = config.compress_format
  return prefix + suffix

def _Recycle(config):
  """Recycles directory from raw source if possible.

  A directory under config.source_dir will be identified as recyclable if
  time criteria and snapshot criteria are both met.

  config.source_file will not be recycled because of potential racing writing.

  1) Time criteria:
    The directory name can be recognized by _ConvertToTimestamp() and the
    time difference between current time are larger than
    config.save_to_recycle_duration.
  2) Snapshop criteria:
    The .archiver/.snapshot has identical content as the one we are going to
    create.

  Although it shouldn't happen logically (unless the system time is drifted
  a lot), we still have a rule to deal with recycle failure. When recycle
  failed (i.e. a directory with same name exists), a 4 digits random hash
  will be added as a suffix with one retry.

  Returns:
    True if recycle run until the end, False if terminate prematurely.
  """
  def _ConvertToTimestamp(dir_name):
    """Converts to time in seconds since the epoch.

    The following format are supported:
      Format                 Example
      YYYYMMDD/              20130929/
      logs.YYYYMMDD/         logs.20140220/
      logs.YYYYMMDD-hh/      logs.20140220-14/

    Returns:
      If dir_name can be converted, a time in seconds as a floating point will
      be returned. Otherwise, return None.
    """
    ret = None
    support_formats = ['logs.%Y%m%d-%H', 'logs.%Y%m%d', '%Y%m%d']
    for format_str in support_formats:
      try:
        ret = time.strptime(dir_name, format_str)
        break
      except ValueError:
        pass  # Not able to parse the string
    if ret is not None:
      ret = time.mktime(ret)
    return ret

  def _WriteSnapshot(file_path, snapshot_to_write):
    with open(file_path, 'w') as fd:
      fd.write(yaml.dump(snapshot_to_write, default_flow_style=False))
    logging.debug('Snapshot %r created.', file_path)

  if not config.recycle_dir:
    logging.debug('No recycle_dir assigned, skipped.')
    return False

  if config.source_file:
    logging.debug('config.source_file %r will not be recycled because of'
                  'potential racing writing, skipped', config.source_file)
    return False

  for current_dir, sub_dirs, filenames in os.walk(config.source_dir):
    if os.path.basename(current_dir) == ARCHIVER_METADATA_DIRECTORY:
      logging.debug('Metadata directory %r found, skipped.', current_dir)
      continue
    # Check if the directory format are recognizable.
    dir_time_in_secs = _ConvertToTimestamp(os.path.basename(current_dir))
    if dir_time_in_secs is None:
      logging.debug('Cannot recognized the timestamp of %r. Will be skipped.',
                    dir_time_in_secs)
      continue
    # Make sure the directory is the deepest (i.e. not more sub_dirs)
    if not (len(sub_dirs) == 1 and sub_dirs[0] == ARCHIVER_METADATA_DIRECTORY):
      logging.debug('Directory %r still have sub-directories %r, not suitable'
                    ' for screenshot creating. Will be skipped.',
                    current_dir, sub_dirs)
      continue

    # Establish new snpahost.
    new_snapshot = []
    for filename in filenames:
      full_path = os.path.join(current_dir, filename)
      mtime = os.path.getmtime(full_path)
      size = os.path.getsize(full_path)
      new_snapshot.append({'path': filename, 'mtime': mtime, 'size': size})
    # Sort the new_snapshot by filename
    new_snapshot.sort(key=lambda _dict: _dict['path'])
    snapshot_path = os.path.join(
        current_dir, ARCHIVER_METADATA_DIRECTORY, SNAPSHOT)
    # Check if the time criteria is already matched.
    if time.time() - dir_time_in_secs < config.save_to_recycle_duration:
      logging.debug(
          'Directory %r still immature for recycling. %.2f secs left.',
          current_dir,
          config.save_to_recycle_duration - (time.time() - dir_time_in_secs))
      # Update snapshot
      _WriteSnapshot(snapshot_path, new_snapshot)
      continue

    # Read the current snapshot to check if we meet snapshot criteria.
    current_snapshot = []
    if os.path.isfile(snapshot_path):
      with open(snapshot_path) as fd:
        current_snapshot = yaml.load(fd.read())
    _WriteSnapshot(snapshot_path, new_snapshot)  # Override the current.

    # Compare the snapshot.
    if current_snapshot != new_snapshot:
      continue

    # Move to recycle_dir. Example of the moving path:
    # raw-logs/eventlog/20130307/* -> recycle/raw-logs/eventlog/20130307/*
    target_dir = os.path.join(config.recycle_dir,
                              os.path.relpath(current_dir, config.source_dir))
    logging.info('Both time and snapshot criteria meet, moving %r '
                 'to %r', current_dir, target_dir)
    try:
      os.rename(current_dir, target_dir)
    except OSError:  # Might already have a directory with same name
      target_dir = target_dir.rstrip('/') + '_' + str(uuid.uuid4())[-4:]
      logging.info('A directory with same name might already existed. Retry'
                   'to move %r to %r instead.', current_dir, target_dir)
      try:
        os.rename(current_dir, target_dir)
      except OSError:  # Fail again.
        logging.error('Fail to recycle directory %r, will try again in next '
                      'archiving cycle.', current_dir)
        continue
    logging.info('Successfully recycled %r to %r', current_dir, target_dir)
  return True


def Archive(config, next_cycle=True):
  """Archives the files based on the ArchiverConfig.

  This is the main logic of the archiver. Each config will call this function
  to set up its archiving cycle running long-lived.

  Args:
    config: An ArchiverConfig instructs how to do the archiving.
    next_cycle:
      True to follow the config.duration and False to make this a one-time
      execution, usually used in run-once mode or unittest.

  Returns:
    Full path of generated archive.
  """
  # TODO(itspeter): Special treat for zip (prepare file list instead of chunks)
  started_time = common.TimeString()
  generated_archive = None

  def _UpdateMetadataInArchive(archive_metadata, started_time):
    """Writes other information about current archiver and its enviornment."""
    archive_metadata['archiver']['started'] = started_time
    archive_metadata['archiver']['version_md5'] = (
        common.GetMD5ForFiles(ARCHIVER_SOURCE_FILES, os.path.dirname(__file__)))
    archive_metadata['archiver']['host'] = hex(uuid.getnode())
    # TODO(itspeter): Write Umpire related information if available

  def _CompressIntoTarXz(tmp_dir, archive_metadata, config):
    """Writes metadata into tmp_dir and compresses it into archived_dir."""
    with open(os.path.join(tmp_dir, 'archive.metadata'), 'w') as fd:
      fd.write(yaml.dump(archive_metadata, default_flow_style=False))

    # Compress it.
    generated_archive = os.path.join(
        config.archived_dir, _GenerateArchiveName(config))
    tmp_archive = generated_archive + '.part'
    logging.info('Compressing %r into %r', tmp_dir, tmp_archive)
    cmd_line = ['tar', '-cvJf', tmp_archive, '-C', tmp_dir, '.']
    p = Popen(cmd_line, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
      error_msg = ('Command %r failed. retcode[%r]\nstdout:\n%s\n\n'
                   'stderr:\n%s\n' % (cmd_line, p.returncode, stdout, stderr))
      logging.error(error_msg)
      archive_failures.append(error_msg)
      raise ArchiverFieldError(error_msg)

    # Remove .part suffix.
    os.rename(tmp_archive, generated_archive)
    return generated_archive

  def _CompressIntoZip(tmp_dir, archive_metadata, config):
    """Writes metadata into tmp_dir and generates the zip archive."""
    root_dir = (os.path.dirname(config.source_file) if
        config.source_file else config.source_dir)
    with open(os.path.join(tmp_dir, 'archive.metadata'), 'w') as fd:
      fd.write(yaml.dump(archive_metadata, default_flow_style=False))
    # Compress it.
    generated_archive = os.path.join(
        config.archived_dir, _GenerateArchiveName(config))
    tmp_archive = generated_archive + '.part'
    logging.info('Compressing %r into %r', tmp_dir, tmp_archive)
    # Prepare the compress list
    with open(os.path.join(tmp_dir, 'zip_list'), 'w') as fd:
      fd.write('\n'.join(archive_metadata['files']))
    cmd_line = ['zip', tmp_archive, '-@']
    with open(os.path.join(tmp_dir, 'zip_list'), 'r') as fd:
      # In order to keep correct relative path, we need to specify the cwd.
      p = Popen(cmd_line, cwd=root_dir, stdin=fd, stdout=PIPE, stderr=PIPE)
      stdout, stderr = p.communicate()
    if p.returncode != 0:
      error_msg = ('Command %r failed. retcode[%r]\nstdout:\n%s\n\n'
                   'stderr:\n%s\n' % (cmd_line, p.returncode, stdout, stderr))
      logging.error(error_msg)
      archive_failures.append(error_msg)
      raise ArchiverFieldError(error_msg)
    # Append metadata into archive
    cmd_line = ['zip', tmp_archive, 'archive.metadata']
    p = Popen(cmd_line, cwd=tmp_dir, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
      error_msg = ('Command %r failed. retcode[%r]\nstdout:\n%s\n\n'
                   'stderr:\n%s\n' % (cmd_line, p.returncode, stdout, stderr))
      logging.error(error_msg)
      archive_failures.append(error_msg)
      raise ArchiverFieldError(error_msg)

    # Remove .part suffix.
    os.rename(tmp_archive, generated_archive)
    return generated_archive


  try:
    tmp_dir = tempfile.mkdtemp(prefix='FactoryArchiver_',
                               suffix='_' + config.data_type)
    logging.info('%r created for archiving data_type[%s]',
                 tmp_dir, config.data_type)
    if config.source_dir:
      eligible_files = _ListEligibleFiles(config.source_dir)
    else:  # Single file archiving.
      appended_range = _GetRangeOfAppendedBytes(config.source_file)
      if (appended_range[1] - appended_range[0]) <= 0:
        logging.debug(
            'No bytes appended to file %r since last archiving. Skipped.',
            config.source_file)
        eligible_files = []
      else:
        eligible_files = [
            (appended_range[0], appended_range[1], config.source_file)]

    try:  # If any of the steps fail, we don't want to proceed further.
      archive_metadata = _IdentifyContentForArchiving(
          eligible_files, tmp_dir, config)
      if len(archive_metadata['files']) > 0:
        _UpdateMetadataInArchive(archive_metadata, started_time)
        # Generate the archive
        if config.compress_format == '.tar.xz':
          generated_archive = _CompressIntoTarXz(
              tmp_dir, archive_metadata, config)
        else:  #  .zip format.
          generated_archive = _CompressIntoZip(
              tmp_dir, archive_metadata, config)
        if config.encrypt_key_pair:
          EncryptFile(generated_archive, config.encrypt_key_pair, delete=True)

        # Update metadata data for archived files only when compression
        # succeed.
        _UpdateArchiverMetadata(archive_metadata['files'], config)
      else:
        logging.info('No data available for archiving for %r', config.data_type)
    except ArchiverFieldError:
      # Do not raise error since it will stop the archiver. We would like to
      # give few more retires in coming cycle.
      if len(archive_failures) > MAX_ALOOWED_FAILURES:
        raise ArchiverFieldError(
            'Archiver failed %d times. The error messages are\n%s\n' %
            pprint.pformat(archive_failures))
  finally:
    shutil.rmtree(tmp_dir)
    logging.info('%r deleted', tmp_dir)

  # Create snapshot and recycle direcotry in source_dir
  _Recycle(config)

  if next_cycle:
    reactor.callLater(config.duration, Archive, config)  # pylint: disable=E1101

  logging.info('%r created for archiving data_type[%s]',
               generated_archive, config.data_type)
  return generated_archive
