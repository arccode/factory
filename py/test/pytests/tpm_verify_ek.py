# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies the TPM endorsement key.

This test (whether it succeeds or fails) always requests a TPM clear
on reboot.  It works even if run multiple times without rebooting.

If the TPM is somehow owned but no password is available, the test
will fail but emit a reasonable error message (and it will pass on the
next boot).
"""

import logging
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import string_utils


class TPMVerifyEK(unittest.TestCase):
  ARGS = [
      # Chromebooks and Chromeboxes should set this to False.
      Arg('is_cros_core', bool, 'Verify with ChromeOS Core endoresement',
          default=False)
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def VerifyByCryptoHome(self):
    """Verifies TPM endorsement by CryptoHome service."""

    def _TPMStatus():
      """Returns TPM status as a dictionary.

      e.g., {'TPM Being Owned': 'false',
             'TPM Ready': 'true',
             'TPM Password': 'd641b63ce6ff',
             'TPM Enabled': 'true',
             'TPM Owned': 'true'}
      """
      status_txt = self.dut.CheckOutput(['cryptohome', '--action=tpm_status'],
                                        log=True)
      status = string_utils.ParseDict(status_txt.splitlines())
      logging.info('TPM status: %r', status)
      return status

    # Make sure TPM is enabled.
    status = _TPMStatus()
    self.assertEqual('true', status['TPM Enabled'])

    # Check explicitly for the case where TPM is owned but password is
    # unavailable.  This shouldn't really ever happen, but in any case
    # the TPM will become un-owned on reboot (thanks to the crossystem
    # command above).
    self.assertFalse(
        status['TPM Owned'] == 'true' and not status['TPM Password'],
        'TPM is owned but password is not available. Reboot and re-run.')

    # Take ownership of the TPM (if not already taken).
    self.dut.CheckCall(['cryptohome', '--action=tpm_take_ownership'],
                       log=True)
    # Wait for TPM ownership to complete.  No check_call=True since this
    # may fail if the TPM is already owned.
    self.dut.Call(['cryptohome', '--action=tpm_wait_ownership'],
                  log=True)
    # Sync, to make sure TPM password was written to disk.
    self.dut.CheckCall(['sync'], log=True)

    self.assertEqual('true', _TPMStatus()['TPM Owned'])

    # Verify the endorsement key.
    with tempfile.TemporaryFile() as stderr:
      self.dut.CheckCall(
          ['cryptohome', '--action=tpm_verify_ek'] + (
              ['--cros_core'] if self.args.is_cros_core else []),
          log=True, stderr=stderr)
      # Make sure there's no stderr from tpm_verify_ek (since that, plus
      # check_call=True, is the only reliable way to make sure it
      # worked).
      stderr.seek(0)
      self.assertEqual('', stderr.read())

  def VerifyByTpmManager(self):
    """Verifies TPM endorsement by tpm-manager (from CryptoHome package)."""

    # Take ownership of the TPM (if not already taken).
    self.dut.CheckCall(['tpm-manager', 'initialize'], log=True)

    # Verify TPM endorsement.
    self.dut.CheckCall(['tpm-manager', 'verify_endorsement'] + (
        ['--cros_core'] if self.args.is_cros_core else []), log=True)

  def runTest(self):
    # Always clear TPM on next boot, in case any problems arise.
    self.dut.CheckCall(['crossystem', 'clear_tpm_owner_request=1'], log=True)

    # Check if we have tpm-manager in system.
    if self.dut.Call(['which', 'tpm-manager']) == 0:
      self.VerifyByTpmManager()
    else:
      self.VerifyByCryptoHome()
