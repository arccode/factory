# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies the TPM endorsement key.

This test (whether it succeeds or fails) always requests a TPM clear
on reboot.  It works even if run multiple times without rebooting.

If the TPM is somehow owned but no password is available, the test
will fail but emit a reasonable error message (and it will pass on the
next boot).
"""

import distutils.spawn
import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.utils.file_utils import Sync
from cros.factory.utils.process_utils import Spawn, CheckOutput
from cros.factory.utils.string_utils import ParseDict

class TPMVerifyEK(unittest.TestCase):
  ARGS = [
      # Chromebooks and Chromeboxes should set this to False.
      Arg('is_cros_core', bool, 'Verify with ChromeOS Core endoresement',
          default=False)
  ]

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
      status_txt = CheckOutput(['cryptohome', '--action=tpm_status'])
      status = ParseDict(status_txt.splitlines())
      logging.info('TPM status: %r', status)
      return status

    # Make sure TPM is enabled.
    status = _TPMStatus()
    self.assertEquals('true', status['TPM Enabled'])

    # Check explicitly for the case where TPM is owned but password is
    # unavailable.  This shouldn't really ever happen, but in any case
    # the TPM will become un-owned on reboot (thanks to the crossystem
    # command above).
    self.assertFalse(
        status['TPM Owned'] == 'true' and not status['TPM Password'],
        'TPM is owned but password is not available. Reboot and re-run.')

    # Take ownership of the TPM (if not already taken).
    Spawn(['cryptohome', '--action=tpm_take_ownership'],
          log=True, check_call=True)
    # Wait for TPM ownership to complete.  No check_call=True since this
    # may fail if the TPM is already owned.
    Spawn(['cryptohome', '--action=tpm_wait_ownership'],
          log=True, call=True)
    # Sync, to make sure TPM password was written to disk.
    Sync()

    self.assertEquals('true', _TPMStatus()['TPM Owned'])

    # Verify the endorsement key.
    process = Spawn(['cryptohome', '--action=tpm_verify_ek'] + (
                    ["--cros_core"] if self.args.is_cros_core else []),
                    read_stderr=True,
                    log=True, check_call=True)
    # Make sure there's no stderr from tpm_verify_ek (since that, plus
    # check_call=True, is the only reliable way to make sure it
    # worked).
    self.assertEquals('', process.stderr_data)

  def VerifyByTpmManager(self):
    """Verifies TPM endorsement by tpm-manager (from CryptoHome package)."""

    # Take ownership of the TPM (if not already taken).
    Spawn(['tpm-manager', 'initialize'], log=True, check_call=True)

    # Verify TPM endorsement.
    Spawn(['tpm-manager', 'verify_endorsement'] + (
          ["--cros_core"] if self.args.is_cros_core else []),
          log=True, check_call=True)

  def runTest(self):
    # Always clear TPM on next boot, in case any problems arise.
    Spawn(['crossystem', 'clear_tpm_owner_request=1'],
          log=True, check_call=True)

    # Check if we have tpm-manager in system.
    if distutils.spawn.find_executable('tpm-manager'):
      self.VerifyByTpmManager()
    else:
      self.VerifyByCryptoHome()
