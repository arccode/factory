# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os
import shelve
import shutil

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


BACKUP_DIRECTORY = 'backup'


class RecoveryException(Exception):
  pass


def IsShelfValid(shelf):
  """Checks whether a shelf can be loaded and unshelved.

  This is done in a separate process, since some databases (like gdbm)
  may throw fatal errors if the shelf is not valid.

  Returns:
    True if valid, False if not valid.
  """
  process = Spawn(['python', '-c',
                   'import factory_common, shelve, sys; '
                   'shelve.open(sys.argv[1], "r").items(); '
                   r'print "\nSHELF OK"',
                   os.path.realpath(shelf)],
                  cwd=os.path.dirname(__file__), call=True,
                  log=True, read_stdout=True, read_stderr=True)
  if process.returncode == 0 and process.stdout_data.endswith('SHELF OK\n'):
    return True

  logging.warn('Unable to validate shelf %r: '
               'returncode=%r, stdout=%r, stderr=%r',
               shelf, process.returncode,
               process.stdout_data, process.stderr_data)
  return False


def FindShelfFiles(shelf):
  """Returns all files in shelf.

  We assume this to be files that have the same name as the shelf, or
  the shelf plus dot and a suffix."""
  shelf_files = glob.glob(shelf + '.*')
  if os.path.exists(shelf):
    shelf_files.append(shelf)
  return shelf_files


def BackupShelfIfValid(shelf):
  """Validates a shelf, and backs it up if it is valid.

  Files that have the same name as the shelf, or the shelf plus dot and a
  suffix, are backed up.

  Returns:
    True if the shelf was valid and is backed up.
  """
  shelf_files = FindShelfFiles(shelf)
  if not shelf_files:
    # Nothing to back up.
    logging.info('Shelf %s not present; not backing up', shelf)
    return False

  if not IsShelfValid(shelf):
    logging.warn('Shelf %s is invalid; not backing up', shelf)
    return False

  backup_dir = os.path.join(os.path.dirname(shelf), BACKUP_DIRECTORY)
  utils.TryMakeDirs(backup_dir)
  logging.info('Backing up %s to %s', shelf_files, backup_dir)
  for f in shelf_files:
    shutil.copyfile(f, os.path.join(backup_dir, os.path.basename(f)))
  return True


def RecoverShelf(shelf):
  """Recovers a shelf from its backup.

  Raises:
    RecoveryException if unable to recover and validate the shelf.
  """
  backup_shelf = os.path.join(os.path.dirname(shelf),
                              BACKUP_DIRECTORY,
                              os.path.basename(shelf))

  # Validate the backup
  if not IsShelfValid(backup_shelf):
    raise IOError('Backup shelf %s is invalid or missing' % backup_shelf)

  shelf_files = FindShelfFiles(backup_shelf)
  assert shelf_files

  for f in shelf_files:
    dest_path = os.path.join(os.path.dirname(shelf),
                             os.path.basename(f))
    logging.info('Recovering %s to %s', f, dest_path)
    shutil.copyfile(f, dest_path)


def OpenShelfOrBackup(shelf, flag='c', protocol=None, writeback=False):
  """Opens a shelf, or its backup if invalid.

  If the shelf is valid, it is backed up.

  Args:
    shelf: Path to the shelf.
    Other arguments: See shelve.open.
  """
  if not FindShelfFiles(shelf) and flag in ['c', 'n']:
    # No worries; just create a new shelf.
    pass
  elif BackupShelfIfValid(shelf):
    # The shelf is valid.
    pass
  else:
    # Attempt to recover the shelf, throwing an exception if we can't.
    RecoverShelf(shelf)
    # At this point the shelf is guaranteed to be valid.

  return shelve.open(shelf, flag, protocol, writeback)
