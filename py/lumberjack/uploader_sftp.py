#!/usr/bin/python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import getpass
import logging
import os
import paramiko
import pprint
import stat
import yaml

import uploader

from common import (GetMetadataPath, GetOrCreateMetadata,
                    RegenerateUploaderMetadataFile,
                    TimeString, UPLOADER_METADATA_DIRECTORY)
from uploader_exception import UploaderConnectionError, UploaderFieldError

BLOCK_SIZE = 32768  # 2^15, take paramiko's source as reference.


class FetchSource(object):
  __implements__ = (uploader.FetchSourceInterface, )  # For pylint

  host = None
  port = None
  username = None
  private_key = None
  archive_path = None

  _sftp = None  # SFTP channel
  _last_dirs = None  # Last time we list the archive_path
  _last_recursively_walk = None

  def _LoadPrivateKey(self, path_to_private_key):
    """Loads the private key.

    Prompts user to enter passphrase if necessary.

    Args:
      path_to_private_key: path to the private key.

    Raises:
      UploaderFieldError if key doesn't exist.
      UploaderFieldError if passphrase is invalid.
    """
    if not os.path.isfile(path_to_private_key):
      raise UploaderFieldError(
          'Private key %r doesn\'t exist or not having enough permission'
          'to load.' % path_to_private_key)

    try:
      self.private_key = paramiko.RSAKey.from_private_key_file(
          path_to_private_key)
    except paramiko.ssh_exception.PasswordRequiredException:
      logging.info('Private key %r needs password', path_to_private_key)
      password = getpass.getpass(
          'Please enter the passphrase for private key %r:\n' %
          path_to_private_key)
      # Try again with the passphrase
      try:
        self.private_key = paramiko.RSAKey.from_private_key_file(
            path_to_private_key, password=password)
      except paramiko.ssh_exception.SSHException:
        error_msg = ('Private key %r is invalid on passphase or format' %
                     path_to_private_key)
        logging.error(error_msg)
        raise UploaderFieldError(error_msg)
    logging.info('Private key %r loaded', path_to_private_key)

  def _CreateSFTP(self):
    try:
      logging.info('Trying to build SFTP channel with %s:%s',
                   self.host, self.port)
      t = paramiko.Transport((self.host, self.port))
      t.connect(username=self.username, pkey=self.private_key)
      self._sftp = paramiko.SFTPClient.from_transport(t)
      self._sftp.chdir('.')
      return True
    except Exception as e:
      logging.debug('Failed to create SFTP channel. Reasons:\n%r\n', e)
      return False

  def _Connect(self, retries=3):
    """Tries to connect to source.

    Raises:
      UploaderConnectionError if all retries failed.
    """
    def _ConnectWithRetries(retries):
      while retries > 0:
        if self._CreateSFTP():
          break
        retries -= 1
      if retries == 0:
        raise UploaderConnectionError(
            'Cannot create SFTP channel with %s:%s' % (self.host, self.port))

    if self._sftp: # Verify if the sftp session is still valid.
      try:
        self._sftp.chdir('.')
      except:  # pylint: disable=W0702
        logging.info('SFTP session no longer valid, reconnect.')
        _ConnectWithRetries(retries)
    else:
      logging.info('Try to establish SFTP session the first time')
      _ConnectWithRetries(retries)

  def LoadConfiguration(self, config):
    # Check if the private key exist.
    self._LoadPrivateKey(config['private_key'])
    # Parsing the config
    self.host = config['host']
    self.port = config['port']
    self.username = config['username']
    # Try to connect and check the existence of archive_path
    self.archive_path = config['archive_path']
    self._Connect()

    try:
      self._last_dirs = self._sftp.listdir(self.archive_path)
    except IOError:
      error_msg = 'Source directory %r doesn\'t exist' % self.archive_path
      raise UploaderFieldError(error_msg)

    logging.info('Configuration loaded. Found %d entries under %r.',
        len(self._last_dirs), self.archive_path)

  def _ListDirRecursively(self, dir_path, files):
    """Appends files recursively under dir_path into files.

    The appended tuple will be in the form:
      A list containing tuples of (absolute path, file size,
      last modification timestamp - mtime)
    """
    self._Connect()
    filenames = self._sftp.listdir(dir_path)
    dirs = []
    for filename in filenames:
      full_path = os.path.join(dir_path, filename)
      sftp_attr = self._sftp.lstat(full_path)
      if stat.S_ISDIR(sftp_attr.st_mode):
        dirs.append(full_path)
      else:
        files.append((full_path, sftp_attr.st_size, sftp_attr.st_mtime))
    # Recursively on the dirs
    for dir_full_path in dirs:
      self._ListDirRecursively(dir_full_path, files)

  def ListFiles(self, file_pool=None):
    files = []
    self._ListDirRecursively(self.archive_path, files)
    self._last_recursively_walk = files
    logging.debug("Getting full list of files from source:\n%s\n",
                  pprint.pformat(files))
    if file_pool:
      for full_path, file_size, mtime in files:
        source_rel_path = os.path.relpath(full_path, self.archive_path)
        metadata_path = GetMetadataPath(
          os.path.join(file_pool, source_rel_path),
          UPLOADER_METADATA_DIRECTORY)
        metadata = GetOrCreateMetadata(
            metadata_path, RegenerateUploaderMetadataFile)
        file_metadata = metadata.setdefault('file', {})
        file_metadata.update({'name': source_rel_path,
                              'size': file_size,
                              'last_modified': TimeString(mtime)})
        with open(metadata_path, 'w') as metadata_fd:
          metadata_fd.write(yaml.dump(metadata, default_flow_style=False))

    return copy.copy(files)

  def FetchFile(self, source_path, target_path,
                metadata_path=None, resume=True):
    def _UpdateDownloadMetadata():
      metadata = GetOrCreateMetadata(
          metadata_path, RegenerateUploaderMetadataFile)
      download_metadata = metadata.setdefault('download', {})
      download_metadata.update({'protocol': 'SFTP',
                                'host': self.host,
                                'port': self.port,
                                'path': source_path,
                                'downloaded_bytes': local_size,
                                'percentage': local_size / float(remote_size)})
      with open(metadata_path, 'w') as metadata_fd:
        metadata_fd.write(yaml.dump(metadata, default_flow_style=False))

    if metadata_path is None:
      metadata_path = GetMetadataPath(
          target_path, UPLOADER_METADATA_DIRECTORY)

    self._Connect()
    remote_size = self._sftp.stat(source_path).st_size
    local_size = (os.path.getsize(target_path) if
                  os.path.isfile(target_path) else 0)

    if remote_size < local_size and resume:
      logging.error('Size on source %r = %15d\nSize on local %r = %15d\n'
                    'Not able to resume, will override it.',
                    source_path, remote_size, target_path, local_size)
      local_size = 0
      resume = False

    file_flag = 'ab' if resume else 'wb'
    # Open a file on the remote.
    with self._sftp.open(source_path, 'rb') as remote_fd:
      if resume:  # Seek depends on resume flag
        remote_fd.seek(local_size)
        logging.info('Resume fetching %r on source at %15dn',
                     source_path, local_size)
      remote_fd.prefetch()
      with open(target_path, file_flag) as local_fd:
        while True:
          buf = remote_fd.read(BLOCK_SIZE)
          local_fd.write(buf)
          local_fd.flush()
          os.fsync(local_fd.fileno())
          local_size += len(buf)
          # Update metadta_path
          _UpdateDownloadMetadata()
          if len(buf) == 0:
            break
    return True

  def CalculateDigest(self, source_path):
    raise NotImplementedError()

  def MoveFile(self, from_path, to_path):
    raise NotImplementedError()

  def CheckDirectory(self, dir_path):
    raise NotImplementedError()

  def CreateDirectory(self, dir_path):
    raise NotImplementedError()
