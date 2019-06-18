# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Validator for HWID configs."""

import logging

# pylint: disable=import-error
import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import \
    verification_payload_generator as vpg_module
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import verify_db_pattern


class ValidationError(ValueError):
  """Indicates that validation of the HWID config failed."""


class HwidValidator(object):
  """Validates HWID configs."""

  def Validate(self, hwid_config_contents):
    """Validates a HWID config.

    Uses strict validation (i.e. includes checksum validation).

    Args:
      hwid_config_contents: the current HWID config.
    """
    expected_checksum = database.Database.ChecksumForText(
        hwid_config_contents.encode('utf8')).decode('utf8')

    try:
      # Validate config by loading it.
      database.Database.LoadData(
          hwid_config_contents, expected_checksum=expected_checksum)
    except HWIDException as e:
      raise ValidationError(e.message)

  def ValidateChange(self, hwid_config_contents, prev_hwid_config_contents):
    """Validates a HWID config change.

    This method validates the current config (strict, i.e. including its
    checksum), the previous config (non strict, i.e. no checksum validation)
    and the change itself (e.g. bitfields may only be appended at the end, not
    inserted in the middle).

    Args:
      hwid_config_contents: the current HWID config.
      prev_hwid_config_contents: the previous HWID config.
    """
    try:
      # Load previous config. This has the side effect of validating it.
      prev_db = database.Database.LoadData(
          prev_hwid_config_contents, expected_checksum=None)
    except HWIDException as e:
      logging.exception('Previous version not valid: %r', e)
      raise ValidationError('Previous version of HWID config is not valid.')

    expected_checksum = database.Database.ChecksumForText(
        hwid_config_contents.encode('utf8')).decode('utf8')

    try:
      # Load and validate current config.
      db = database.Database.LoadData(
          hwid_config_contents, expected_checksum=expected_checksum)
      # Verify that the change is valid.
      verify_db_pattern.HWIDDBsPatternTest.VerifyParsedDatabasePattern(
          prev_db, db)
    except HWIDException as e:
      raise ValidationError(e.message)

    if db.project in CONFIG.board_mapping:
      try:
        vpg_module.GenerateVerificationPayload([db])
      except vpg_module.GenerateVerificationPayloadError as e:
        raise ValidationError(e.message)
