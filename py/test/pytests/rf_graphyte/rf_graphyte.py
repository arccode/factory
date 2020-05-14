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

1. (Optional) Use pytest ``retrieve parameter`` to fetch the config files from
   the Chrome OS factory server.
2. Start running Graphyte framework with the assigned config file.
3. Parse the result and upload them via testlog.

Dependency
----------
Need Graphyte framework with DUT and instrument plugins. This can be easily done
by deploying a RF bundle. First, you need to make a RF bundle as follows.

.. code-block:: bash

   # Inside Chromium chroot
   cros_workon --board <board> start graphyte-<board>
   emerge-<board> graphyte-<board>
   ls /build/<board>/var/lib/graphyte/rf_bundle_*.tar.gz

This will generate the RF bundle named ``rf_bundle_*.tar.gz``. Copy this to
target machine, and install Graphyte by:

.. code-block:: bash

   mkdir -p /tmp/graphyte
   cd /tmp/graphyte
   tar xvf /path/to/rf_bundle_xxx.tar.gz
   ./install_graphyte.sh
   # Choose (Y) to install Graphyte to another folder
   # Press (Enter) to install Graphyte to /usr/local
   rm -rf /tmp/graphyte

Examples
--------
To run Graphyte framework with the config file `conductive_config.json`, add
this in test list::

  {
    "pytest_name": "rf_graphyte.rf_graphyte",
    "args": {
      "graphyte_config_file": "conductive_config.json",
      "verbose": true
    }
  }
"""

import csv
import json
import logging
import os
import time

from cros.factory.device import device_utils
from cros.factory.test import device_data
from cros.factory.test.env import paths
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg


# The Graphyte config files (pathloss, test plan, port config) should be placed
# in the config_files folder in Graphyte framework.
RELATIVE_CONFIG_DIR = 'config_files/'
# The log files are in the default log folder.
RESULT_FILENAME = 'graphyte_result.csv'
LOG_FILENAME = 'graphyte.log'


class RFGraphyteTest(test_case.TestCase):

  ARGS = [
      Arg('graphyte_package', str,
          'Path to Graphyte package folder',
          default='/usr/local/graphyte/'),
      Arg('graphyte_config_file', str,
          'Path to Graphyte config file. This is passed to `config-file` '
          'parameter to Graphyte framework.'),
      Arg('patch_dhcp_ssh_dut_ip', bool,
          'Set to True if Goofy uses SSH link with DHCP enabled to connect to '
          "DUT. This will patch the IP from Goofy's link into Graphyte's "
          'target DUT IP configuration.',
          default=False),
      Arg('verbose', bool, 'Enable Graphyte debug logging',
          default=True),
  ]

  ui_class = test_ui.ScrollableLogUI

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()

    timestamp = time.strftime('%H%M%S')
    self.config_dir = os.path.join(self.args.graphyte_package,
                                   RELATIVE_CONFIG_DIR)
    self.config_file_path = os.path.join(self.config_dir,
                                         self.args.graphyte_config_file)
    self.result_file_path = self.GetLogPath(timestamp, RESULT_FILENAME)
    self.log_file_path = self.GetLogPath(timestamp, LOG_FILENAME)

    # Group checker for Testlog.
    self.group_checker = testlog.GroupParam(
        'result',
        ['rf_type', 'component_name', 'test_type', 'center_freq',
         'result_name', 'power_level', 'result', 'extra_fields'])
    testlog.UpdateParam('rf_type', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('component_name',
                        param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('test_type', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('center_freq', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('result_name', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('power_level', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('extra_fields', param_type=testlog.PARAM_TYPE.argument)


  def runTest(self):
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
    self.ui.SetInstruction(_('Executing Graphyte'))
    cmd = [os.path.join(self.args.graphyte_package, "main.py"),
           '--config-file', self.config_file_path,
           '--result-file', self.result_file_path,
           '--log-file', self.log_file_path]
    if self.args.verbose:
      cmd.append('-v')
    session.console.info('Call the Graphyte command: %s', ' '.join(cmd))
    return_value = self.ui.PipeProcessOutputToUI(cmd)

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

    # Fail if return_value is not zero.
    if return_value:
      self.fail('Graphyte ended abnormally.')

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
    self.assertEqual(final_result, 'PASS')

  def GetLogPath(self, timestamp, suffix):
    """Get the file path of Graphyte output files.

    To keep the output file for every DUT, we add serial number and timestamp to
    make the file name unique.
    """
    mlb_serial_number = device_data.GetAllSerialNumbers().get(
        'mlb_serial_number', 'unknown')
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

        parameters = ParseGraphyteArguments(data['test_item'])
        parameters['result_name'] = data['result_name']
        parameters['power_level'] = _ConvertToNumber(data['power_level'])
        result_value = _ConvertToNumber(data['result'])
        if result_value is None:
          code = 'GraphyteResultMissing'
          details = '%s result is missing.' % json.dumps(parameters)
          testlog.AddFailure(code=code, details=details)
        else:
          with self.group_checker:
            testlog.CheckNumericParam(
                name='result', value=result_value,
                min=_ConvertToNumber(data['lower_bound']),
                max=_ConvertToNumber(data['upper_bound']))
            for k, v in parameters.items():
              testlog.LogParam(k, v)


def ParseGraphyteArguments(test_item):
  """Parse the test arguments from the test items."""
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

  items = list(map(_ConvertDataType, test_item.split(' ')))
  common_fields = ['rf_type', 'component_name', 'test_type', 'center_freq']
  if items[0] == 'WLAN':
    extra_fields = ['standard', 'data_rate', 'bandwidth', 'chain_mask']
  elif items[0] == 'BLUETOOTH':
    extra_fields = ['packet_type']
  elif items[0] == '802_15_4':
    extra_fields = []
  else:
    logging.error('Should not be here. items: %s', items)
  if (len(items[:4]) != len(common_fields) or
      len(items[4:]) != len(extra_fields)):
    raise ValueError('items %s, fields %s' %
                     (items, common_fields + extra_fields))

  arguments = dict(zip(common_fields, items[:4]))
  arguments['extra_fields'] = dict(zip(extra_fields, items[4:]))

  return arguments
