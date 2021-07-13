# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Validator for HWID configs."""

from typing import List

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import \
    verification_payload_generator as vpg_module
from cros.factory.hwid.v3 import contents_analyzer
from cros.factory.hwid.v3 import database


ErrorCode = contents_analyzer.ErrorCode
Error = contents_analyzer.Error


class ValidationError(Exception):
  """An exception class that indicates validation failures."""

  def __init__(self, errors: List[Error]):
    super().__init__(str(errors))
    self.errors = errors


class HwidValidator:
  """Validates HWID configs."""

  def Validate(self, hwid_config_contents):
    """Validates a HWID config.

    Uses strict validation (i.e. includes checksum validation).

    Args:
      hwid_config_contents: the current HWID config as a string.
    """
    expected_checksum = database.Database.ChecksumForText(hwid_config_contents)

    contents_analyzer_inst = contents_analyzer.ContentsAnalyzer(
        hwid_config_contents, expected_checksum, None)
    report = contents_analyzer_inst.ValidateIntegrity()
    if report.errors:
      raise ValidationError(report.errors)

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
    expected_checksum = database.Database.ChecksumForText(hwid_config_contents)
    analyzer = contents_analyzer.ContentsAnalyzer(
        hwid_config_contents, expected_checksum, prev_hwid_config_contents)

    report_of_change = analyzer.ValidateChange()
    if report_of_change.errors:
      raise ValidationError(report_of_change.errors)

    report_of_integrity = analyzer.ValidateIntegrity()
    if report_of_integrity.errors:
      raise ValidationError(report_of_integrity.errors)

    db = analyzer.curr_db_instance
    vpg_target = CONFIG.vpg_targets.get(db.project)
    if vpg_target:
      errors = vpg_module.GenerateVerificationPayload(
          [(db, vpg_target.waived_comp_categories)]).error_msgs
      if errors:
        raise ValidationError(
            [Error(ErrorCode.CONTENTS_ERROR, err) for err in errors])
    return db.project, report_of_change.name_changed_components
