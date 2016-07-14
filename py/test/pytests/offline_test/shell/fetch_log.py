#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import logging
import os
import shutil
import tempfile
import time
import unittest
import zipfile

import factory_common  # pylint: disable=unused-import
from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test.pytests.offline_test.shell import common
from cros.factory.utils import file_utils
from cros.factory.utils.arg_utils import Arg


class OfflineTestFetchLog(unittest.TestCase):
  """Fetch results of shell offline test."""

  ARGS = [
      Arg('shopfloor_dir_name', str,
          'Relative directory on shopfloor', default='offline_test'),
      Arg('upload_to_shopfloor', bool,
          'Whether uploading fetched log file to shopfloor or not.',
          default=True)]

  def setUp(self):
    self.dut = dut.Create()
    self.data_root = common.DataRoot(self.dut)
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.exists(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def _DisableStartUpApp(self):
    self.dut.init.RemoveFactoryStartUpApp(common.OFFLINE_JOB_NAME)

  def _CompressLog(self, files):
    zipfile_name = '%s.zip' % time.strftime('%Y%m%d%H%M%S')
    zipfile_path = os.path.join(self.temp_dir, zipfile_name)
    with zipfile.ZipFile(zipfile_path, 'w') as myzip:
      for f in files:
        logging.info('zip file %r', f)
        myzip.write(f)

    return zipfile_path

  def runTest(self):
    # disable test script
    self._DisableStartUpApp()

    # fetch results
    upload_files = []
    for fname in ['logfile', 'task_id']:
      local_path = os.path.join(self.temp_dir, fname)
      remote_path = self.dut.path.join(self.data_root, fname)
      upload_files.append(local_path)

      try:
        self.dut.link.Pull(remote_path, local_path)
      except Exception:
        logging.exception('cannot fetch %s from DUT', remote_path)
        self.fail('cannot fetch %s from DUT' % remote_path)

    # get test spec
    test_spec = json.loads(self.dut.ReadFile(
        self.dut.path.join(self.data_root, 'test_spec.json')))
    total_tasks = len(test_spec)

    last_task_id = int(self.dut.ReadFile(
        self.dut.path.join(self.data_root, 'task_id')))

    if self.args.upload_to_shopfloor:
      dir_name = os.path.join(self.args.shopfloor_dir_name,
                              self.dut.info.mlb_serial_number)
      shopfloor.UploadAuxLogs([self._CompressLog(upload_files)],
                              dir_name=dir_name)
    else:
      logging.info('DUT mlb_serial_number: %s',
                   self.dut.info.mlb_serial_number)
      logging.info('logfile: %s',
                   file_utils.ReadFile(os.path.join(self.temp_dir, 'logfile')))

    # if the test succeeded, last_task_id should be (total_tasks + 1)
    if last_task_id != total_tasks + 1:

      failed_test = test_spec[last_task_id - 1]
      if 'shtest_name' in failed_test:
        failed_test_name = failed_test['shtest_name']
      elif 'pytest_name' in failed_test:
        failed_test_name = failed_test['pytest_name']
      else:
        raise ValueError('Cannot find shtest_name or pytest_name.')

      fail_msg = 'offline test failed on test %s (%d/%d)' % (
          failed_test_name, last_task_id, total_tasks)
      factory.console.error(fail_msg)
      # show content of logfile in factory.log
      if self.args.upload_to_shopfloor:
        logging.error('logfile: %s',
                      file_utils.ReadFile(os.path.join(self.temp_dir,
                                                       'logfile')))
      self.fail(fail_msg)
