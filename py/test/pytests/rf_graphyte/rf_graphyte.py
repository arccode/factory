# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests RF chip's transmitting and receiving capabilities using Graphyte.

Description
-----------
A station-based test using
`Graphyte framework <https://chromium.googlesource.com/chromiumos/graphyte/>`_
to validate RF chip's transmitting and receiving capabilities in conductive or
radiated way. Currently it supports WLAN, Bluetooth, and 802.15.4 technologies.

Graphyte is a RF testing framework that runs on Linux and ChromeOS, and
provide a unified RF testing way for each product in Google. It contains three
parts: Graphyte framework, DUT plugin and instrument plugin.

Test Procedure
--------------
This is an automated test without user interaction.

1. If the argument `enable_factory_server` is True, fetch the config files from
   the Chrome OS factory server. The folder name is assigned by the argument
   `server_parameter_dir`.
2. Start running Graphyte framework with the assigned config file.
3. Parse the result and upload them via testlog.

Dependency
----------
- Python pip package
- `Graphyte framework <https://chromium.googlesource.com/chromiumos/graphyte/>`_
- Graphyte plugins for the target DUT and test instrument.

Examples
--------
To run Graphyte framework with the config file `conductive_config.json`, add
this in test list::

  {
    "pytest_name": "rf_graphyte",
    "args": {
      "graphyte_config_file": "conductive_config.json",
      "server_parameter_dir": "rf_conductive",
      "enable_factory_server": true,
      "verbose": true
    }
  }
