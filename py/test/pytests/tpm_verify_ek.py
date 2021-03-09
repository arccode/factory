# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Verifies the TPM endorsement key.

Description
-----------
This test (whether it succeeds or fails) always requests a TPM clear
on reboot.  It works even if run multiple times without rebooting.

If the TPM is somehow owned but no password is available, the test
will fail but emit a reasonable error message (and it will pass on the
next boot).

Test Procedure
--------------
This is an automated test without user interaction.

Dependency
----------
A workable TPM with endorsement key on it.
And hardware security daemons & clients.

Examples
--------
Examples of how to use this test::

  {
    "pytest_name": "tpm_verify_ek",
    "args": {
      "is_cros_core": false,
    }
  }

"""

import logging
import unittest

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

  def _TPMStatus(self):
    """Returns TPM status as a dictionary.

    e.g., {'status': 'STATUS_SUCCESS',
           'is_enabled': 'true',
           'is_owned': 'true',
           'is_owner_password_present': 'true',
           'has_reset_lock_permissions': 'true'}
    """

    status_txt = self.dut.CheckOutput(
        ['tpm_manager_client', 'status', '--nonsensitive'], log=True)

    # The status_txt would look like this:
    #
    # Message Reply: [tpm_manager.GetTpmNonsensitiveStatusReply] {
    #   status: STATUS_SUCCESS
    #   is_enabled: true
    #   is_owned: true
    #   is_owner_password_present: true
    #   has_reset_lock_permissions: true
    # }

    status_lines = status_txt.splitlines()
    self.assertTrue(
        len(status_lines) > 2, 'Failed to get TPM status. Reboot and re-run.')

    # Trim the first and last lines.
    status = string_utils.ParseDict(status_lines[1:-1])
    logging.info('TPM status: %r', status)
    return status

  def _AttestationVerifyEK(self):
    """Returns TPM EK status."""

    status_txt = self.dut.CheckOutput(
        ['attestation_client', 'verify_attestation', '--ek-only'] +
        (['--cros_core'] if self.args.is_cros_core else []), log=True)

    # The status_txt would look like this:
    #
    # [attestation.VerifyReply] {
    #   verified: true
    # }

    status_lines = status_txt.splitlines()
    self.assertTrue(
        len(status_lines) > 2,
        'Failed to get TPM EK status. Reboot and re-run.')

    # Trim the first and last lines.
    status = string_utils.ParseDict(status_lines[1:-1])
    logging.info('TPM EK status: %r', status)
    return status['verified'] == 'true'

  def VerifyByHwsecDaemons(self):
    """Verifies TPM endorsement by hardware security daemons."""

    # Make sure TPM is enabled.
    status = self._TPMStatus()
    self.assertEqual('true', status['is_enabled'])

    # Check explicitly for the case where TPM is owned but password is
    # unavailable.  This shouldn't really ever happen, but in any case
    # the TPM will become un-owned on reboot (thanks to the crossystem
    # command above).
    self.assertFalse(
        status['is_owned'] == 'true' and
        status['is_owner_password_present'] == 'false',
        'TPM is owned but password is not available. Reboot and re-run.')

    # Take ownership of the TPM (if not already taken).
    self.dut.CheckCall(['tpm_manager_client', 'take_ownership'], log=True)

    # Make sure TPM is owned.
    self.assertEqual('true', self._TPMStatus()['is_owned'])

    # Verify TPM endorsement.
    self.assertTrue(self._AttestationVerifyEK())

  def runTest(self):
    # Always clear TPM on next boot, in case any problems arise.
    self.dut.CheckCall(['crossystem', 'clear_tpm_owner_request=1'], log=True)

    # Run the verify process.
    self.VerifyByHwsecDaemons()
