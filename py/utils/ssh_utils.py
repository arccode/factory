# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for ssh and rsync.

This module is intended to work with Chrome OS DUTs only as it uses Chrome OS
testing_rsa identity.
"""

import os
import shutil
import tempfile

import factory_common  # pylint: disable=W0611
from cros.factory.utils import process_utils


# The path to the testing_rsa identity file.
testing_rsa = None


def _Init():
  """Initializes ssh identity.

  The identity file is created per user in /tmp as testing_rsa.${USER}.  We
  first create a temp identity file from the reference testing_rsa identity and
  change file mode to 0400 so it is only readable by the user.  We then move the
  temp file to our target /tmp/testing_rsa.${USER}.  We do not have race
  condition here since the move operation is atomic.

  We do not use generated temp files because we do not want to leave dangling
  temp files around.
  """
  global testing_rsa    # pylint: disable=W0603
  if not testing_rsa:
    temp_fd, temp_file_name = tempfile.mkstemp()

    # Copy testing_rsa into a private file since otherwise ssh will ignore it
    os.write(temp_fd, open(os.path.join(
        os.environ.get('CROS_WORKON_SRCROOT'),
        'src/scripts/mod_for_test_scripts/ssh_keys/testing_rsa')).read())
    os.fsync(temp_fd)
    os.fchmod(temp_fd, 0400)
    os.close(temp_fd)

    # Rename the temp file to the target file name.
    target_name = '/tmp/testing_rsa.%s' % os.environ.get('USER')
    shutil.move(temp_file_name, target_name)
    testing_rsa = target_name


def BuildSSHCommand():
  """Builds SSH command that can be used to connect to a DUT."""
  _Init()
  return ['ssh',
          '-o', 'IdentityFile=%s' % testing_rsa,
          '-o', 'UserKnownHostsFile=/dev/null',
          '-o', 'User=root',
          '-o', 'StrictHostKeyChecking=no']


def BuildRsyncCommand():
  """Build rsync command that can be used to rsync to a DUT."""
  _Init()
  return ['rsync', '-e', ' '.join(BuildSSHCommand())]


def SpawnSSHToDUT(args, **kwargs):
  """Spawns a process to issue ssh command to a DUT.

  Args:
    args: Args appended to the ssh command.
    kwargs: See docstring of Spawn.
  """
  return process_utils.Spawn(BuildSSHCommand() + args, **kwargs)


def SpawnRsyncToDUT(args, **kwargs):
  """Spawns a process to issue rsync command to a DUT.

  Args:
    args: Arguments appended to the rsync command.
    kwargs: See docstring of Spawn.
  """
  return process_utils.Spawn(BuildRsyncCommand() + args, **kwargs)