"""

import csv
import json
import logging
import os
import subprocess
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test.env import paths
from cros.factory.test import factory
from cros.factory.test.i18n import test_ui as i18n_test_ui
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg


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

_MSG_FETCH_CONFIG = i18n_test_ui.MakeI18nLabelWithClass(
    'Fetching config files from factory server', 'message')
_MSG_EXECUTE_GRAPHYTE = i18n_test_ui.MakeI18nLabelWithClass(
    'Executing Graphyte', 'message')

class RFGraphyteTest(unittest.TestCase):

  ARGS = [
      Arg('graphyte_config_file', str,
          'Path to Graphyte config file. This is interpreted as the path '
          'relative to `test/pytests/rf_graphyte` folder.',
          optional=False),
      Arg('patch_dhcp_ssh_dut_ip', bool,
          'Set to True if Goofy uses SSH link with DHCP enabled to connect to '
          "DUT. This will patch the IP from Goofy's link into Graphyte's "
          'target DUT IP configuration.',
          default=False, optional=True),
      Arg('verbose', bool, 'Enable Graphyte debug logging',
          default=True, optional=True),
      Arg('enable_factory_server', bool,
          'Whether or not to use Chrome OS factory server. '
          'If True, the test will try to update config files from server, '
          'and upload the log and result file to factory server. '
          'If False, load config file from local disk and does not upload log.',
          default=True, optional=False),
      Arg('server_parameter_dir', str,
          'Directory in which to place the updated config files. All the files '
          'in this folder will be downloaded to `test/pytests/rf_graphyte` '
          'folder if argument "enable_factory_server" is True.',
          default='rf_graphyte', optional=True),
      ]

  def setUp(self):
    self._ui = test_ui.UI()
    self._ui.AppendCSS(_CSS)
    self._template = ui_templates.OneSection(self._ui)
    self._template.SetState(_STATE_HTML)
    self._dut = device_utils.CreateDUTInterface()
    self.process = None
    if self.args.enable_factory_server:
      self._server_proxy = server_proxy.GetServerProxy()

    timestamp = time.strftime('%H%M%S')
    self.config_file_path = os.path.join(
        LOCAL_CONFIG_DIR, self.args.graphyte_config_file)
    self.result_file_path = self.GetLogPath(timestamp, RESULT_FILENAME)
    self.log_file_path = self.GetLogPath(timestamp, LOG_FILENAME)

  def tearDown(self):
    if self.process:
      logging.info('Graphyte process still exists, kill the process (pid: %s).',
                   self.process.pid)
      self.process.kill()

  def runTest(self):
    self._ui.RunInBackground(self._runTest)
    self._ui.Run()

  def _runTest(self):
    # Update the config file from factory server.
    self.FetchConfigFromFactoryServer()

    # Check the config file exists.
    if not os.path.exists(self.config_file_path):
      self.fail('Graphyte config file %s does not exist.' %
                self.config_file_path)

    # Patch the DUT config with DHCP IP.
    if self.args.patch_dhcp_ssh_dut_ip:
      self.PatchSSHLinkConfig()

    testlog.AttachFile(
        path=self.config_file_path,
        mime_type='application/json',
        name='graphyte_config.json',
        description=os.path.basename(self.config_file_path),
        delete=False)

    # Execute Graphyte.
    self._ui.SetHTML(_MSG_EXECUTE_GRAPHYTE, id=_ID_MSG_DIV)
    cmd = ['python', '-m', 'graphyte.main',
           '--config-file', self.config_file_path,
           '--result-file', self.result_file_path,
           '--log-file', self.log_file_path]
    if self.args.verbose:
      cmd.append('-v')
    session.console.info('Call the Graphyte command: %s', ' '.join(cmd))
    self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE)

    # Output to UI
    debug_str = ''
    while True:
      line = self.process.stdout.readline()
      if not line:
        break
      # Keep 8Kb data.
      debug_str = (test_ui.Escape(line) + debug_str)[:8 * 1024]
      self._ui.SetHTML(debug_str, id=_ID_DEBUG_DIV)
    self.process = None

    # Save the log file.
    if os.path.exists(self.log_file_path):
      testlog.AttachFile(
          path=self.log_file_path,
          mime_type='text/plain',
          name='graphyte.log',
          description=os.path.basename(self.log_file_path),
          delete=False)

    # Save the result file.
    if os.path.exists(self.result_file_path):
      testlog.AttachFile(
          path=self.result_file_path,
          mime_type='text/csv',
          name='graphyte_result.csv',
          description=os.path.basename(self.result_file_path),
          delete=False)

    # Parse result file.
    if not os.path.exists(self.result_file_path):
      self.fail('Result file is not found.')
    with open(self.result_file_path) as result_file:
      result_data = result_file.read()
      logging.debug('Graphyte result: %s', result_data)
      session.console.info('Graphyte result:\n%s', result_data)
      failed_results = [result for result in result_data.splitlines()
                        if 'FAIL' in result]
      if failed_results:
        session.console.error('Failed result:\n%s', '\n'.join(failed_results))

    # Upload the log by testlog.
    try:
      self.SaveParamsToTestlog()
    except Exception as e:
      logging.exception(e)
      logging.error('Error saving params to testlog: %s: %s',
                    e.__class__.__name__, e)

    # Total test result is at the last column of the last row.
    result_lines = result_data.splitlines()
    try:
      final_result = result_lines[-1].split(',')[-1]
    except Exception as e:
      logging.exception(e)
      self.fail('Corrupt or incomplete result file %s: %s: %s'
                % (self.result_file_path, e.__class__.__name__, e))

    # Pass or fail the pytest.
    self.assertEquals(final_result, 'PASS')

  def GetLogPath(self, timestamp, suffix):
    """Get the file path of Graphyte output files.

    To keep the output file for every DUT, we add serial number and timestamp to
    make the file name unique.
    """
    # Workaround: Get the serial number without InfoProperty.
    # https://bugs.chromium.org/p/chromium/issues/detail?id=707200
    # Revert it after the issue is resolved.
    mlb_serial_number = self._dut.vpd.ro.get('mlb_serial_number', 'unknown')
    file_name = '%s_%s_%s' % (
        mlb_serial_number, timestamp, suffix)
    # save the log under /var/factory/tests/<TestID>-<UUID>/
    current_test_dir = os.path.join(
        paths.DATA_TESTS_DIR, session.GetCurrentTestPath())
    return os.path.join(current_test_dir, file_name)

  def PatchSSHLinkConfig(self):
    """Patch the DHCP IP in the DUT config.

    The DUT config might be in three places: device default config, overridden
    config file, overridden config in the global config file. Since the last one
    will override the previous config, we directly patch the DHCP IP in the
    global config file. Please refer "Graphyte Use Manual" for detail.
    """
    with open(self.config_file_path, 'r') as f:
      global_config = json.load(f)

    # Override DUT link IP in the global config file.
    global_config.setdefault('dut_config', {})
    global_config['dut_config'].setdefault('link_options', {})
    global_config['dut_config']['link_options']['host'] = self._dut.link.host

    # Write the patched config into new config file.
    self.config_file_path += '.patched'
    with open(self.config_file_path, 'w') as f:
      json.dump(global_config, f)

  def FetchConfigFromFactoryServer(self):
    """Fetch all config files from factory server.

    The Graphyte config file lists other needed files, such as port config, test
    plan, and DUT/instrument config file. Since we don't only need one config
    file, we fetch all config files from the factory server to local side.
    """
    if not self.args.enable_factory_server:
      return

    self._ui.SetHTML(_MSG_FETCH_CONFIG, id=_ID_MSG_DIV)
    config_file_paths = self._server_proxy.ListParameters(
        os.path.join(self.args.server_parameter_dir, '*'))
    for file_path in config_file_paths:
      session.console.info('Fetch config file from server: %s', file_path)
      content = self._server_proxy.GetParameter(file_path).data
      file_name = os.path.basename(file_path)
      with open(os.path.join(LOCAL_CONFIG_DIR, file_name), 'w') as f:
        f.write(content)

  def SaveParamsToTestlog(self):
    def _ConvertToNumber(value):
      """Convert the string to a number or None."""
      try:
        return float(value)
      except ValueError:
        return None

    with open(self.result_file_path, 'r') as f:
      for data in csv.DictReader(f):
        if data['test_item'] == 'TOTAL RESULT':
          continue

        parameters = ParseGraphyteTestName(data['test_item'])
        parameters['result_name'] = data['result_name']
        parameters['power_level'] = _ConvertToNumber(data['power_level'])
        test_name = json.dumps(parameters)
        result_value = _ConvertToNumber(data['result'])
        if result_value is None:
          code = 'GraphyteResultMissing'
          details = '%s result is missing.' % test_name
          testlog.AddFailure(code=code, details=details)
        else:
          try:
            testlog.CheckParam(name=test_name,
                               value=result_value,
                               min=_ConvertToNumber(data['lower_bound']),
                               max=_ConvertToNumber(data['upper_bound']))
          except Exception as e:
            logging.exception(e)
            logging.error('Could not run CheckParam for data=%r: %s: %s',
                          data, e.__class__.__name__, e)


def ParseGraphyteTestName(test_name):
  """Parse the test arguments from the test name."""
  def _ConvertDataType(value_str):
    if value_str in ['', 'None', 'none']:
      return None
    try:
      return int(value_str)
    except ValueError:
      pass
    try:
      return float(value_str)
    except ValueError:
      pass
    return value_str

  items = map(_ConvertDataType, test_name.split(' '))
  if items[0] == 'WLAN':
    fields = ['rf_type', 'component_name', 'test_type', 'center_freq',
              'standard', 'data_rate', 'bandwidth', 'chain_mask']
  elif items[0] == 'BLUETOOTH':
    fields = ['rf_type', 'component_name', 'test_type', 'center_freq',
              'packet_type']
  elif items[0] == '802_15_4':
    fields = ['rf_type', 'component_name', 'test_type', 'center_freq']
  else:
    logging.error('Should not be here. items: %s', items)
  assert len(items) == len(fields), 'items %s, fields %s' % (items, fields)
  return dict(zip(fields, items))
