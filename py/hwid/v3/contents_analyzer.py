# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module collects utilities that analyze / validate the HWID DB contents.
"""

import collections
from typing import List, Mapping, NamedTuple, Optional

import yaml

from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import name_pattern_adapter
from cros.factory.utils import schema


_BLOCKLIST_DRAM_TAG = set([
    'dram_default',
    'dram_placeholder',
    'a_fake_dram_0gb',
])


class NameChangedComponentInfo(NamedTuple):
  """A data structure to collect the component info of added/updated names."""
  comp_name: str
  cid: int
  qid: int
  status: str
  has_cid_qid: bool


class ValidationReport(NamedTuple):
  errors: List[str]
  warnings: List[str]
  name_changed_components: Mapping[str, List[NameChangedComponentInfo]]

  @classmethod
  def CreateEmpty(cls):
    return cls([], [], {})


class ContentsAnalyzer:

  class DBSnapshot(NamedTuple):
    """A record class that holds a specific version of HWID DB."""
    contents: str  # The raw string data.
    instance: Optional[database.Database]  # The loaded DB instance.
    load_error: Optional[Exception]  # Exception instance for loading failure.

  def __init__(self, curr_db_contents: str,
               expected_curr_db_checksum: Optional[str],
               prev_db_contents: Optional[str]):
    self._curr_db = self._LoadFromDBContents(curr_db_contents,
                                             expected_curr_db_checksum)
    self._prev_db = (
        self._LoadFromDBContents(prev_db_contents, None)
        if prev_db_contents is not None else None)

  @property
  def curr_db_instance(self) -> Optional[database.Database]:
    return self._curr_db.instance

  def ValidateIntegrity(self) -> ValidationReport:
    """Validates the current HWID DB."""
    report = ValidationReport.CreateEmpty()
    if self._curr_db.load_error:
      report.errors.append(str(self._curr_db.load_error))
    else:
      for validation_func in [self._ValidateDramIntegrity]:
        keep_going = validation_func(report, self._curr_db.instance)
        if not keep_going:
          break
    return report

  def _ValidateDramIntegrity(self, validation_report, db_instance):
    for dram_tag, dram_info in db_instance.GetComponents('dram').items():
      if dram_tag in _BLOCKLIST_DRAM_TAG:
        continue
      if not dram_info.values or 'size' not in dram_info.values:
        validation_report.errors.append(
            f'{dram_tag!r} does not contain size property')
    return True

  def ValidateChange(self, ignore_invalid_old_db=False) -> ValidationReport:
    """Validates the change between the current HWID DB and the previous one."""
    report = ValidationReport.CreateEmpty()
    if self._curr_db.load_error:
      report.errors.append(str(self._curr_db.load_error))
      return report

    if self._prev_db is None:
      if not self._ValidateChangeOfNewCreation(report):
        return report
    elif self._prev_db.load_error:
      if ignore_invalid_old_db:
        report.warnings.append(
            'The previous version of HWID database is an incompatible version '
            f'(exception: {self._prev_db.load_error}), ignore the pattern '
            'check.')
      else:
        report.errors.append(str(self._prev_db.load_error))
        return report
    else:
      if not self._ValidateChangeFromExistingSnapshot(report):
        return report
    self._ValidateChangeOfComponents(report)
    return report

  def _ValidateChangeOfNewCreation(self, report: ValidationReport) -> bool:
    """Checks if the newly created HWID DB applies up-to-date styles.

    Returns:
      A boolean indicates whether to keep performing the rest of validation
          steps.
    """
    if not self._curr_db.instance.can_encode:
      report.errors.append(
          'The new HWID database should not use legacy pattern.  Please use '
          '"hwid build-database" to prevent from generating legacy pattern.')
      return False

    region_field_legacy_info = self._curr_db.instance.region_field_legacy_info
    if not region_field_legacy_info or any(region_field_legacy_info.values()):
      report.errors.append(
          'Legacy region field is forbidden in any new HWID database.')
    return True

  def _ValidateChangeFromExistingSnapshot(self,
                                          report: ValidationReport) -> bool:
    """Checks if the HWID DB changes is backward compatible.

    Returns:
      A boolean indicates whether to keep performing the rest of validation
          steps.
    """
    # If the old database follows the new pattern rule, so does the new
    # database.
    if (self._prev_db.instance.can_encode and
        not self._curr_db.instance.can_encode):
      report.errors.append(
          'The new HWID database should not use legacy pattern. Please use '
          '"hwid update-database" to prevent from generating legacy pattern.')
      return False

    # Make sure all the encoded fields in the existing patterns are not changed.
    for image_id in self._prev_db.instance.image_ids:
      old_bit_mapping = self._prev_db.instance.GetBitMapping(image_id=image_id)
      new_bit_mapping = self._curr_db.instance.GetBitMapping(image_id=image_id)
      for index, (element_old, element_new) in enumerate(
          zip(old_bit_mapping, new_bit_mapping)):
        if element_new != element_old:
          report.errors.append(
              f'Bit pattern mismatch found at bit {index} (encoded '
              f'field={element_old[0]}). If you are trying to append new '
              'bit(s), be sure to create a new bit pattern field instead of '
              'simply incrementing the last field.')

    old_reg_field_legacy_info = self._prev_db.instance.region_field_legacy_info
    new_reg_field_legacy_info = self._curr_db.instance.region_field_legacy_info
    for field_name, is_legacy_style in new_reg_field_legacy_info.items():
      orig_is_legacy_style = old_reg_field_legacy_info.get(field_name)
      if orig_is_legacy_style is None:
        if is_legacy_style:
          report.errors.append(
              'New region field should be constructed by new style yaml tag.')
      else:
        if orig_is_legacy_style != is_legacy_style:
          report.errors.append(
              'Style of existing region field should remain unchanged.')
    return True

  def _ValidateChangeOfComponents(self, report: ValidationReport):
    """Check if modified (created) component names are valid."""

    def FindModifiedComponentsWithIdx(old_db, db, comp_cls):
      name_idx = {}
      for idx, (tag, comp) in enumerate(db.GetComponents(comp_cls).items(), 1):
        name_idx[tag] = (idx, comp)

      if old_db is not None:
        for tag in old_db.GetComponents(comp_cls):
          name_idx.pop(tag, None)

      return name_idx

    adapter = name_pattern_adapter.NamePatternAdapter()
    rename_component = {}
    bucket = collections.defaultdict(list)
    for comp_cls in self._curr_db.instance.GetActiveComponentClasses():
      name_pattern = adapter.GetNamePattern(comp_cls)
      modified_names = FindModifiedComponentsWithIdx(
          self._prev_db.instance, self._curr_db.instance, comp_cls)
      for tag, (idx, comp) in modified_names.items():
        name, sep, unused_seq = tag.partition('#')
        if sep:
          expected_component_name = f'{name}#{idx}'
          if tag != expected_component_name:
            rename_component[tag] = expected_component_name

        ret = name_pattern.Matches(tag)
        if ret:
          cid, qid = ret
          has_cid_qid = True
        else:
          cid = qid = 0
          has_cid_qid = False

        bucket[comp_cls].append(
            NameChangedComponentInfo(tag, cid, qid, comp.status, has_cid_qid))

    if rename_component:
      for actual_comp_name, expected_comp_name in rename_component.items():
        report.errors.append(
            'Invalid component name with sequence number, please modify it '
            f'from {actual_comp_name!r} to {expected_comp_name!r}.')
    else:
      for comp_cls, name_change_info_list in bucket.items():
        report.name_changed_components[comp_cls] = name_change_info_list

  @classmethod
  def _LoadFromDBContents(cls, db_contents: str,
                          expected_checksum: Optional[str]) -> 'DBSnapshot':
    try:
      db = database.Database.LoadData(db_contents,
                                      expected_checksum=expected_checksum)
      load_error = None
    except (schema.SchemaException, common.HWIDException,
            yaml.error.YAMLError) as ex:
      db = None
      load_error = ex
    return cls.DBSnapshot(db_contents, db, load_error)
