# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests RF chip's transmitting and receiving capabilities using Graphyte.

Usage example::

  FactoryTest(
      id='RFConductive',
      label_zh=u'射频传导测试',
      pytest_name='rf_graphyte',
      dargs={
          'graphyte_config_file': 'conductive_config.json',
          'verbose': True,
          'enable_shopfloor': True,
          'shopfoor_parameter_dir': 'rf_conductive',
          'shopfloor_log_dir': 'rf_conductive'})
"""

import logging
import os
import subprocess
import time
import unittest

import factory_common  # pylint: disable=W0611

from cros.factory.test import dut
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg
from cros.factory.test.env import paths


# The Graphyte config files (pathloss, test plan, port config) should be placed
# in the rf_graphyte folder.
LOCAL_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
# The log files are in the default log folder.
RESULT_FILENAME = 'graphyte_result.csv'
LOG_FILENAME = 'graphyte.log'

_ID_MSG_DIV = '_msg'
_ID_DEBUG_DIV = '_debug'

_CSS = """
  #%s {
    font-size: 2em;
    color: blue;
  }
  #%s {
    text-align: left;
    height: 70%%;
    overflow: auto;
  }
""" % (_ID_MSG_DIV, _ID_DEBUG_DIV)

_STATE_HTML = """
  <div id='%s'></div>
  <div id='%s'></div>
""" % (_ID_MSG_DIV, _ID_DEBUG_DIV)

_MSG_FETCH_CONFIG = test_ui.MakeLabel(
    'Fetching config files from shopfloor',
    u'从 shopfloor 下载测试参数',
    'message')
_MSG_EXECUTE_GRAPHYTE = test_ui.MakeLabel(
    'Executing Graphyte',
    u'執行 Graphyte',
    'message')
_MSG_UPLOAD_RESULT = test_ui.MakeLabel(
    'Uploading result files to shopfloor',
    u'上傳测试纪录到 shopfloor',
    'message')

class RFGraphyteTest(unittest.TestCase):

  ARGS = [
      Arg('graphyte_config_file', str,
          'Path to Graphyte config file. This is interpreted as the path '
          'relative to `test/pytests/rf_graphyte` folder.',
          optional=False),
      Arg('verbose', bool, 'Enable Graphyte debug logging',
          default=True, optional=True),
      Arg('enable_shopfloor', bool,
          'Whether or not to use shopfloor. If True, the test will try to '
          'update config files from shopfloor, and upload the log and result '
          'file to shopfloor server. If False, the test will load config file '
          'from local disk and does not upload log.',
          default=True, optional=False),
      Arg('shopfloor_parameter_dir', str,
          'Directory in which to place the updated config files. All the files '
          'in this folder will be downloaded to `test/pytests/rf_graphyte` '
          'folder. Only takes effect if "enable_shopfloor" is set to True.',
          default='rf_graphyte', optional=True),
      Arg('shopfloor_log_dir', str, 'Directory in which to save logs on '
          'shopfloor.  For example: "wifi_radiated".  Only takes effect if '
          '"enable_shopfloor" is set to True.',
          default='rf_graphyte', optional=True),
      ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._ui.AppendCSS(_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetState(_STATE_HTML)
    self._dut = dut.Create()
    if self.args.enable_shopfloor:
      self._shopfloor_proxy = shopfloor.GetShopfloorConnection()

    timestamp = time.strftime('%H%M%S')
    self.result_file_path = self.GetLogPath(timestamp, RESULT_FILENAME)
    self.log_file_path = self.GetLogPath(timestamp, LOG_FILENAME)

  def runTest(self):
    # Update the config file from shopfloor.
    self.FetchConfigFromShopfloor()

    # Check the config file exists.
    config_file_path = os.path.join(
        LOCAL_CONFIG_DIR, self.args.graphyte_config_file)
    if not os.path.exists(config_file_path):
      self.fail('Graphyte config file %s does not exist.' % config_file_path)

    # Execute Graphyte.
    self._ui.SetHTML(_MSG_EXECUTE_GRAPHYTE, id=_ID_MSG_DIV)
    cmd = ['python', '-m', 'graphyte.main',
           '--config-file', config_file_path,
           '--result-file', self.result_file_path,
           '--log-file', self.log_file_path]
    if self.args.verbose:
      cmd.append('-v')
    factory.console.info('Call the Graphyte command: %s', ' '.join(cmd))
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)

    # Output to UI
    debug_str = ''
    while True:
      line = process.stdout.readline()
      if not line:
        break
      # Keep 8Kb data.
      debug_str = (test_ui.Escape(line) + debug_str)[:8 * 1024]
      self._ui.SetHTML(debug_str, id=_ID_DEBUG_DIV)

    # Parse result file.
    # TODO(akahuang): Send result to testlog.
    if not os.path.exists(self.result_file_path):
      self.fail('Result file is not found.')
    with open(self.result_file_path) as result_file:
      result_data = result_file.read()
      logging.debug('Graphyte result: %s', result_data)

    # Total test result is at the last column of the last row.
    result_lines = result_data.splitlines()
    final_result = result_lines[-1].split(',')[-1]
    # Upload the log to shopfloor.
    self.UploadResultToShopfloor()
    self.assertEquals(final_result, 'PASS')

  def GetLogPath(self, timestamp, suffix):
    """Get the file path of Graphyte output files.

    To keep the output file for every DUT, we add serial number and timestamp to
    make the file name unique.
    """
    file_name = '%s_%s_%s' % (
        self._dut.info.mlb_serial_number, timestamp, suffix)
    # The log files are in the default log folder.
    return os.path.join(paths.GetLogRoot(), file_name)

  def FetchConfigFromShopfloor(self):
    """Fetch all config files from shopfloor.

    The Graphyte config file lists other needed files, such as port config, test
    plan, and DUT/instrument config file. Since we don't only need one config
    file, we fetch all config files at the shopfloor to local side.
    """
    if not self.args.enable_shopfloor:
      return

    self._ui.SetHTML(_MSG_FETCH_CONFIG, id=_ID_MSG_DIV)
    config_file_paths = self._shopfloor_proxy.ListParameters(
        os.path.join(self.args.shopfloor_parameter_dir, '*'))
    for file_path in config_file_paths:
      factory.console.info('Fetch config file from shopfloor: %s', file_path)
      content = self._shopfloor_proxy.GetParameter(file_path).data
      file_name = os.path.basename(file_path)
      with open(os.path.join(LOCAL_CONFIG_DIR, file_name), 'w') as f:
        f.write(content)

  def UploadResultToShopfloor(self):
    """Upload Graphyte log and result to shopfloor."""
    if not self.args.enable_shopfloor:
      return

    self._ui.SetHTML(_MSG_UPLOAD_RESULT, id=_ID_MSG_DIV)
    output_files = [self.result_file_path, self.log_file_path]
    factory.console.info('Upload the result to shopfloor: %s', output_files)
    shopfloor.UploadAuxLogs(output_files, True,
                            dir_name=self.args.shopfloor_log_dir)
