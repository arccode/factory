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
2. Collect materials (including probed results, device data, and optionally
   the vpd data) from DUT for generating the HWID string.  This step is
   equivalent to executing ``hwid collect-material`` in shell.
3. Generate HWID by command ``hwid generate --probed-results-file
   <probed-results> --material-file <hwid-material-file> --json-output``.
4. Verify generated HWID by ``hwid verify --material-file <hwid-material-file>
   --phase <phase>``.
5. Write HWID to GBB by ``hwid write <generated-hwid>``.

If ``generate`` is ``False``, then instead of running ``hwid generate`` in step
3, it will just use ``hwid read`` to read saved HWID from the device.  And step
5 will be skipped.

If ``vpd_data_file`` is set to a string of ``<path>``, the vpd-related
arguments for ``hwid`` tool will be ``--vpd-data-file <path>``; otherwise if
``run_vpd`` is ``True``, the vpd-related arguments for ``hwid`` tool will be
``--run-vpd``.  Note that ``run_vpd=True`` has no effect if ``vpd_data_file``
is set.

Dependency
----------
Various of system utilities like ``vpd`` and ``flashrom`` will be invoked to
grab materials from DUT.

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

import yaml

from cros.factory.device import device_utils
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


class HWIDV3Test(test_case.TestCase):
  """A test for generating and verifying HWID v3."""
  ARGS = [
      Arg('generate', bool,
          'Generate and write the HWID (if False, only verify it).',
          default=True),
      Arg('enable_factory_server', bool,
          'Update hwid data from factory server.', default=True),
      Arg('run_vpd', bool,
          'Run the `vpd` commandline tool to get the vpd data.', default=False),
      Arg('vpd_data_file', str, 'Read the specified file to get the vpd data.',
          default=None),
      Arg('rma_mode', bool,
          'Enable rma_mode, do not check for deprecated components.',
          default=False),
      Arg('verify_checksum', bool, 'Enable database checksum verification.',
          default=True),
      Arg('enable_configless_fields', bool, 'Include the configless fields',
          default=False),
      Arg('include_brand_code', bool, 'Include RLZ brand code', default=True),
  ]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    self.factory_tools = deploy_utils.CreateFactoryTools(self._dut)
    self.tmpdir = self._dut.temp.mktemp(is_dir=True, prefix='hwid')

  def tearDown(self):
    self._dut.Call(['rm', '-rf', self.tmpdir])

  def runTest(self):
    testlog.LogParam(name='phase', value=str(phase.GetPhase()))
    phase.AssertStartingAtPhase(phase.EVT, self.args.verify_checksum,
                                'HWID checksum must be verified')

    if self.args.enable_factory_server:
      update_utils.UpdateHWIDDatabase(self._dut)

    self.ui.SetState(_('Collecting DUT materials...'))
    collect_material_cmd = ['hwid', 'collect-material']

    # pass device info to DUT
    device_info_file = self._dut.path.join(self.tmpdir, 'device_info')
    device_info = device_data.GetAllDeviceData()
    with file_utils.UnopenedTemporaryFile() as f:
      yaml.dump(device_info, open(f, 'w'))
      self._dut.SendFile(f, device_info_file)

    collect_material_cmd.extend(['--device-info-file', device_info_file])
    if self.args.vpd_data_file:
      collect_material_cmd.extend(['--vpd-data-file', self.args.vpd_data_file])
    if self.args.run_vpd:
      collect_material_cmd.append('--run-vpd')

    hwid_material_file = self._dut.path.join(self.tmpdir, 'hwid_material_file')
    hwid_material = self.factory_tools.CallOutput(collect_material_cmd)
    self._dut.WriteFile(hwid_material_file, hwid_material)
    testlog.LogParam(name='hwid_material', value=hwid_material)
    testlog.UpdateParam(name='hwid_material',
                        description='materials to generate HWID string')

    if self.args.generate:
      self.ui.SetState(_('Generating HWID (v3)...'))
      generate_cmd = [
          'hwid', 'generate', '--material-file', hwid_material_file,
          '--json-output'
      ]
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
      decode_cmd = ['hwid', 'decode'] + [encoded_string]
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

    verify_cmd = [
        'hwid', 'verify', '--material-file', hwid_material_file, '--phase',
        str(phase.GetPhase())
    ]
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
      self.factory_tools.CheckCall(['hwid', 'write', encoded_string])
