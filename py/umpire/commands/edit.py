# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Edits an Umpire config file.

See ConfigEditor for detail.
"""

import errno
import logging
import os
import shutil
import subprocess
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire import config


class ConfigEditor(object):
  """Edits an Umpire config file.

  The steps to edit the active Umpire config are:
  1. copies the staging config file to temporary directory;
  2. opens the temporary config file with default editor;
  3. after the user edits the file and closes the editor, validates the
     modified config file;
  4. if not okay, prompts error of validation failed and asks to edit again;
  5. if okay, moves the modified config file to resources folder and marks it
     staging;
  6. finally, prompts to run "umpire deploy".

  Usage:
    config_editor = ConfigEditor(env)
    config_editor.Edit(config_file="/path/to/config_file")
  """
  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env
    self._config_file = None
    self._config_file_to_edit = None
    self._temp_dir = None
    self._should_rm_temp_dir = False
    self._max_retry = 3

  def __del__(self):
    if self._should_rm_temp_dir:
      shutil.rmtree(self._temp_dir)

  @property
  def config_file(self):
    return self._config_file

  @property
  def config_file_to_edit(self):
    return self._config_file_to_edit

  @property
  def temp_dir(self):
    return self._temp_dir

  @property
  def max_retry(self):
    return self._max_retry

  @max_retry.setter
  def max_retry(self, value):
    """Only for unittest."""
    self._max_retry = value

  def Edit(self, config_file=None, temp_dir=None):
    """Edits an Umpire config file.

    Args:
      config_file: path to config file. If omitted, uses staging config.
      temp_dir: temporary directory. If omitted, uses tempfile.mkdtemp()
      created one.
    """
    # TODO(deanliao): retrieve staging file from umpired and store it locally
    #     (self._config_file_to_edit).
    self._Prepare(config_file, temp_dir)
    file_utils.AtomicCopy(self._config_file, self._config_file_to_edit)
    logging.info('Copy target %s to %s for edit.', self._config_file,
                 self._config_file_to_edit)

    # TODO(deanliao): ask umpired to validate edited file as umpired
    #     can validate resources.
    self._EditValidate()

    # TODO(deanliao): ask umpired to staging the validated config file.
    logging.info('Edited config validated. Staging it...')
    self._StagingEditedConfig()

  def _Prepare(self, config_file, temp_dir):
    """Sets up members _config_file, _temp_file and _config_file_to_edit."""
    if config_file:
      self._config_file = config_file
    else:
      self._config_file = self._env.staging_config_file

    if not os.path.isfile(self._config_file):
      raise IOError(errno.ENOENT, 'Missing config file', self._config_file)

    if temp_dir:
      self._temp_dir = temp_dir
    else:
      self._temp_dir = tempfile.mkdtemp()
      self._should_rm_temp_dir = True

    self._config_file_to_edit = os.path.join(
        self._temp_dir, os.path.basename(self._config_file))

  def _EditValidate(self):
    """Calls editor to edit config file and validates it after edit.

    Note that if validation failed, it will let user retry self._max_retry
    times with failed reason prepend to the config file.

    Raises:
      UmpireError: failed to invoke editor or validate edited result.
      IOError: missing config file to edit.
    """

    if not os.path.isfile(self._config_file_to_edit):
      raise IOError(errno.ENOENT, 'Missing cloned config file',
                    self._config_file)

    for _ in xrange(self._max_retry):
      self._InvokeEditor(self._config_file_to_edit)
      if self._Validate(self._config_file_to_edit):
        return
    raise UmpireError('Failed to validate config after %d retry.' %
                      self._max_retry)

  def _StagingEditedConfig(self):
    """Copies config file to resources, stages it, and prompts user to deploy.
    """
    new_config_file = self._env.AddResource(self._config_file_to_edit)
    self._env.StageConfigFile(new_config_file, force=True)
    print 'Successful editing %s.' % self._config_file
    print 'You may deploy it using "umpire deploy".'

  @staticmethod
  def _InvokeEditor(file_to_edit):
    """Invokes default editor to edit a config file.

    It is a blocking call.

    Args:
      file_to_edit: path to the config file to edit.

    Raises:
      UmpireError: failed to invoke editor.
    """
    edit_command = os.environ.get('EDITOR', 'vi').split()
    edit_command.append(file_to_edit)
    try:
      # Use subprocess.call to avoid redirect stdin/stdout from terminal
      # to pipe. vim needs stdin/stdout as terminal.
      subprocess.call(edit_command)
    except Exception as e:
      raise UmpireError('Unable to invoke editor: %s\nReason: %s' %
                        (' '.join(edit_command), str(e)))

  @staticmethod
  def _Validate(config_file):
    """Validates a config file.

    If validation failed, prepends reason to the config file.

    Args:
      config_file: path to the config file to validate.

    Returns:
      True if the config is validated; False otherwise.
    """
    try:
      config.UmpireConfig(config_file)
      return True
    except Exception as e:
      header = ('Failed to validate Umpire config: %s. Reason:\n%s\n'
                'Please fix it.') % (config_file, str(e))
      header = ''.join('# %s\n' % line for line in header.split('\n'))
      file_utils.PrependFile(config_file, header)
      return False

