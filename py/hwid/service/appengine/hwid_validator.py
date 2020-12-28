# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Validator for HWID configs."""

import logging

import yaml

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import \
    verification_payload_generator as vpg_module
from cros.factory.hwid.v3.common import HWIDException
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import validator as v3_validator
from cros.factory.utils import schema


class HwidValidator:
  """Validates HWID configs."""

  def Validate(self, hwid_config_contents):
    """Validates a HWID config.

    Uses strict validation (i.e. includes checksum validation).

    Args:
      hwid_config_contents: the current HWID config as a string.
    """
    expected_checksum = database.Database.ChecksumForText(hwid_config_contents)

    try:
      # Validate config by loading it.
      db = database.Database.LoadData(
          hwid_config_contents, expected_checksum=expected_checksum)
    except (HWIDException, schema.SchemaException, yaml.error.YAMLError) as e:
      raise v3_validator.ValidationError(str(e))
    v3_validator.ValidateIntegrity(db)

  def ValidateChange(self, hwid_config_contents, prev_hwid_config_contents):
    """Validates a HWID config change.

    This method validates the current config (strict, i.e. including its
    checksum), the previous config (non strict, i.e. no checksum validation)
    and the change itself (e.g. bitfields may only be appended at the end, not
    inserted in the middle).

    Args:
      hwid_config_contents: the current HWID config as a string.
      prev_hwid_config_contents: the previous HWID config as a string.
    Returns:
      A tuple (project, new_comps) where new_comps is a dict in the form of
      {category: [(ciq, qid, status),...]} which collects created/updated
      component names in the ${category}_${cid}_${qid} pattern.
    """
    try:
      # Load previous config. This has the side effect of validating it.
      prev_db = database.Database.LoadData(
          prev_hwid_config_contents, expected_checksum=None)
    except (HWIDException, schema.SchemaException, yaml.error.YAMLError) as e:
      logging.exception('Previous version not valid: %r', e)
      raise v3_validator.ValidationError(
          'Previous version of HWID config is not valid.')

    expected_checksum = database.Database.ChecksumForText(hwid_config_contents)

    try:
      # Load and validate current config.
      db = database.Database.LoadData(
          hwid_config_contents, expected_checksum=expected_checksum)
    except (HWIDException, schema.SchemaException, yaml.error.YAMLError) as e:
      raise v3_validator.ValidationError(str(e))

    new_components = v3_validator.ValidateChange(prev_db, db)
    v3_validator.ValidateIntegrity(db)

    vpg_target = CONFIG.vpg_targets.get(db.project)
    if vpg_target:
      errors = vpg_module.GenerateVerificationPayload(
          [(db, vpg_target.waived_comp_categories)]).error_msgs
      if errors:
        raise v3_validator.ValidationError(str(errors))
    return db.project, new_components
