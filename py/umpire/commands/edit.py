# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Edits an Umpire config file.

See ConfigEditor for detail.
"""

import logging
import os
import shutil
import subprocess
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.utils import file_utils
from cros.factory.umpire.common import UmpireError
from cros.factory.umpire import config as umpire_config


class ConfigEditor(object):
  """Edits an Umpire config file.

  The steps to edit the active Umpire config are:
  1. checks if a staging config exists, if not, staging active config.
  2. copies the staging config file to temporary directory;
  3. opens the temporary config file with default editor;
  4. after the user edits the file and closes the editor, validates the
     modified config file;
  5. if not okay, prompts error of validation failed and asks to edit again;
  6. if okay, moves the modified config file to resources folder and marks it
     staging;
  7. finally, prompts to run "umpire deploy".

  Note that in step 3, it needs to call Umpire to validate and once pass
  validation, Umpire needs to stage the config.

  Usage:
    config_editor = ConfigEditor(umpire_cli)
    config_editor.Edit(config_file="/path/to/config_file")
  """
  def __init__(self, umpire_cli, temp_dir=None, max_retry=1):
    """Constructor.

    Args:
      umpire_cli: A logical connection to Umpire XML-RPC server.
      temp_dir: temporary directory. If omitted, uses tempfile.mkdtemp()
          to created one.
      max_retry: number of tries before fail.
    """
    self._umpire_cli = umpire_cli
    self._should_rm_temp_dir = not temp_dir
    if not temp_dir:
      temp_dir = tempfile.mkdtemp()
    self._temp_dir = os.path.abspath(temp_dir)
    self._max_retry = max_retry

    # Config file to edit (in temporary directory).
    self._config_file = None

  def __del__(self):
    if self._should_rm_temp_dir:
      shutil.rmtree(self._temp_dir)

  def Edit(self, config_file=None):
    """Edits an Umpire config file.

    Args:
      config_file: path to config file. If omitted, retrives staging config from
          Umpire daemon.
    """
    self._PrepareConfigToEdit(config_file)

    validated = False
    for _ in xrange(self._max_retry):
      self._InvokeEditor()
      if self._Validate():
        validated = True
        break
    if not validated:
      raise UmpireError('Failed to validate config after %d retry.' %
                        self._max_retry)

    logging.info('Edited config validated. Staging it...')
    self._StageEditedConfig()

  def _PrepareConfigToEdit(self, config_file):
    """Prepares a config file to edit.

    Unless specified, it retrieves config from Umpire CLI server and stores
    in a temporary file for edit.
    """
    if config_file:
      with open(config_file) as c:
        config = c.read()
    else:
      config_file = 'umpire.yaml'
      config = self._umpire_cli.GetStagingConfig(True)

    if not config:
      raise UmpireError('Unable to load config file %s for edit' % config_file)

    self._config_file = os.path.join(self._temp_dir,
                                     os.path.basename(config_file))
    with open(self._config_file, 'w') as f:
      f.write(config)

    logging.info('Copied config to %s for edit', self._config_file)

  def _StageEditedConfig(self):
    """Copies config file to resources, stages it, and prompts user to deploy.
    """
    res_name = self._umpire_cli.UploadConfig(
        os.path.basename(self._config_file),
        open(self._config_file).read())
    # Force staging.
    self._umpire_cli.StageConfigFile(res_name, True)
    print ('Successful upload config to resource %r and mark it as staging.' %
           res_name)
    print 'You may deploy it using "umpire deploy".'

  def _InvokeEditor(self):
    """Invokes an editor to edit a config file to edit.

    It uses EDITOR defined in shell environment. If not specified, uses 'vi'.
    It is a blocking call.

    Raises:
      UmpireError: failed to invoke editor.
    """
    edit_command = os.environ.get('EDITOR', 'vi').split()
    edit_command.append(self._config_file)
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
    # Verify edited config locally (schema check).
    try:
      umpire_config.UmpireConfig(self._config_file)
    except Exception as e:
      header = ('Failed to load Umpire config. Reason:\n%s\nPlease fix it.'
                % str(e))
      header = ''.join('# %s\n' % line for line in header.split('\n'))
      file_utils.PrependFile(self._config_file, header)
      return False

    # Verify edited config on Umpire daemon (resource check).
    try:
      config = open(self._config_file).read()
      self._umpire_cli.ValidateConfig(config)
    except Exception as e:
      header = ('Failed to validate Umpire config in Umpire daemon. '
                'Reason:\n%s\nPlease fix it.' % str(e))
      header = ''.join('# %s\n' % line for line in header.split('\n'))
      file_utils.PrependFile(self._config_file, header)
      return False

    return True

  @property
  def config_file(self):
    return self._config_file

  @property
  def temp_dir(self):
    return self._temp_dir

  @property
  def max_retry(self):
    return self._max_retry
