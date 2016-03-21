#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import os
import re
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test.args import Arg
from cros.factory.test.dut.boards import android
from cros.factory.test.dut.boards import chromeos
from cros.factory.test.pytests.offline_test.shell import common
from cros.factory.utils import file_utils


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

  def _DisableChromeOSStartUpApp(self):
    self.dut.CheckCall(['chmod', '-x',
                        '/usr/local/factory/init/main.d/offline-test.sh'])

  def _DisableStartUpApp(self):
    if isinstance(self.dut, chromeos.ChromeOSBoard):
      self._DisableChromeOsStartUpApp()
    elif isinstance(self.dut, android.AndroidBoard):
      # TODO(stimim): support Android init
      raise NotImplementedError
    else:
      raise NotImplementedError

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

    # get total number of tasks
    test_script = self.dut.ReadFile(common.TestScriptPath(self.dut))
    match = re.search(r'^TOTAL_TASKS=(\d+)', test_script, re.MULTILINE)
    self.assertTrue(match)
    total_tasks = int(match.group(1))

    last_task_id = int(self.dut.ReadFile(
        self.dut.path.join(self.data_root, 'task_id')))

    if self.args.upload_to_shopfloor:
      shopfloor.UploadAuxLogs(upload_files,
                              self.args.shopfloor_dir_name)
    else:
      logging.info('logfile: %s',
                   file_utils.ReadFile(os.path.join(self.temp_dir, 'logfile')))

    # if the test succeeded, last_task_id should be (total_tasks + 1)
    if last_task_id != total_tasks + 1:
      fail_msg = 'offline test failed on test %d (total: %d)' % (
          last_task_id, total_tasks)
      factory.console.error(fail_msg)
      # show content of logfile in factory.log
      if self.args.upload_to_shopfloor:
        logging.error('logfile: %s',
                      file_utils.ReadFile(os.path.join(self.temp_dir,
                                                       'logfile')))
      self.fail(fail_msg)
