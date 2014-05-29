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

  Note that in step 3, it needs to call Umpire to validate and once pass
  validation, Umpire needs to stage the config.

  Usage:
    config_editor = ConfigEditor(env, umpire_cli)
    config_editor.Edit(config_file="/path/to/config_file")
  """
  def __init__(self, env, umpire_cli=None, temp_dir=None):
    """Constructor.

    Args:
      env: UmpireEnv object.
      umpire_cli: A logical connection to Umpire XML-RPC server.
      temp_dir: temporary directory. If omitted, uses tempfile.mkdtemp()
          to created one.
    """
    self._env = env
    self._umpire_cli = umpire_cli
    self._temp_dir = temp_dir if temp_dir else tempfile.mkdtemp()
    self._temp_dir = os.path.abspath(self._temp_dir)
    self._should_rm_temp_dir = not temp_dir

    self._config_file = None
    self._config_file_to_edit = None

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

  def Edit(self, config_file=None):
    """Edits an Umpire config file.

    Args:
      config_file: path to config file. If omitted, uses staging config.
    """
    self._PrepareConfigToEdit(config_file)

    self._EditValidate()

    logging.info('Edited config validated. Staging it...')
    self._StageEditedConfig()

  def _PrepareConfigToEdit(self, config_file):
    """Prepares a config file to edit.

    It copies the config file to edit (default is staging config file) to
    a temporary file.
    """
    if config_file:
      self._config_file = config_file
    else:
      # For now, we assume Umpire daemon and CLI share the same file access
      # permission. It should be no longer true in the near future (we don't
      # plan to let Umpired user have login permission.)
      # TODO(deanliao): retrieve staging file from Umpire daemon.
      self._config_file = self._env.staging_config_file

    if not os.path.isfile(self._config_file):
      raise IOError(errno.ENOENT, 'Missing config file', self._config_file)

    self._config_file_to_edit = os.path.join(
        self._temp_dir, os.path.basename(self._config_file))

    file_utils.AtomicCopy(self._config_file, self._config_file_to_edit)
    logging.info('Copied target %s to %s for edit.', self._config_file,
                 self._config_file_to_edit)


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
                    self._config_file_to_edit)

    for _ in xrange(self._max_retry):
      self._InvokeEditor()
      if self._Validate():
        return
    raise UmpireError('Failed to validate config after %d retry.' %
                      self._max_retry)

  def _StageEditedConfig(self):
    """Copies config file to resources, stages it, and prompts user to deploy.
    """
    if self._umpire_cli:
      res_name = self._umpire_cli.AddResource(self._config_file_to_edit)
      self._umpire_cli.StageConfigFile(res_name, force=True)
    else:
      new_config_file = self._env.AddResource(self._config_file_to_edit)
      self._env.StageConfigFile(new_config_file, force=True)
    print 'Successful editing %s.' % self._config_file
    print 'You may deploy it using "umpire deploy".'

  def _InvokeEditor(self):
    """Invokes an editor to edit a config file to edit.

    It uses EDITOR defined in shell environment. If not specified, uses 'vi'.
    It is a blocking call.

    Raises:
      UmpireError: failed to invoke editor.
    """
    edit_command = os.environ.get('EDITOR', 'vi').split()
    edit_command.append(self._config_file_to_edit)
    try:
      # Use subprocess.call to avoid redirect stdin/stdout from terminal
      # to pipe. vim needs stdin/stdout as terminal.
      subprocess.call(edit_command)
    except Exception as e:
      raise UmpireError('Unable to invoke editor: %s\nReason: %s' %
                        (' '.join(edit_command), str(e)))

  def _Validate(self):
    """Validates a config file to edit.

    It tries to load the config file to edit. Also, if self._umpire_cli is
    given, it asks Umpire daemon to validate the config file, too.

    If validation failed, prepends reason to the config file.

    Returns:
      True if the config is validated; False otherwise.
    """
    target = self._config_file_to_edit
    try:
      config.UmpireConfig(target)
      if self._umpire_cli:
        self._umpire_cli.ValidateConfig(target)
      return True
    except Exception as e:
      header = ('Failed to validate Umpire config: %s. Reason:\n%s\n'
                'Please fix it.') % (target, str(e))
      header = ''.join('# %s\n' % line for line in header.split('\n'))
      file_utils.PrependFile(target, header)
      return False

