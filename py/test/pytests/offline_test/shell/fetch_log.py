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
import xmlrpc.client
import zipfile

from cros.factory.device import device_utils
from cros.factory.test.pytests.offline_test.shell import common
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils


LOGS_ARG_HELP = """
Set customized log files.
A list of tuples: (local_fpath, remote_fpath, required).

* - ``local_fpath``: (str) The file path stored in local. We can not use
    absolute path of local_fpath.
  - ``remote_fpath``: (str) The file path from remote which will be
    os.path.join with self.data_root.
  - ``required``: (bool) Check if it is required or not. If this log is
    required but we do not get it, we will raise exception.
"""


class OfflineTestFetchLog(unittest.TestCase):
  """Fetch results of shell offline test."""

  ARGS = [
      Arg('logs', list, LOGS_ARG_HELP, default=[]),
      Arg('shopfloor_dir_name', str,
          'Relative directory on shopfloor', default='offline_test'),
      Arg('upload_to_shopfloor', bool,
          'Whether uploading fetched log file to shopfloor or not.',
          default=True)]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.data_root = common.DataRoot(self.dut)
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.exists(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def _DisableStartUpApp(self):
    self.dut.init.RemoveFactoryStartUpApp(common.OFFLINE_JOB_NAME)

  def _FetchFiles(self, local_fpath, remote_fpath, required):
    local_path = os.path.join(self.temp_dir, local_fpath)
    remote_path = self.dut.path.join(self.data_root, remote_fpath)
    try:
      self.dut.link.Pull(remote_path, local_path)
    except Exception:
      logging.exception('cannot fetch %s from DUT', remote_path)
      if required:
        self.fail('cannot fetch %s from DUT' % remote_path)
      else:
        return []
    return [local_path]

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
      local_path = self._FetchFiles(fname, fname, True)
      upload_files += local_path

    # fetch customized logs
    for local, remote, required in self.args.logs:
      local_path = self._FetchFiles(local, remote, required)
      upload_files += local_path

    # get test spec
    test_spec = json.loads(self.dut.ReadFile(
        self.dut.path.join(self.data_root, 'test_spec.json')))
    total_tasks = len(test_spec)

    last_task_id = int(self.dut.ReadFile(
        self.dut.path.join(self.data_root, 'task_id')))

    if self.args.upload_to_shopfloor:
      dir_name = os.path.join(self.args.shopfloor_dir_name,
                              self.dut.info.mlb_serial_number)
      # TODO(hungte) Change this by test log?
      proxy = server_proxy.GetServerProxy()
      zip_file = self._CompressLog(upload_files)
      proxy.SaveAuxLog(
          os.path.join(dir_name, os.path.basename(zip_file)),
          xmlrpc.client.Binary(file_utils.ReadFile(zip_file, encoding=None)))
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
      session.console.error(fail_msg)
      # show content of logfile in factory.log
      if self.args.upload_to_shopfloor:
        logging.error('logfile: %s',
                      file_utils.ReadFile(os.path.join(self.temp_dir,
                                                       'logfile')))
      self.fail(fail_msg)
