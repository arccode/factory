# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Uses HWID v3 to generate, encode, and verify the device's HWID.

Description
-----------
This test generates and verifies HWID of device under testing.

Test Procedure
--------------
This test does not require operator interaction.
When ``generate`` is ``True``, this test will do the following:

1. If ``enable_factory_server`` is ``True``, it downloads latest HWID database
   from Google Factory Server.
2. Probe components on the device, which is equivalent to executing
   ``hwid probe`` in shell.
3. Get device data from ``device_data`` module.
4. Generate HWID by command ``hwid generate --probed-results-file
   <probed-results> --device-info-file <device-info>
   [--run-vpd|--vpd-data-file <path>] --json-output``.
5. Verify generated HWID by ``hwid verify --probed-results-file <probed-results>
   --phase <phase> [--run-vpd|--vpd-data-file <path>]``.
6. Write HWID to GBB by ``hwid write <generated-hwid>``.

If ``generate`` is ``False``, then instead of running ``hwid generate`` in step
4, it will just use ``hwid read`` to read saved HWID from the device.  And step
6 will be skipped.

If ``vpd_data_file`` is set to a string of ``<path>``, the vpd-related
arguments for ``hwid`` tool will be ``--vpd-data-file <path>``; otherwise if
``run_vpd`` is ``True``, the vpd-related arguments for ``hwid`` tool will be
``--run-vpd``.  Note that ``run_vpd=True`` has no effect if ``vpd_data_file``
is set.

Dependency
----------
It requires ``yaml`` python module.

Examples
--------
To generate and verify HWID, add this to your test list::

  {
    "pytest_name": "hwid",
    "label": "Write HWID"
  }

If you are doing RMA, to allow ``deprecated`` components, you need to enable RMA
mode::

  {
    "pytest_name": "hwid",
    "label": "Write HWID",
    "args": {
      "rma_mode": true
    }
  }

New HWID with 'configless' format is still under testing.  To enable this
feature, set argument like this::

  {
    "pytest_name": "hwid",
    "label": "Write HWID",
    "args": {
      "enable_configless_fields": true
    }
  }
