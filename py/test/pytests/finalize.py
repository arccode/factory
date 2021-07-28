# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The finalize test is the last step before DUT switching to release image.

Description
-----------
The test invokes ``gooftool finalize`` with specified arguments to switch the
machine to shipping state, in following steps:

1. Run preflight tasks, including:

  a. Download HWID file from server if available.
  b. Log test states.
  c. Log image versions.

2. Call ``gooftool finalize``, which executes following sub commands in order:

  a. Verify firmware, keys, disk image, hardware components... etc. (equivalent
     to ``gooftool verify``)
  b. Clear manufacturing flags in firmware (equivalent to ``gooftool
     clear_gbb_flags``)
  c. Enable software write protect (equivalent to ``gooftool write_protect``)
  d. Start wiping process (equivalent to ``gooftool wipe_in_place``), which will
     do the following tasks:

    1. Wipe stateful partiton
    2. Enable release partition
    3. Notify factory server
    4. Battery cutoff

You can use ``gooftool_waive_list`` and ``gooftool_skip_list`` to waive or skip
some gooftool steps.

Test Procedure
--------------
When started, the pytest runs a few preflight tasks, to check configuration or
prepare logs.

After that, ``gooftool finalize`` will be called, and it will check device's
state, from hardware to software configuration.

If everything looks good (or waived, skipped by test arguments), ``gooftool``
will enable shipping mode by clearing firmware manufacturing flags, enabling
write protection, enabling release image, wiping out manufacturing disk data,
cutting off battery.

During battery cutoff, operator might be prompted to plug / unplug charger if
battery charge percentage is too low or too high.

Dependency
----------
Almost everything essential to Chrome OS, especially:

* crossystem (developer switch status, hardware WP status)
* battery driver (read battery percentage from sysfs)
* flashrom (to turn on software WP)
* TPM (read from sysfs)
* frecon (to show wipe progress and instructions)
* network connection (to notify factory server)
* clobber-state (/sbin/clobber-state, which wipes stateful partition)

Examples
--------
A minimum example should be::

  {
    "pytest_name": "finalize"
  }

Where,

* ``write_protection`` will be ``True`` for PVT phase, otherwise ``False``.
* ``enable_factory_server`` is ``True``, will try to connect to factory server
  and update HWID data, flush event logs.
* All gooftool verification rules are not skipped or waived.

For early builds (PROTO, EVT), you can skip things that are not ready::

  {
    "pytest_name": "finalize",
    "args": {
      "gooftool_skip_list": ["clear_gbb_flags"],
      "write_protection": false,
      "gooftool_waive_list": ["verify_tpm", "verify_hwid"]
    }
  }
