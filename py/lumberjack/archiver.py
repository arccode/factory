#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Main logics for archiving raw logs into unified archives."""

import logging
import os
import re
import tempfile
import yaml

from archiver_exception import ArchiverFieldError
from twisted.internet import reactor


METADATA_DIRECTORY = '.archiver'  # For storing metadata.
# These suffix indicate another process is using.
SKIP_SUFFIX = ['.part', '.inprogress', '.lock', '.swp']

# Global variable to keep locked file open during process life-cycle
locks = []


def ListEligibleFiles(dir_path):
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
    if os.path.basename(current_dir) == METADATA_DIRECTORY:
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


def GetMetadataPath(file_path, dir_path=None):
  """Returns the metadata path of file_path.

  Args:
    file_path: The path to the file that we want its metadata's path.
    dir_path:
      The directory path of the file_path. If the caller has the infomation
      of its directory name in place, we can save a call of calling
      os.path.dirname() by assigning this.

  Returns:
    The path to the metadata.
  """
  if not dir_path:
    dir_path = os.path.dirname(file_path)

  return os.path.join(
      dir_path, METADATA_DIRECTORY,
      os.path.basename(file_path) + '.metadata')


def GenerateArchiverMetadata(completed_bytes=0):
  """Returns a string that can be written directly into the metadata file."""
  return yaml.dump({'completed_bytes': completed_bytes})


def _RegenerateArchiverMetadataFile(metadata_path):
  """Regenerates the metadata file such completed_bytes is 0.

  Args:
    metadata_path: The path to the metadata.

  Returns:
    Retrns the string it writes into the metadata_path
  """
  logging.info("Re-generate metadata at %r", metadata_path)
  ret_str = GenerateArchiverMetadata()
  with open(metadata_path, 'w') as fd:
    fd.write(ret_str)
  return ret_str


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
  metadata_path = GetMetadataPath(file_path, dir_path)
  metadata = _GetOrCreateArchiverMetadata(metadata_path)

  current_size = os.path.getsize(file_path)
  # current_size+1 to trigger if completed_bytes is not in the dictionary.
  completed_bytes = metadata.get('completed_bytes', current_size + 1)
  if completed_bytes > current_size:
    logging.info(
        'Metadata %r seems corrupted. Either completed_bytes cannot '
        'be found or is larger than current file size. Reconstruct it.',
        metadata_path)
    _RegenerateArchiverMetadataFile(metadata_path)
    completed_bytes = 0
  return (completed_bytes, current_size)


def _TryMakeDirs(path, raise_exception=False):
  """Tries to create a directory and its parents."""
  # TODO(itspeter):
  #   switch to cros.factory.test.utils.TryMakeDirs once migration to
  #   Umpire is fully rolled-out.
  try:
    if not os.path.exists(path):
      os.makedirs(path)
  except Exception:
    if raise_exception:
      raise


def _GetOrCreateArchiverMetadata(metadata_path):
  """Returns a dictionary based on the metadata of file.

  Regenerate metadata if it is not a valid YAML format
  (syntax error or non-dictionary).

  Args:
    metadata_path: The path to the metadata.

  Returns:
    A dictionary of the parsed YAML from metadata file.
  """
  # Check if metadata directory is created.
  metadata_dir = os.path.dirname(metadata_path)
  try:
    _TryMakeDirs(metadata_dir, raise_exception=True)
  except Exception:
    logging.error('Failed to create metadata directory %r for archiver',
                  metadata_dir)

  fd = os.fdopen(os.open(metadata_path, os.O_RDWR | os.O_CREAT), 'r+')
  content = fd.read()
  fd.close()
  if content:
    try:
      metadata = yaml.load(content)
      # Check if it is a dictionary
      if not isinstance(metadata, dict):
        raise ArchiverFieldError(
            'Unexpected metadata format, should be a dictionary')
      return metadata
    except (yaml.YAMLError, ArchiverFieldError):
      logging.info(
          'Metadata %r seems corrupted. YAML syntax error or not a '
          'dictionary. Reconstruct it.', metadata_path)
  return yaml.load(_RegenerateArchiverMetadataFile(metadata_path))


def CopyCompleteChunks(files, tmp_dir, config):
  """Identifies chunks and copies them into tmp_dir.

  This function will copy the non archived, completed chunks into temporary
  directory for later processing. If no delimiter assigned in config, all
  non archived bytes will be treated as a complete chunk.

  The structure of the files will be preserved. For example
    abcd/foo.txt -> /tmp_dir/abcd/foo.txt

  Args:
    files:
      A list of tuple about non archived bytes in the form (start position,
      end position, full path of the file).
    tmp_dir: Path to the temporary directory where new files are created.
    config: An ArchiverConfig to indicate delimiter information.

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
          logging.debug('No complete chunk in appended bytes for %r', filename)
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
      _TryMakeDirs(os.path.dirname(tmp_full_path), raise_exception=True)
    except Exception:
      logging.error(
          'Failed to create sub-directory for %r in temporary folder %r',
          tmp_full_path, tmp_dir)

    with open(tmp_full_path, 'w') as output_fd:
      output_fd.write(appended[:last_complete_chunk_pos])
    # Add to the metadata
    archive_metadata['files'][relative_path] = {'start': start, 'end': end}
    logging.debug('%r for archiving prepared.', filename)
  return archive_metadata


def Archive(config, next_cycle=True):
  """Archives the files based on the ArchiverConfig.

  This is the main logic of the archiver. Each config will call this function
  to set up its archiving cycle running long-lived.

  Args:
    config: An ArchiverConfig instructs how to do the archiving.
    next_cycle:
      True to follow the config.duration and False to make this a one-time
      execution, usually used in run-once mode or unittest.
  """
  # TODO(itspeter): Special treat for zip (prepare file list instead of chunks)

  try:
    tmp_dir = tempfile.mkdtemp(prefix='FactoryArchiver',
                               suffix=config.data_type)
    logging.info('%r created for archiving data_type[%s]',
                 tmp_dir, config.data_type)
    if config.source_dir:
      eligible_files = ListEligibleFiles(config.source_dir)
      # pylint: disable=W0612
      archive_metadata = CopyCompleteChunks(eligible_files, tmp_dir, config)
      # TODO(itspeter): Complete the logic:
      #   Create metadata for the archive
      #   Compress it.
    else:  # Single file archiving.
      appended_range = _GetRangeOfAppendedBytes(config.source_file)
      if (appended_range[1] - appended_range[0]) <= 0:
        logging.debug(
            'No bytes appended to file %r since last archiving. Skipped.',
            config.source_file)
      else:
        # TODO(itspeter): complete the logic
        pass
  finally:
    # TODO(itspeter): enable after debugging completed.
    #shutil.rmtree(tmp_dir)
    #logging.info('%r deleted', tmp_dir)
    pass

  if next_cycle:
    reactor.callLater(config.duration, Archive, config)  # pylint: disable=E1101