"""

import json
import logging
import os

import yaml

from cros.factory.device import device_utils
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.test import device_data
from cros.factory.test.i18n import _
from cros.factory.test.rules import phase
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test.utils import deploy_utils
from cros.factory.test.utils import update_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils

# If present, these files will override the project and probe results
# (for testing).
OVERRIDE_PROJECT_PATH = os.path.join(
    hwid_utils.GetDefaultDataPath(), 'OVERRIDE_PROJECT')
# OVERRIDE_PROBED_RESULTS should be generated with:
#    `hwid probe`
# to include all the VPD in it.
OVERRIDE_PROBED_RESULTS_PATH = os.path.join(
    hwid_utils.GetDefaultDataPath(), 'OVERRIDE_PROBED_RESULTS')


class HWIDV3Test(test_case.TestCase):
  """A test for generating and verifying HWID v3."""
  ARGS = [
      Arg('generate', bool,
          'Generate and write the HWID (if False, only verify it).',
          default=True),
      Arg('enable_factory_server', bool,
          'Update hwid data from factory server.',
          default=True),
      Arg('run_vpd', bool,
          'Run the `vpd` commandline tool to get the vpd data.',
          default=False),
      Arg('vpd_data_file', str,
          'Read the specified file to get the vpd data.',
          default=None),
      Arg('rma_mode', bool,
          'Enable rma_mode, do not check for deprecated components.',
          default=False),
      Arg('verify_checksum', bool,
          'Enable database checksum verification.',
          default=True),
      Arg('enable_configless_fields', bool,
          'Include the configless fields',
          default=False),
      Arg('include_brand_code', bool,
          'Include RLZ brand code',
          default=True),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.factory_tools = deploy_utils.CreateFactoryTools(self._dut)
    self.tmpdir = self._dut.temp.mktemp(is_dir=True, prefix='hwid')

  def tearDown(self):
    self._dut.Call(['rm', '-rf', self.tmpdir])

  def runTest(self):
    testlog.LogParam(name='phase', value=str(phase.GetPhase()))
    phase.AssertStartingAtPhase(
        phase.EVT,
        self.args.verify_checksum,
        'HWID checksum must be verified')

    if self.args.enable_factory_server:
      update_utils.UpdateHWIDDatabase(self._dut)

    self.ui.SetState(_('Probing components...'))
    # check if we are overriding probed results.
    probed_results_file = self._dut.path.join(self.tmpdir,
                                              'probed_results_file')
    if os.path.exists(OVERRIDE_PROBED_RESULTS_PATH):
      self._dut.SendFile(OVERRIDE_PROBED_RESULTS_PATH, probed_results_file)
      probed_results = file_utils.ReadFile(OVERRIDE_PROBED_RESULTS_PATH)
      testlog.LogParam(
          name='probed_results',
          value=probed_results)
      testlog.UpdateParam(
          name='probed_results',
          description='hwid probe result (overriden)')
    else:
      probed_results = self.factory_tools.CallOutput(['hwid', 'probe'])
      self._dut.WriteFile(probed_results_file, probed_results)
      testlog.LogParam(
          name='probed_results',
          value=probed_results)
      testlog.UpdateParam(
          name='probed_results',
          description='hwid probe result')

    # check if we are overriding the project name.
    if os.path.exists(OVERRIDE_PROJECT_PATH):
      with open(OVERRIDE_PROJECT_PATH) as f:
        project = f.read().strip()
      logging.info('overrided project name: %s', project)
      project_arg = ['--project', project.upper()]
    else:
      project_arg = []

    # pass device info to DUT
    device_info_file = self._dut.path.join(self.tmpdir, 'device_info')
    device_info = device_data.GetAllDeviceData()
    with file_utils.UnopenedTemporaryFile() as f:
      yaml.dump(device_info, open(f, 'w'))
      self._dut.SendFile(f, device_info_file)

    vpd_args = []
    if self.args.vpd_data_file:
      vpd_args += ['--vpd-data-file', self.args.vpd_data_file]
    elif self.args.run_vpd:
      vpd_args.append('--run-vpd')

    if self.args.generate:
      self.ui.SetState(_('Generating HWID (v3)...'))
      generate_cmd = ['hwid', 'generate',
                      '--probed-results-file', probed_results_file,
                      '--device-info-file', device_info_file,
                      '--json-output'] + project_arg + vpd_args
      if self.args.rma_mode:
        generate_cmd += ['--rma-mode']
      if not self.args.verify_checksum:
        generate_cmd += ['--no-verify-checksum']
      if self.args.enable_configless_fields:
        generate_cmd += ['--with-configless-fields']
      if not self.args.include_brand_code:
        generate_cmd += ['--no-brand-code']

      output = self.factory_tools.CallOutput(generate_cmd)
      self.assertIsNotNone(output, 'HWID generate failed.')
      hwid = json.loads(output)

      encoded_string = hwid['encoded_string']
      session.console.info('Generated HWID: %s', encoded_string)

      # try to decode HWID
      decode_cmd = ['hwid', 'decode'] + project_arg + [encoded_string]
      decoded_hwid = self.factory_tools.CallOutput(decode_cmd)
      self.assertIsNotNone(decoded_hwid, 'HWID decode failed.')

      logging.info('HWID Database checksum: %s', hwid['database_checksum'])

      testlog.LogParam(name='generated_hwid', value=encoded_string)
      testlog.LogParam(name='database_checksum',
                       value=hwid['database_checksum'])
      testlog.LogParam(name='decoded_hwid', value=decoded_hwid)

      device_data.UpdateDeviceData({'hwid': encoded_string})
    else:
      encoded_string = self.factory_tools.CheckOutput(['hwid', 'read']).strip()

    self.ui.SetState(
        _('Verifying HWID (v3): {encoded_string}...',
          encoded_string=(encoded_string or _('(unchanged)'))))

    verify_cmd = ['hwid', 'verify',
                  '--probed-results-file', probed_results_file,
                  '--phase', str(phase.GetPhase())] + project_arg + vpd_args
    if self.args.rma_mode:
      verify_cmd += ['--rma-mode']
    if not self.args.verify_checksum:
      verify_cmd += ['--no-verify-checksum']
    verify_cmd += [encoded_string]

    output = self.factory_tools.CheckOutput(verify_cmd)
    self.assertTrue('Verification passed.' in output)
    testlog.LogParam(name='verified_hwid', value=encoded_string)

    if self.args.generate:
      self.ui.SetState(
          _('Setting HWID (v3): {encoded_string}...',
            encoded_string=encoded_string))
      self.factory_tools.CheckCall(['hwid', 'write', encoded_string] +
                                   project_arg)
