# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Export specific log, such as factory log, DUT report, and ECHO codes.

See LogExporter comments for usage.
"""

import datetime
import os

from cros.factory.umpire import common
from cros.factory.utils import process_utils


class LogExporter:

  def __init__(self, env):
    """Constructor.

    Args:
      env: UmpireEnv object.
    """
    self._env = env

  def DateRange(self, start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
      yield start_date + datetime.timedelta(days=n)

  def GetBytes(self, size, unit):
    if unit == 'MB':
      return size * 1024**2
    if unit == 'GB':
      return size * 1024**3
    raise ValueError('This is not a valid unit')

  def CompressFilesFromListToPath(self, src_dir, dst_path, filenames):
    cmd = ['tar', '-cjf', dst_path, '-C', src_dir]
    cmd.extend(filenames)
    process_utils.Spawn(cmd, check_call=True, log=True)

  def CompressFilesFromList(self, index, date, src_dir, dst_dir, filenames):
    tar_file = '{}-{}.tar.bz2'.format(date, index)
    dst_path = os.path.join(dst_dir, tar_file)
    self.CompressFilesFromListToPath(src_dir, dst_path, filenames)
    return tar_file

  def CompressFilesLimitedMaxSize(
      self, date, src_dir, dst_dir, max_archive_size):
    filenames = []
    current_archive_size = 0
    tar_files = []

    for (root, unused_dirs, files) in os.walk(src_dir):
      for filename in files:
        filepath = os.path.join(root, filename)
        relpath = os.path.relpath(filepath, src_dir)
        file_size = os.path.getsize(filepath)
        if current_archive_size + file_size > max_archive_size:
          if not filenames:
            continue
          tar_files.append(self.CompressFilesFromList(
              len(tar_files), date, src_dir, dst_dir, filenames))
          current_archive_size = file_size
          filenames = [relpath]
        else:
          current_archive_size += file_size
          filenames.append(relpath)

    if filenames:
      tar_files.append(self.CompressFilesFromList(
          len(tar_files), date, src_dir, dst_dir, filenames))

    return tar_files

  def ExportLog(
      self, dst_dir, log_type, split_size, start_date_str, end_date_str):
    """Compress and export a specific log, such as factory log, DUT report,
    or csv files.

    Args:
      dst_dir: the destination directory to export the specific log.
      log_type: download type of the log, e.g. log, report, csv.
      split_size: maximum size of the archives.
                  (format: {'size': xxx, 'unit': 'MB'/'GB'})
      start_date: start date (format: yyyymmdd)
      end_date: end date (format: yyyymmdd)

    Returns:
      {
        'messages': array (messages of ExportLog)
        'log_paths': array (files paths of compressed files)
      }
    """
    umpire_data_dir = self._env.umpire_data_dir
    sub_dir = {
        'csv': 'csv',
        'report': 'report',
        'log': 'aux_log'
    }[log_type]
    split_bytes = self.GetBytes(split_size['size'], split_size['unit'])
    messages = []

    try:
      if log_type == 'csv':
        compressed_file_name = 'csv.tar.bz2'
        dst_path = os.path.join(dst_dir, compressed_file_name)
        self.CompressFilesFromListToPath(umpire_data_dir, dst_path, [sub_dir])

        if os.path.isfile(dst_path):
          return {
              'messages': messages,
              'log_paths': [compressed_file_name],
          }

        messages.append('%s does not exist' % compressed_file_name)
        return {
            'messages': messages,
            'log_paths': [],
        }

      if log_type in ('report', 'log'):
        start_date = datetime.datetime.strptime(start_date_str, '%Y%m%d').date()
        end_date = datetime.datetime.strptime(end_date_str, '%Y%m%d').date()
        tar_files_list = []
        no_logs = True
        for date in self.DateRange(start_date, end_date):
          date_str = date.strftime('%Y%m%d')
          src_dir = os.path.join(umpire_data_dir,
                                 sub_dir,
                                 date_str)
          if not os.path.isdir(src_dir) or not os.listdir(src_dir):
            continue
          no_logs = False
          tar_files = self.CompressFilesLimitedMaxSize(
              date_str, src_dir, dst_dir, split_bytes)
          tar_files_list.extend(tar_files)
        if no_logs:
          messages.append('no {}s for {} ~ {}'.format(log_type,
                                                      start_date,
                                                      end_date))
        return {
            'messages': messages,
            'log_paths': tar_files_list,
        }
      raise common.UmpireError('Failed to export %s: No such type' % log_type)
    except Exception as e:
      raise common.UmpireError('Failed to export %s\n%r' % (log_type, e))
