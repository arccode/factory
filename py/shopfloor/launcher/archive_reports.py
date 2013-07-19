#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The application periodically archives shopfloor reports."""


import logging
import optparse
import os
import shutil
import signal
from twisted.internet import reactor

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor import INCREMENTAL_EVENTS_DIR
from cros.factory.shopfloor import REPORTS_DIR
from cros.factory.test.shopfloor import get_instance
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.test.utils import FormatExceptionOnly, TryMakeDirs
from cros.factory.utils.process_utils import Spawn

ARCHIVE_DIR = 'archive'
RECYCLE_DIR = 'recycle_bin'

LOGS_PREFIX = 'logs.'
IN_PROGRESS_SUFFIX = '.INPROGRESS'
ARCHIVE_SUFFIX = '.tar.bz2'

# Check report folder every _DEFAULT_PERIOD_MINUTES
_DEFAULT_PERIOD_MINUTES = 10

# Default URL for the XMLRPC server
_DEFAULT_RPC_URL = 'http://localhost:8082/'


def ArchiveLogs(options):
  """Archives logs.

  This archiver searches reports and incremental events directories
  periodically and archives log folders to destination folder.

  Args:
    options.period: checking period in minutes.
    options.recycle: move archived logs into recycle dir.
    options.rpc_url: the URL to the RPC server.
  """

  shopfloor_data = os.path.join(env.runtime_dir, constants.SHOPFLOOR_DATA)
  archive_dir = os.path.join(shopfloor_data, ARCHIVE_DIR)
  recycle_dir = None
  map(TryMakeDirs, [archive_dir, recycle_dir] +
      [os.path.join(shopfloor_data, folder) for folder in options.dirs] +
      [os.path.join(archive_dir, folder) for folder in options.dirs])

  if options.recycle:
    recycle_dir = os.path.join(shopfloor_data, RECYCLE_DIR)
    map(TryMakeDirs, [os.path.join(recycle_dir, folder)
                      for folder in options.dirs])

  # Trigger to generate all log dirs. Empty directory will be recycled later.
  try:
    if REPORTS_DIR in options.dirs:
      get_instance(url=options.rpc_url, timeout=5).GetReportsDir()
    if INCREMENTAL_EVENTS_DIR in options.dirs:
      get_instance(url=options.rpc_url, timeout=5).GetIncrementalEventsDir()
  except: #pylint: disable=W0702
    exception_string = FormatExceptionOnly()
    # Continue to archive if the backend even if the backend is down.
    logging.error(
        'Failed to make RPC call - %s, ignore and continue.',
        exception_string)

  for folder in options.dirs:
    ArchiveFolder(os.path.join(shopfloor_data, folder),
                  os.path.join(archive_dir, folder),
                  recycle_dir=recycle_dir)

  # Restart timer
  reactor.callLater(int(options.period) * 60,  # pylint: disable=E1101
                    ArchiveLogs, options)


def ArchiveFolder(folder, dest_folder, log_prefix=LOGS_PREFIX,
                  suffix='', skip=-2, recycle_dir=None):
  """Archives the dirs with prefix inside a folder.

  Parameters:
    folder: The parent folder contains log dirs.
    dest_folder: The folder to store archived files.
    log_prefix: Log dir name prefix.
    suffix: Generated archive filename suffix.
    skip: Number of log dirs to skip. Skipping last 2 log dirs by default.
  """
  # Get an accending order list of incremental events dirs.
  dirs = filter((lambda path: os.path.isdir(os.path.join(folder, path)) and
                path.startswith(log_prefix)), os.listdir(folder))
  dirs.sort()
  if len(dirs) == 0:
    logging.debug('watching dir = %s', folder)
    logging.debug('os.listdir() = %s', os.listdir(folder))

  dirs = dirs[:skip] if skip < 0 else dirs[skip:]

  for log_name in dirs:
    logging.debug('Archiving %s', log_name)
    log_fullpath = os.path.join(folder, log_name)
    archive_name = log_name + suffix + ARCHIVE_SUFFIX
    archived_log = os.path.join(dest_folder, archive_name)
    in_progress_name = archived_log + IN_PROGRESS_SUFFIX

    # Ignore archived reports
    if os.path.isfile(archived_log):
      if recycle_dir:
        logging.debug('Recycling archived log: %s', log_name)
        shutil.move(log_fullpath, os.path.join(recycle_dir, log_name + suffix))
      else:
        logging.debug('Removing archived log: %s', log_name)
        shutil.rmtree(log_fullpath)
      continue

    # Remove empty report folder
    if len(os.listdir(log_fullpath)) == 0:
      logging.debug('Removing emtpy log folder: %s', log_name)
      shutil.rmtree(log_fullpath)
      continue

    # Delete interrupted temp file
    if os.path.isfile(in_progress_name):
      logging.debug('Removing previous in-progress file.')
      os.unlink(in_progress_name)

    have_pbzip2 = Spawn(
        ['which', 'pbzip2'],
        ignore_stdout=True, ignore_stderr=True, call=True).returncode == 0
    Spawn(['tar', '-I', 'pbzip2' if have_pbzip2 else 'bzip2',
           '-cf', in_progress_name, '-C', folder,
           log_name],
           check_call=True, log=True, log_stderr_on_error=True)
    shutil.move(in_progress_name, archived_log)
    if recycle_dir:
      shutil.move(log_fullpath, recycle_dir)
    else:
      shutil.rmtree(log_fullpath)
    logging.info('Finished archive %s to %s',
                 log_name, archive_name)

def SignalHandler(dummy_signal, dummy_frame):
  # Call reactor.stop() from reactor instance to make sure no spawned process
  # is running parallely.
  logging.info('Stopping...')
  reactor.callLater(1, reactor.stop)  # pylint: disable=E1101

def main():
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  parser = optparse.OptionParser()
  parser.add_option('-p', '--period', dest='period', metavar='PERIOD_MINITES',
                    default=_DEFAULT_PERIOD_MINUTES, type='int',
                    help='run every N minutes (default: %default)')
  parser.add_option('-d', '--dir', dest='dirs', metavar='DIR',
                    action='append', default=['reports'],
                    help='the folder(s) to watch (default: %default)')
  parser.add_option('-r', '--recycle', dest='recycle', action='store_true',
                    help='move archived logs to recycle bin')
  parser.add_option('-u', '--rpc_url', dest='rpc_url', metavar='RPC_URL',
                    default=_DEFAULT_RPC_URL, type='str',
                    help="RPC server's URL (default: %default)")
  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  # Start the first cycle, give the httpd (RPC Server) 30 seconds to be up
  # before making the first RPC call.
  reactor.callLater(30, ArchiveLogs, options)  # pylint: disable=E1101

  signal.signal(signal.SIGTERM, SignalHandler)
  signal.signal(signal.SIGINT, SignalHandler)
  reactor.run(installSignalHandlers=0)  # pylint: disable=E1101


if __name__ == '__main__':
  main()