"""


import json
import logging
import os
import random
import subprocess
import threading

import yaml

from cros.factory.device import device_utils
from cros.factory.device.links import ssh
from cros.factory.test import device_data
from cros.factory.test.env import paths
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test import gooftools
from cros.factory.test.i18n import _
from cros.factory.test.rules import phase
from cros.factory.test import server_proxy
from cros.factory.test import session
from cros.factory.test import state
from cros.factory.test import test_case
from cros.factory.test.utils import cbi_utils
from cros.factory.test.utils import deploy_utils
from cros.factory.test.utils import update_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


MSG_BUILD_PHASE = _('Build Phase')
MSG_WRITE_PROTECTION = _('Write Protection')
MSG_FACTORY_SERVER = _('Factory Server')
MSG_ENABLED = _('Enabled')
MSG_DISABLED = _('Disabled')
MSG_PREFLIGHT = _(
    'Running preflight tasks to prepare for finalization, please wait...')
MSG_FINALIZING = _('Finalizing, please wait.<br>'
                   'Do not restart the device or terminate this test,<br>'
                   'or the device may become unusable.')


class Finalize(test_case.TestCase):
  """The main class for finalize pytest."""
  ARGS = [
      Arg('write_protection', bool, 'Check and enable write protection.',
          default=None),
      Arg('has_ectool', bool, 'Has ectool utility or not.', default=True),
      Arg('secure_wipe', bool,
          'Wipe the stateful partition securely (False for a fast wipe).',
          default=True),
      Arg('upload_method', str, 'Upload method for "gooftool finalize"',
          default=None),
      Arg('upload_max_retry_times', int,
          'Number of tries to upload. 0 to retry infinitely.', default=0),
      Arg('upload_retry_interval', int,
          'Retry interval in seconds between retries.', default=None),
      Arg('upload_allow_fail', bool,
          ('Continue finalize if report upload fails, instead of raising error.'
          ), default=False),
      Arg('enable_factory_server', bool, (
          'Perform factory server operations: update HWID data and flush event '
          'logs.'), default=True),
      Arg('hwid_need_vpd', bool,
          'Whether the HWID validation process needs the vpd data.',
          default=False),
      Arg('rma_mode', bool,
          'Enable rma_mode, do not check for deprecated components.',
          default=False),
      Arg('mlb_mode', bool, 'Enable MLB mode, only do cr50 finalize.',
          default=False),
      Arg('is_cros_core', bool,
          'For ChromeOS Core device, skip setting firmware bitmap locale.',
          default=False),
      Arg('has_ec_pubkey', bool, 'Perform VerifyECKey.', default=None),
      Arg('enforced_release_channels', list,
          ('A list of string indicating the enforced release image channels. '
           'Each item should be one of "dev", "beta" or "stable".'),
          default=None),
      Arg('ec_pubkey_path', str,
          ('Path to public key in vb2 format. Verify EC key with pubkey file.'
           'Verify by pubkey file should have higher priority.'), default=None),
      Arg('ec_pubkey_hash', str,
          'A string for public key hash. Verify EC key with the given hash.',
          default=None),
      Arg('use_local_gooftool', bool,
          ('If DUT is local, use factory.par or local gooftool? If DUT is not '
           'local, factory.par is always used.'), default=True),
      Arg('station_ip', str, 'IP address of this station.', default=None),
      Arg('gooftool_waive_list', list,
          ('A list of waived checks for "gooftool finalize", '
           'see "gooftool finalize --help" for available items.'), default=[]),
      Arg('gooftool_skip_list', list,
          ('A list of skipped checks for "gooftool finalize", '
           'see "gooftool finalize --help" for available items.'), default=[]),
      Arg('enable_zero_touch', bool, 'Set SN bits to enable zero-touch.',
          default=False),
      Arg('cbi_eeprom_wp_status', cbi_utils.CbiEepromWpStatus,
          ('If set to "Locked", checks that CBI EEPROM write protection is '
           'enabled. If set to "Unlocked", checks that CBI EEPROM write '
           'protection is disabled. If set to "Absent", checks that CBI EEPROM '
           'is absent.'), default=cbi_utils.CbiEepromWpStatus.Locked),
      Arg('use_generic_tpm2', bool,
          ('Most Chromebooks are using Google security chips.  If this project '
           'is using a generic TPM (e.g. infineon), set this to true.  The '
           'steps in `cr50_finalize` will be adjusted'), default=False),
  ]

  FINALIZE_TIMEOUT = 180

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.force = False
    self.go_cond = threading.Condition()
    self.test_states_path = os.path.join(paths.DATA_LOG_DIR, 'test_states')
    self.factory_par = deploy_utils.CreateFactoryTools(self.dut)

    # variables for remote SSH DUT
    self.dut_response = None
    self.response_listener = None

  def tearDown(self):
    if self.response_listener:
      self.response_listener.shutdown()
      self.response_listener.server_close()
      self.response_listener = None

  def runTest(self):
    testlog.LogParam(name='phase', value=str(phase.GetPhase()))
    # TODO(hungte) Should we set a percentage of units to run WP on DVT?
    if self.args.write_protection is None:
      self.args.write_protection = phase.GetPhase() >= phase.PVT
    phase.AssertStartingAtPhase(phase.PVT, self.args.write_protection,
                                'Write protection must be enabled')
    if self.args.cbi_eeprom_wp_status != cbi_utils.CbiEepromWpStatus.Absent:
      phase.AssertStartingAtPhase(
          phase.PVT,
          self.args.cbi_eeprom_wp_status == cbi_utils.CbiEepromWpStatus.Locked,
          'CBI Write protection must be enabled')

    def GetState(v):
      return (['<b style="color: green;">', MSG_ENABLED, '</b>']
              if v else ['<b style="color: red;">', MSG_DISABLED, '</b>'])

    self.ui.SetInstruction([
        MSG_WRITE_PROTECTION, ': ',
        GetState(self.args.write_protection), '<br>', MSG_BUILD_PHASE,
        ': %s, ' % phase.GetPhase(), MSG_FACTORY_SERVER, ': ',
        GetState(self.args.enable_factory_server)
    ])
    self.ui.SetState(MSG_PREFLIGHT)
    self.Preflight()
    self.ui.SetState(MSG_FINALIZING)
    self.DoFinalize()

  def Preflight(self):
    # Check for HWID bundle update from factory server.
    if self.args.enable_factory_server:
      update_utils.UpdateHWIDDatabase(self.dut)
    self.LogTestStates()
    self.LogImageVersion()

  def LogTestStates(self):
    test_list = self.test_info.ReadTestList()
    test_states = test_list.AsDict(
        state.GetInstance().GetTestStates())
    file_utils.TryMakeDirs(os.path.dirname(self.test_states_path))
    with open(self.test_states_path, 'w') as f:
      yaml.dump(test_states, f)
    event_log.Log('test_states', test_states=test_states)
    testlog.LogParam('test_states', test_states)

  def LogImageVersion(self):
    release_image_version = self.dut.info.release_image_version
    factory_image_version = self.dut.info.factory_image_version
    if release_image_version:
      logging.info('release image version: %s', release_image_version)
    else:
      self.FailTask('Can not determine release image version')
    if factory_image_version:
      logging.info('factory image version: %s', factory_image_version)
    else:
      self.FailTask('Can not determine factory image version')
    event_log.Log('finalize_image_version',
                  factory_image_version=factory_image_version,
                  release_image_version=release_image_version)
    testlog.LogParam('factory_image_version', factory_image_version)
    testlog.LogParam('release_image_version', release_image_version)

  def _CallGoofTool(self, command):
    """Execute a gooftool command, `command`.

    Args:
      command: a string object which starts with 'gooftool '.
    """
    assert command.startswith('gooftool ')

    if self.dut.link.IsLocal() and self.args.use_local_gooftool:
      (out, unused_err, returncode) = gooftools.run(command)
      # since STDERR is logged, we only need to log STDOUT
      session.console.info('========= STDOUT ========')
      session.console.info(out)
    else:
      session.console.info('call factory.par: %s', command)
      session.console.info('=== STDOUT and STDERR ===')
      # append STDOUT and STDERR to console log.
      console_log_path = paths.CONSOLE_LOG_PATH
      file_utils.TryMakeDirs(os.path.dirname(console_log_path))
      with open(console_log_path, 'a') as output:
        returncode = self.factory_par.Call(command, stdout=output,
                                           stderr=subprocess.STDOUT)
    session.console.info('=========================')
    session.console.info('return code: %d', returncode)
    return returncode == 0

  def Warn(self, message, times=3):
    """Alerts user that a required test is bypassed."""
    for i in range(times, 0, -1):
      session.console.warn(
          '%s. '
          'THIS DEVICE CANNOT BE QUALIFIED. '
          '(will continue in %d seconds)', message, i)
      self.Sleep(1)

  def NormalizeUploadMethod(self, method):
    """Builds the report file name and resolves variables."""
    if method in [None, 'none']:
      # gooftool accepts only 'none', not empty string.
      return 'none'

    if method == 'shopfloor':
      method = 'shopfloor:%s#%s' % (server_proxy.GetServerURL(),
                                    device_data.GetSerialNumber())
    logging.info('Using upload method %s', method)

    return method

  def DoFinalize(self):
    upload_method = self.NormalizeUploadMethod(self.args.upload_method)

    command = 'gooftool -v 4 finalize'

    if self.args.enable_factory_server:
      state.GetInstance().FlushEventLogs()

    if not self.args.write_protection:
      self.Warn('WRITE PROTECTION IS DISABLED.')
      command += ' --no_write_protect'
    command += ' --cbi_eeprom_wp_status %s' % self.args.cbi_eeprom_wp_status

    if self.args.use_generic_tpm2:
      command += ' --use_generic_tpm2'

    if not self.args.has_ectool:
      command += ' --no_ectool'
    if not self.args.secure_wipe:
      command += ' --fast'

    if self.args.enable_factory_server:
      server_url = server_proxy.GetServerURL()
      if server_url:
        command += ' --shopfloor_url "%s"' % server_url

    command += ' --upload_method "%s"' % upload_method
    if self.args.upload_max_retry_times:
      command += ' --upload_max_retry_times %s' % (
          self.args.upload_max_retry_times)
    if self.args.upload_retry_interval is not None:
      command += ' --upload_retry_interval %s' % self.args.upload_retry_interval
    if self.args.upload_allow_fail:
      command += ' --upload_allow_fail'
    command += ' --add_file "%s"' % self.test_states_path
    if self.args.hwid_need_vpd:
      command += ' --hwid-run-vpd'
    if self.args.rma_mode:
      command += ' --rma_mode'
      logging.info('Using RMA mode. Accept deprecated components')
    if self.args.mlb_mode:
      command += ' --mlb_mode'
      logging.info('Using MLB mode. Only do cr50 finalize')
    if self.args.is_cros_core:
      command += ' --cros_core'
      logging.info('ChromeOS Core device. Skip some check.')
    if self.args.has_ec_pubkey:
      command += ' --has_ec_pubkey'
      logging.info('Device has EC public key for EFS and need to verify it.')
    if self.args.enforced_release_channels:
      command += ' --enforced_release_channels %s' % (
          ' '.join(self.args.enforced_release_channels))
      logging.info(
          'Enforced release channels: %s.', self.args.enforced_release_channels)
    if self.args.ec_pubkey_path:
      command += ' --ec_pubkey_path %s' % self.args.ec_pubkey_path
    elif self.args.ec_pubkey_hash:
      command += ' --ec_pubkey_hash %s' % self.args.ec_pubkey_hash
    if self.args.gooftool_waive_list:
      command += ' --waive_list ' + ' '.join(self.args.gooftool_waive_list)
    if self.args.gooftool_skip_list:
      command += ' --skip_list ' + ' '.join(self.args.gooftool_skip_list)
    if self.args.enable_zero_touch:
      command += ' --enable_zero_touch'
    command += ' --phase "%s"' % phase.GetPhase()

    self._FinalizeWipeInPlace(command)

  def _FinalizeWipeInPlace(self, command):
    if self.dut.link.IsLocal():
      self._CallGoofTool(command)
      # Wipe-in-place will terminate all processes that are using stateful
      # partition, this test should be killed at here.
      self.Sleep(self.FINALIZE_TIMEOUT)
      raise type_utils.TestFailure('DUT Failed to finalize in %d seconds' %
                                   self.FINALIZE_TIMEOUT)
    if isinstance(self.dut.link, ssh.SSHLink):
      # For remote SSH DUT, we ask DUT to send wipe log back.
      self._FinalizeRemoteSSHDUT(command)
    else:
      # For other remote links, we only checks if it has lost connection in
      # @self.FINALIZE_TIMEOUT seconds
      self._CallGoofTool(command)
      try:
        sync_utils.WaitFor(lambda: not self.dut.IsReady(),
                           self.FINALIZE_TIMEOUT,
                           poll_interval=1)
      except type_utils.TimeoutError:
        raise type_utils.TestFailure(
            'Remote DUT failed to finalize in %d seconds' %
            self.FINALIZE_TIMEOUT)

  def _FinalizeRemoteSSHDUT(self, command):
    # generate a random token, so the response is different for every DUT.
    token = "{:016x}".format(random.getrandbits(64))

    dut_finished = threading.Event()
    self.dut_response = None

    def _Callback(handler):
      """Receive and verify DUT message.

      Args:
        :type handler: socketserver.StreamRequestHandler
      """
      try:
        dut_response = json.loads(handler.rfile.readline())
        if dut_response['token'] == token:
          self.dut_response = dut_response
          dut_finished.set()
        # otherwise, the reponse is invalid, just ignore it
      except Exception:
        pass

    # Start response listener
    self.response_listener = net_utils.CallbackSocketServer(_Callback)
    server_thread = threading.Thread(
        target=self.response_listener.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # If station IP is not given, we assume that this station is the first host
    # in the subnet, and number of prefix bits in this subnet is 24.
    station_ip = (self.args.station_ip or
                  net_utils.CIDR(str(self.dut.link.host), 24).SelectIP(1))
    command += ' --station_ip "%s"' % station_ip
    command += ' --station_port %d' % self.response_listener.server_address[1]
    command += ' --wipe_finish_token "%s"' % token

    if not self._CallGoofTool(command):
      raise type_utils.TestFailure('finalize command failed')

    session.console.info('wait DUT to finish wiping')

    if not dut_finished.wait(self.FINALIZE_TIMEOUT):
      raise type_utils.TestFailure(
          'Remote DUT not response in %d seconds' % self.FINALIZE_TIMEOUT)

    # save log files in test data directory
    output_dir = os.path.join(
        paths.DATA_TESTS_DIR, session.GetCurrentTestPath())
    with open(os.path.join(output_dir, 'wipe_in_tmpfs.log'), 'w') as f:
      f.write(self.dut_response.get('wipe_in_tmpfs_log', ''))
    with open(os.path.join(output_dir, 'wipe_init.log'), 'w') as f:
      f.write(self.dut_response.get('wipe_init_log', ''))

    self.assertTrue(self.dut_response['success'])
