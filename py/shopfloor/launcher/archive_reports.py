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
from cros.factory.shopfloor import REPORTS_DIR
from cros.factory.shopfloor.launcher import env
from cros.factory.test.utils import TryMakeDirs
from cros.factory.utils.process_utils import Spawn

SHOPFLOOR_DATA_DIR = 'shopfloor_data'
ARCHIVE_DIR = 'archive'
RECYCLE_DIR = 'recycle_bin'

LOGS_PREFIX = 'logs.'
IN_PROGRESS_SUFFIX = '.INPROGRESS'
ARCHIVE_SUFFIX = '.tar.bz2'

# Check report folder every _DEFAULT_PERIOD_MINUTES
_DEFAULT_PERIOD_MINUTES = 10


def ArchiveReports(minutes):
  """Archives reports.

  This archiver searches reports directory periodically and archives past logsi
  into archive folder.

  Args:
    minutes: checking period in minutes.
  """

  reports_dir = os.path.join(env.runtime_dir, SHOPFLOOR_DATA_DIR, REPORTS_DIR)
  archive_dir = os.path.join(env.runtime_dir, SHOPFLOOR_DATA_DIR, ARCHIVE_DIR)
  recycle_dir = os.path.join(env.runtime_dir, SHOPFLOOR_DATA_DIR, RECYCLE_DIR)
  map(TryMakeDirs, [reports_dir, archive_dir, recycle_dir])

  # Get an accending order list of dirs in watching dir.
  dirs = filter((lambda path: os.path.isdir(os.path.join(reports_dir, path)) and
                path.startswith(LOGS_PREFIX)), os.listdir(reports_dir))
  dirs.sort()
  logging.debug('Found %d report dirs.', len(dirs))
  if len(dirs) == 0:
    logging.debug('reports_dir = %s', reports_dir)
    logging.debug('os.listdir() = %s', os.listdir(reports_dir))
  # Archive and remove log dirs except for lastest 2 entries.
  for report_name in dirs[:-2]:
    logging.debug('Starting to archive %s', report_name)
    report_fullpath = os.path.join(reports_dir, report_name)
    archive_name = report_name + ARCHIVE_SUFFIX
    archived_log = os.path.join(archive_dir, archive_name)
    in_progress_name = archived_log + IN_PROGRESS_SUFFIX

    # Ignore and recycle archived reports
    if os.path.isfile(archived_log):
      logging.debug('Recycle archived report: %s', archive_name)
      shutil.move(os.path.join(reports_dir, report_name), recycle_dir)
      continue

    # Recycle empty report folder
    if len(os.listdir(report_fullpath)) == 0:
      logging.debug('Recycle emtpy report folder: %s', report_name)
      shutil.move(report_fullpath, recycle_dir)
      continue

    # Delete interrupted temp file
    if os.path.isfile(in_progress_name):
      logging.debug('Removing previous in-progress file.')
      os.unlink(in_progress_name)

    have_pbzip2 = Spawn(
        ['which', 'pbzip2'],
        ignore_stdout=True, ignore_stderr=True, call=True).returncode == 0
    Spawn(['tar', '-I', 'pbzip2' if have_pbzip2 else 'bzip2',
           '-cf', in_progress_name, '-C', reports_dir,
           report_name],
           check_call=True, log=True, log_stderr_on_error=True)
    shutil.move(in_progress_name, archived_log)
    shutil.move(report_fullpath, recycle_dir)
    logging.info('Finishing archiving %s to %s',
                 report_name, archive_name)

    reactor.callLater(minutes * 60,  # pylint: disable=E1101
                      ArchiveReports, minutes)

def SignalHandler(dummy_signal, dummy_frame):
  # Call reactor.stop() from reactor instance to make sure no spawned process
  # is running parallely.
  logging.info('Stopping...')
  reactor.callLater(1, reactor.stop)  # pylint: disable=E1101

def main():
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  parser = optparse.OptionParser()
  parser.add_option('-p', '--period', dest='period', metavar='PERIOD_MINITES',
                    default=_DEFAULT_PERIOD_MINUTES,
                    help='run every N minutes (default: %default)')
  (options, args) = parser.parse_args()
  if args:
    parser.error('Invalid args: %s' % ' '.join(args))

  # Start the first cycle.
  reactor.callLater(1, ArchiveReports, options.period)  # pylint: disable=E1101

  signal.signal(signal.SIGTERM, SignalHandler)
  signal.signal(signal.SIGINT, SignalHandler)
  reactor.run(installSignalHandlers=0)  # pylint: disable=E1101


if __name__ == '__main__':
  main()
