#!/usr/bin/python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import getpass
import logging
import os
import paramiko

import uploader

from uploader_exception import UploaderConnectionError, UploaderFieldError


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
      self._sftp.listdir('.')
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
        self._sftp.listdir('.')
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

    The appended tuple will be in the form
      A list containing tuples of (absolute path, file size,
      last modification timestamp - mtime)
    """
    raise NotImplementedError()

  def ListFiles(self):
    raise NotImplementedError()

  def FetchFile(self, source_path, target_path,
                metadata_path=None, resume=True):
    raise NotImplementedError()

  def CalculateDigest(self, source_path):
    raise NotImplementedError()

  def MoveFile(self, from_path, to_path):
    raise NotImplementedError()

  def CheckDirectory(self, dir_path):
    raise NotImplementedError()

  def CreateDirectory(self, dir_path):
    raise NotImplementedError()
