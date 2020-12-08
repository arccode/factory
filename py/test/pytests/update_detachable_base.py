# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Detachable base update test

Description
-----------
For detachable projects, the detachable base (as a USB device) may need to be
updated with its standalone EC and touchpad firmware.
This test leverages ``hammerd``, which is the dedicated daemon for updating
detachable base firmware, to help factory automize firmware update and basic
verification.

Test Procedure
--------------
1. Test will try to locate detachable base with the given USB device info.
   If the info is not provided from test lists, the test will try to get it
   from ``cros_config``.
2. Hammerd is invoked to update base's EC and touch firmware.
3. Verify base is properly updated by probing base info and doing some
   preliminary checkings.

Note that one might want to disable hammerd being inited on boot by configuring
upstart. See `here
<https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/init/preinit.d/inhibit_jobs/README.md>`_
for detail.

In addition, it's recommended to configure detachable base info in
chromeos-config (instead of test lists) with following properties provided:

- ec-image-name
- touch-image-name
- vendor-id
- product-id
- usb-path

So that the it can be maintained in the standalone config and be easily shared
across the system.

Dependency
----------
- chromeos_config (cros_config)
- hammerd
- usb_updater2

Examples
--------
If detachable base information is ready in cros_config::

  {
    "pytest_name": "update_detachable_base"
  }

If explicitly supplying detachable base info (Krane for example)::

  {
    "pytest_name": "update_detachable_base",
    "args": {
      "usb_path": "1-1.1",
      "product_id": 20540,
      "vendor_id": 6353,
      "ec_image_path": "/lib/firmware/masterball.fw",
      "touchpad_image_path": "/lib/firmware/masterball-touch.fw"
    }
  }
