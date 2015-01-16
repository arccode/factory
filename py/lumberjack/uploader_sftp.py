#!/usr/bin/python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""SFTP implementation for FetchSource and UploadTarget."""

import getpass
import logging
import os
import paramiko
import stat
import yaml

from common import (ComputePercentage, GetMetadataPath, GetOrCreateMetadata,
                    LogListDifference, RegenerateUploaderMetadataFile,
                    UPLOADER_METADATA_DIRECTORY)
from uploader_exception import UploaderConnectionError, UploaderFieldError
from uploader_interface import FetchSourceInterface, UploadTargetInterface

BLOCK_SIZE = 32768  # 2^15, take paramiko's source as reference.
DISCONNECTED_RETRY = 3


def _MakeConnected(func):
  """Decorator to check and establish SFTP channel if necessary."""

  def _Wrapper(self, *args, **kwargs):
    self._Connect()  # pylint: disable=W0212
    return func(self, *args, **kwargs)  # pylint: disable=E1102
  return _Wrapper


class SFTPBase(object):
  """Common function shared across FetchSource and UploadTarget on SFTP.

  The SFTPBase class is inherited by FetchSource and UploadTarget, designed
  for SFTP protocol and key exchange authentication.

  Properties:
    host: the remote host name or IP address of the SFTP.
    port: the remote port of the SFTP. Default to port 22.
    username: the username to login the SFTP.
    private_key: the private key used to login.
    archive_path: the starting path of the SFTP. Most function takes path
        relative to archive_path as its arguments.
    config_name: name for a SFTP connection.
    _sftp: internal maintained variable, representing a channel of SFTP.
  """
  host = None
  port = 22
  username = None
  private_key = None

  archive_path = None
  config_name = None

  _sftp = None  # SFTP channel

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
    except Exception:
      logging.exception('Failed to create SFTP channel.')
      return False

  def _Connect(self, retries=DISCONNECTED_RETRY):
    """Tries to connect SFTP.

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

    if self._sftp:  # Verify if the sftp session is still valid.
      try:
        self._sftp.chdir('.')
      except:  # pylint: disable=W0702
        logging.info('SFTP session no longer valid, reconnect.')
        _ConnectWithRetries(retries)
    else:
      logging.info('Try to establish SFTP session the first time')
      _ConnectWithRetries(retries)

  @_MakeConnected
  def CheckDirectory(self, dir_path):
    try:
      self._sftp.chdir(dir_path)
    except IOError:
      return False
    return True

  @_MakeConnected
  def CalculateDigest(self, relative_path):
    # SFTP doesn't guarantee to support checksum by standard.
    raise NotImplementedError

  @_MakeConnected
  def MoveFile(self, from_path, to_path):
    # Construct the complete path.
    from_path = os.path.join(self.archive_path, from_path)
    to_path = os.path.join(self.archive_path, to_path)
    self._sftp.rename(from_path, to_path)
    logging.info('Moved %r -> %r', from_path, to_path)

  def CreateDirectory(self, dir_path):
    raise NotImplementedError


class FetchSource(SFTPBase):  # pylint: disable=W0223
  """A SFTP implementation of FetchSourceInterface."""
  __implements__ = (FetchSourceInterface, )  # For pylint

  _last_dirs = None  # Last time we list the archive_path
  _last_recursively_walk = []

  def LoadConfiguration(self, config, config_name=None):
    # Check if the private key exist.
    self._LoadPrivateKey(config['private_key'])
    # Parsing the config
    self.config_name = config_name
    self.host = config['host']
    self.port = config['port']
    self.username = config['username']
    # Try to connect and check the existence of archive_path
    self.archive_path = config['archive_path']
    self._Connect()

    if not self.CheckDirectory(self.archive_path):
      error_msg = 'Source directory %r doesn\'t exist' % self.archive_path
      raise UploaderFieldError(error_msg)

    logging.info('Source configuration %r loaded.', config_name)

  @_MakeConnected
  def _ListDirRecursively(self, dir_path, files):
    """Appends file infos under dir_path recursively.

    Args:
      dir_path: The directory to be list.
      files:
          a list that tuple is going to appened into. The appended tuple
          will be in the form (absolute path, file size, last modification
          timestamp - mtime)

    Returns:
      True if no errors happened during the process. False means only partial
      results are obtained during this call. This might happen in lots of
      scenario. For example: a file found during listdir, but then deleted so
      causing the lstat later raises an IOError exception. Caller should
      determine its reaction based on the return value.
    """
    ret_flag = True

    # High risk of raising exception, narrow down to get verbose information.
    try:
      filenames = self._sftp.listdir(dir_path)
    except Exception:
      logging.exception(
          'Exception raised while _ListDirRecursively is scanning %r',
          dir_path)
      return False

    dirs = []
    for filename in filenames:
      full_path = os.path.join(dir_path, filename)
      # High risk of raising exception, narrow down to get verbose information.
      try:
        sftp_attr = self._sftp.lstat(full_path)
      except Exception:
        logging.exception(
            'Exception raised while _ListDirRecursively lstat %r', full_path)
        ret_flag = False
        continue

      if stat.S_ISDIR(sftp_attr.st_mode):
        dirs.append(full_path)
      else:
        files.append((full_path, sftp_attr.st_size, sftp_attr.st_mtime))
    # Recursively on the dirs
    for dir_full_path in dirs:
      ret_flag = ret_flag and self._ListDirRecursively(dir_full_path, files)
    return ret_flag

  def ListFiles(self):
    files = []
    self._ListDirRecursively(self.archive_path, files)
    # Log the difference of discovered items
    LogListDifference(self._last_recursively_walk, files,
                      help_text='remote %r' % self.config_name)
    self._last_recursively_walk = files
    ret = []
    # Based on the interface. Change it to relative path.
    for full_path, file_size, mtime in files:
      source_rel_path = os.path.relpath(full_path, self.archive_path)
      ret.append((source_rel_path, file_size, mtime))

    return ret

  @_MakeConnected
  def FetchFile(self, source_path, target_path,
                metadata_path=None, resume=True):
    def _UpdateDownloadMetadata():
      logging.info(
          'Downloading...%9.5f%% of %10d bytes',
          ComputePercentage(local_size, remote_size), remote_size)
      metadata = GetOrCreateMetadata(
          metadata_path, RegenerateUploaderMetadataFile)
      download_metadata = metadata.setdefault('download', {})
      download_metadata.update(
          {'protocol': 'SFTP',
           'host': self.host,
           'port': self.port,
           'path': source_path,
           'downloaded_bytes': local_size,
           'percentage': ComputePercentage(local_size, remote_size)})
      with open(metadata_path, 'w') as metadata_fd:
        metadata_fd.write(yaml.dump(metadata, default_flow_style=False))

    if metadata_path is None:
      metadata_path = GetMetadataPath(
          target_path, UPLOADER_METADATA_DIRECTORY)

    # Convert source_path into full_path on the SFTP side.
    source_path = os.path.join(self.archive_path, source_path)

    try:
      remote_size = self._sftp.stat(source_path).st_size
    except IOError:
      logging.exception('No %r exists on remote', source_path)
      return False

    local_size = (os.path.getsize(target_path) if
                  os.path.isfile(target_path) else 0)

    if remote_size < local_size:
      logging.error(
          'Size on source %r = %10d\nSize on local %r = %10d. Abnormal.',
          source_path, remote_size, target_path, local_size)
      local_size = 0
      if resume:
        logging.error('Not able to resume, will override it.')
        resume = False

    file_flag = 'ab' if resume else 'wb'
    local_size = 0 if not resume else local_size
    # Open a file on the remote.
    with self._sftp.open(source_path, 'rb') as remote_fd:
      if resume:  # Seek depends on resume flag
        remote_fd.seek(local_size)
        logging.info('Resume fetching %r [size %10d] from remote at %10d.',
                     source_path, remote_size, local_size)
      else:
        logging.info('Fetching %r [size %10d] from remote.',
                     source_path, remote_size)

      remote_fd.prefetch()
      with open(target_path, file_flag) as local_fd:
        while True:
          _UpdateDownloadMetadata()  # Update metadata
          buf = remote_fd.read(BLOCK_SIZE)
          local_fd.write(buf)
          local_fd.flush()
          os.fsync(local_fd.fileno())
          local_size += len(buf)
          if len(buf) == 0 or local_size == remote_size:
            break

    # We move the last metadata update outside the main loop because putting
    # on the bottom of loop might causing false recognition by other threads
    # in uploader.
    _UpdateDownloadMetadata()  # Update metadata

    return True


class UploadTarget(SFTPBase):  # pylint: disable=W0223
  """A SFTP implementation of UploadTargetInterface."""
  __implements__ = (UploadTargetInterface, )  # For pylint

  def LoadConfiguration(self, config, config_name=None):
    # Check if the private key exist.
    self._LoadPrivateKey(config['private_key'])
    # Parsing the config
    self.config_name = config_name
    self.host = config['host']
    self.port = config['port']
    self.username = config['username']
    # Try to connect and check the existence of archive_path
    self.archive_path = config['archive_path']
    self._Connect()

    if not self.CheckDirectory(self.archive_path):
      error_msg = 'Source directory %r doesn\'t exist' % self.archive_path
      raise UploaderFieldError(error_msg)

    logging.info('Target configuration %r loaded.', config_name)

  @_MakeConnected
  def UploadFile(self, local_path, target_path,
                 metadata_path=None, resume=True):
    def _UpdateUploadMetadata():
      metadata = GetOrCreateMetadata(
          metadata_path, RegenerateUploaderMetadataFile)
      logging.info(
          'Uploading...%9.5f%% of %10d bytes',
          ComputePercentage(remote_size, local_size), local_size)
      upload_metadata = metadata.setdefault('upload', {})
      upload_metadata.update(
          {'protocol': 'SFTP',
           'host': self.host,
           'port': self.port,
           'path': target_path,
           'uploaded_bytes': remote_size,
           'percentage': ComputePercentage(remote_size, local_size)})
      with open(metadata_path, 'w') as metadata_fd:
        metadata_fd.write(yaml.dump(metadata, default_flow_style=False))

    # Check if file to upload exists.
    if not os.path.isfile(local_path):
      raise UploaderFieldError(
          '%r doesn\'t exist on local file system', local_path)

    if metadata_path is None:
      metadata_path = GetMetadataPath(
          local_path, UPLOADER_METADATA_DIRECTORY)

    # Convert target_path into full_path on the SFTP side.
    target_path = os.path.join(self.archive_path, target_path)

    try:
      remote_size = self._sftp.stat(target_path).st_size
    except IOError:
      logging.info(
          '%r doesn\'t exist on remote, no resuming will be conducted',
          target_path)
      remote_size = 0
      resume = False

    local_size = os.path.getsize(local_path)

    if remote_size > local_size:
      logging.error(
          'Size on remote %r = %10d\nSize on local %r = %10d. Abnormal.',
          target_path, remote_size, local_path, local_size)
      remote_size = 0
      if resume:
        resume = False
        logging.error('Not able to resume, will override it.')

    file_flag = 'ab' if resume else 'wb'
    remote_size = 0 if not resume else remote_size
    with open(local_path, 'rb') as local_fd:
      # Open a file on the remote.
      with self._sftp.open(target_path, file_flag) as remote_fd:
        # Speed up and defer the exception until close() called.
        remote_fd.set_pipelined(True)
        if resume:  # Seek depends on resume flag
          local_fd.seek(remote_size)
          logging.info('Resume uploading %r on target at %10d',
                       target_path, remote_size)
        while True:
          _UpdateUploadMetadata()  # Update metadata
          buf = local_fd.read(BLOCK_SIZE)
          remote_fd.write(buf)
          remote_fd.flush()
          remote_size += len(buf)
          if len(buf) == 0 or remote_size == local_size:
            break
      # Double confirm if the transfer succeed.
      confirmed_size = self._sftp.stat(target_path).st_size
      if confirmed_size != remote_size:
        logging.error('Size mismatch after a put action. remote_size = %d, '
                      'confirmed_size = %d. Resize the remote file to zero '
                      'so uploader can resume next time.',
                      remote_size, confirmed_size)
        remote_fd = self._sftp.open(target_path, 'w')
        remote_fd.close()
        remote_size = 0

    # We move the last metadata update outside the main loop because it is
    # possible that an exception throws at remote_fd.close(). In addition,
    # putting on the bottom of loop might causing false recognition by other
    # threads in uploader.
    _UpdateUploadMetadata()

    return True if remote_size == local_size else False

  def CalculateDigest(self, target_path):
    raise NotImplementedError