"""

import logging
import os
import re
import time

from cros.factory.device import device_utils
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils

BASE_FW_DIR = '/lib/firmware'

ELAN_VENDOR_ID = 0x04f3
ST_VENDOR_ID = 0x0483
VENDOR_IDS = (ELAN_VENDOR_ID, ST_VENDOR_ID)

class UpdateDetachableBaseTest(test_case.TestCase):
  ARGS = [
      Arg('usb_path', str, 'USB path for searching the detachable base.',
          default=None),
      Arg('product_id', int, 'Product ID of the USB device.',
          default=None),
      Arg('vendor_id', int, 'Vendor ID of the USB device.',
          default=None),
      Arg('ec_image_path', str,
          'Path to the EC firmware image file under %s.' % BASE_FW_DIR,
          default=None),
      Arg('touchpad_image_path', str,
          'Path to the touchpad image file under %s.' % BASE_FW_DIR,
          default=None),
      Arg('update', bool,
          'Update detachable base FW (hammerd is needed)',
          default=True),
      Arg('verify', bool,
          'Verify base info after FW update. (usb_updater2 is needed)',
          default=True),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()
    self.ui.ToggleTemplateClass('font-large', True)

    # Read preconfigured values from cros_config if args are not provided.
    if self.args.usb_path is None:
      self.args.usb_path = self.CrosConfig('usb-path')
    if self.args.product_id is None:
      self.args.product_id = int(self.CrosConfig('product-id'))
    if self.args.vendor_id is None:
      self.args.vendor_id = int(self.CrosConfig('vendor-id'))
    if self.args.ec_image_path is None:
      self.args.ec_image_path = os.path.join(
          BASE_FW_DIR, self.CrosConfig('ec-image-name'))
    if self.args.touchpad_image_path is None:
      self.args.touchpad_image_path = os.path.join(
          BASE_FW_DIR, self.CrosConfig('touch-image-name'))

    self.device_id = '{:04x}:{:04x}'.format(self.args.vendor_id,
                                            self.args.product_id)
    self.usb_info = UsbInfo(self.device_id)

  def runTest(self):
    self.ui.SetState(_('Please connect the detachable base.'))
    sync_utils.PollForCondition(poll_method=self.BaseIsReady,
                                timeout_secs=60,
                                poll_interval_secs=1)

    if self.args.update:
      self.ui.SetState(_('Updating base firmware. Do not remove the base.'))
      self.UpdateDetachableBase()
      session.console.info('Base firmware update done.')

    if self.args.verify:
      self.ui.SetState(_('Verifying detachable base information...'))
      # Sleep for a while, because usb_updater2 may not be able to read
      # touchpad info right after FW is flashed.
      self.Sleep(3)

      # Getting info of touchpad on base / EC on base / target EC image
      # respectively.  b/146536191: Must query touchpad info before base EC
      # info.
      tp_info = self.usb_info.GetTouchpadInfo()
      ec_info = self.usb_info.GetBaseInfo()
      fw_info = self.usb_info.GetFirmwareInfo(self.args.ec_image_path)

      self.VerifyBaseInfo(ec=ec_info, tp=tp_info, fw=fw_info)
      session.console.info('Detachable base verification done.')

  @staticmethod
  def CrosConfig(key):
    """Helper method for cros_config key retrieval.

    Args:
      key: The key under detachable-base path.

    Returns:
      The value of the provided key.
    """
    return process_utils.LogAndCheckOutput(
        ['cros_config', '/detachable-base', key])

  def UpdateDetachableBase(self):
    """Main update method which calls hammerd to do base FW update.

    Raises:
      CalledProcessError if hammerd returns non-zero code.
    """
    minijail0_cmd = ['/sbin/minijail0', '-e', '-N', '-p', '-l',
                     '-u', 'hammerd', '-g', 'hammerd', '-c', '0002']
    hammerd_cmd = ['/usr/bin/hammerd',
                   '--at_boot=true',
                   '--force_inject_entropy=true',
                   '--update_if=always',
                   '--product_id=%d' % self.args.product_id,
                   '--vendor_id=%d' % self.args.vendor_id,
                   '--usb_path=%s' % self.args.usb_path,
                   '--ec_image_path=%s' % self.args.ec_image_path,
                   '--touchpad_image_path=%s' % self.args.touchpad_image_path]

    try:
      process_utils.Spawn(minijail0_cmd + hammerd_cmd,
                          log=True, check_call=True)
    except process_utils.CalledProcessError as e:
      # Note that hammerd prints log to stderr by default so reading stdout
      # does not help.
      # In addition, hammerd only prints log when stdin is a tty, so we can not
      # read log from stderr when hammerd is invoked by Spawn() either.
      # As a result, log can only be manually retrieved in hammerd.log.
      exit_reason = {
          1:  'kUnknownError',
          10: 'kNeedUsbInfo',
          11: 'kEcImageNotFound',
          12: 'kTouchpadImageNotFound',
          13: 'kUnknownUpdateCondition',
          14: 'kConnectionError',
          15: 'kInvalidFirmware',
          16: 'kTouchpadMismatched',
      }

      if e.returncode in exit_reason:
        logging.error('Hammerd exit reason: %s', exit_reason[e.returncode])
      else:
        logging.error('Hammerd exited due to unknown error.')

      self.FailTask('Hammerd update failed (exit status %d). Please check '
                    '/var/log/hammerd.log for detail.' % e.returncode)

  def VerifyBaseInfo(self, ec, tp, fw):
    """Verify base is updated properly by comparing its attributes with the
    target FW.

    Args:
      ec: A dictionary of the on-board EC info.
      tp: A dictionary of the on-board touchpad info.
      fw: A dictionary of the target EC FW info.
    """
    self.assertEqual(
        ec['ro_version'], fw['ro']['version'],
        'Base EC may not be properly updated: Base RO version %s (%s expected).'
        % (ec['ro_version'], fw['ro']['version']))
    self.assertEqual(
        ec['rw_version'], fw['rw']['version'],
        'Base EC may not be properly updated: Base RW version %s (%s expected).'
        % (ec['rw_version'], fw['rw']['version']))
    self.assertIn(
        int(tp['tp_vendor'], 16), VENDOR_IDS,
        'Touchpad may not be properly updated: Vendor %s (any of %s expected).'
        % (tp['tp_vendor'], [hex(x) for x in VENDOR_IDS]))
    self.assertNotEqual(
        tp['tp_fw_checksum'], '0x0000',
        'Touchpad may not be properly updated: checksum %s (unexpected).'
        % (tp['tp_fw_checksum']))

  def BaseIsReady(self):
    try:
      process_utils.CheckCall(['lsusb', '-d', self.device_id])
    except process_utils.CalledProcessError:
      return 0
    return 1


class UsbInfo:
  """Helper class to get USB device info via usb_updater2 or lsusb."""

  def __init__(self, device_id):
    self._device_id = device_id

  def CmdWithArgs(self, args, cmd='usb_updater2', tries=5):
    """Helper method that appends USB device ID to USB related command,
    retries the command and returns its output.

    Args:
      args: The args or subcommand to be passed to usb command.
      cmd: The main USB related command. The default is `usb_updater2`.
      tries: times to retry. The default is 5.

    Returns:
      The output of `cmd`.

    Raises:
      CalledProcessError if `cmd` failed up to `tries` times.
    """
    err = None

    for _ in range(tries):
      try:
        return process_utils.LogAndCheckOutput(
            [cmd, '-d', self._device_id] + args)
      except process_utils.CalledProcessError as e:
        err = e
        logging.warning('Failed to call %s, trying again.', cmd)
        time.sleep(0.5)

    logging.error('Failed to call %s after %d tries.', cmd, tries)

    raise err  # pylint: disable=raising-bad-type

  def GetBaseInfo(self):
    """Retrieve and parse on-board EC info.

    Returns:
      A dictionary containing on-board EC info.
    """
    key_trans = {
        'Flash protection status': 'wp_status',
        'maximum PDU size': 'pdu_size',
        'min_rollback': 'min_rollback',
        'version': 'ro_version',
    }
    res = {}

    for line in self.CmdWithArgs(['-f']).splitlines():
      if ':' in line:
        k, v = line.split(':', 1)
        if k in key_trans:
          res[key_trans[k]] = v.strip()

    # Extra step to read RW version via lsusb.
    # usb_updater2 is unable to read the version of current FW section which
    # base is running on (usually RW), so using lsusb instead.
    # The code is a bit nasty here, because we only care about the RW version
    # and the lsusb content is not easy to be parsed without regexp.
    for line in self.CmdWithArgs(['-vv'], cmd='lsusb').splitlines():
      if re.search(r'iConfiguration\s*\d*\s*RW', line):
        res['rw_version'] = line.split(':', 1)[1].strip()

    return res

  def GetTouchpadInfo(self):
    """Retrieve and parse on-board touchpad info.

    Returns:
      A dictionary containing on-board touchpad info.
    """
    key_trans = {
        'fw_fw_checksum': 'tp_fw_checksum',
        'fw_version': 'tp_version',
        'id': 'tp_id',
        'status': 'tp_status',
        'vendor': 'tp_vendor',
    }
    res = {}

    for line in self.CmdWithArgs(['-t']).splitlines():
      if ':' in line:
        k, v = line.split(':', 1)
        if k in key_trans:
          res[key_trans[k]] = v.strip()

    return res

  def GetFirmwareInfo(self, fw_path):
    """Retrieve and parse given EC FW info.

    Args:
      fw_path: The absolute path to target EC FW image.

    Returns:
      A dictionary containing target EC FW info.
    """
    key_trans = {
        'v': 'version',
        'rb': 'rollback',
        'off': 'offset',
        'kv': 'key_version',
    }
    res = {'ro': {}, 'rw': {}}

    for line in self.CmdWithArgs(['-b', fw_path]).splitlines():
      mode, *rest = line.split()
      if mode in ('RO', 'RW'):
        for kv in rest:
          k, v = kv.split('=', 1)
          if k in key_trans:
            res[mode.lower()][key_trans[k]] = v.strip()

    return res
