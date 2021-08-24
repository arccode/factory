# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module collects utilities that analyze / validate the HWID DB contents.
"""

import copy
import difflib
import enum
import functools
import itertools
from typing import List, Mapping, NamedTuple, Optional, Tuple

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


def _GetComponentMagicPlaceholder(comp_cls, comp_name):
  # Prefix "x" prevents yaml from quoting the string.
  return f'x@@@@component@{comp_cls}@{comp_name}@@@@'


def _GetSupportStatusMagicPlaceholder(comp_cls, comp_name):
  # Prefix "x" prevents yaml from quoting the string.
  return f'x@@@@support_status@{comp_cls}@{comp_name}@@@@'


class ErrorCode(enum.Enum):
  """Enumerate the type of errors."""
  SCHEMA_ERROR = enum.auto()
  CONTENTS_ERROR = enum.auto()
  UNKNOWN_ERROR = enum.auto()
  COMPATIBLE_ERROR = enum.auto()


class Error(NamedTuple):
  """A record class to hold an error message."""
  code: ErrorCode
  message: str


class NameChangedComponentInfo(NamedTuple):
  """A data structure to collect the component info of added/updated names."""
  comp_name: str
  cid: int
  qid: int
  status: str
  has_cid_qid: bool


class ValidationReport(NamedTuple):
  errors: List[Error]
  warnings: List[str]
  name_changed_components: Mapping[str, List[NameChangedComponentInfo]]

  @classmethod
  def CreateEmpty(cls):
    return cls([], [], {})


class DBLineAnalysisResult(NamedTuple):

  class ModificationStatus(enum.Enum):
    NOT_MODIFIED = enum.auto()
    MODIFIED = enum.auto()
    NEWLY_ADDED = enum.auto()

  class Part(NamedTuple):

    class Type(enum.Enum):
      TEXT = enum.auto()
      COMPONENT_NAME = enum.auto()
      COMPONENT_STATUS = enum.auto()

    type: Type
    text: str

    @property
    def reference_id(self):
      return self.text  # Reuse the existing field.

  modification_status: ModificationStatus
  parts: List[Part]


class HWIDComponentAnalysisResult(NamedTuple):
  comp_cls: str
  comp_name: str
  support_status: str
  is_newly_added: bool
  avl_id: Optional[Tuple[int, int]]
  seq_no: int
  comp_name_with_correct_seq_no: Optional[str]


class ChangeAnalysisReport(NamedTuple):
  precondition_errors: List[Error]
  lines: List[DBLineAnalysisResult]
  hwid_components: Mapping[str, HWIDComponentAnalysisResult]


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
      report.errors.append(
          Error(ErrorCode.SCHEMA_ERROR, str(self._curr_db.load_error)))
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
            Error(ErrorCode.CONTENTS_ERROR,
                  f'{dram_tag!r} does not contain size property'))
    return True

  def ValidateChange(self, ignore_invalid_old_db=False) -> ValidationReport:
    """Validates the change between the current HWID DB and the previous one."""
    report = ValidationReport.CreateEmpty()
    if self._curr_db.load_error:
      report.errors.append(
          Error(ErrorCode.SCHEMA_ERROR, str(self._curr_db.load_error)))
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
        report.errors.append(
            Error(
                ErrorCode.UNKNOWN_ERROR,
                'Failed to load the previous version of '
                f'HWID DB: {self._curr_db.load_error}'))
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
          Error(
              ErrorCode.CONTENTS_ERROR,
              'The new HWID database should not use legacy pattern.  Please '
              'use "hwid build-database" to prevent from generating legacy '
              'pattern.'))
      return False

    region_field_legacy_info = self._curr_db.instance.region_field_legacy_info
    if not region_field_legacy_info or any(region_field_legacy_info.values()):
      report.errors.append(
          Error(ErrorCode.CONTENTS_ERROR,
                'Legacy region field is forbidden in any new HWID database.'))
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
          Error(
              ErrorCode.COMPATIBLE_ERROR,
              'The new HWID database should not use legacy pattern. Please '
              'use "hwid update-database" to prevent from generating legacy '
              'pattern.'))
      return False

    # Make sure all the encoded fields in the existing patterns are not changed.
    for image_id in self._prev_db.instance.image_ids:
      old_bit_mapping = self._prev_db.instance.GetBitMapping(image_id=image_id)
      new_bit_mapping = self._curr_db.instance.GetBitMapping(image_id=image_id)
      for index, (element_old, element_new) in enumerate(
          zip(old_bit_mapping, new_bit_mapping)):
        if element_new != element_old:
          report.errors.append(
              Error(
                  ErrorCode.COMPATIBLE_ERROR,
                  f'Bit pattern mismatch found at bit {index} (encoded '
                  f'field={element_old[0]}). If you are trying to append new '
                  'bit(s), be sure to create a new bit pattern field instead '
                  'of simply incrementing the last field.'))

    old_reg_field_legacy_info = self._prev_db.instance.region_field_legacy_info
    new_reg_field_legacy_info = self._curr_db.instance.region_field_legacy_info
    for field_name, is_legacy_style in new_reg_field_legacy_info.items():
      orig_is_legacy_style = old_reg_field_legacy_info.get(field_name)
      if orig_is_legacy_style is None:
        if is_legacy_style:
          report.errors.append(
              Error(
                  ErrorCode.CONTENTS_ERROR,
                  'New region field should be constructed by new style yaml '
                  'tag.'))
      else:
        if orig_is_legacy_style != is_legacy_style:
          report.errors.append(
              Error(ErrorCode.COMPATIBLE_ERROR,
                    'Style of existing region field should remain unchanged.'))
    return True

  def _ValidateChangeOfComponents(self, report: ValidationReport):
    """Check if modified (created) component names are valid."""
    for comp_cls, comps in self._ExtractHWIDComponents().items():
      for comp in comps:
        if comp.extracted_seq_no is not None:
          expected_comp_name = (
              f'{comp.extracted_noseq_comp_name}#{comp.expected_seq_no}')
          if expected_comp_name != comp.name:
            report.errors.append(
                Error(
                    ErrorCode.CONTENTS_ERROR,
                    'Invalid component name with sequence number, please '
                    f'modify it from {comp.name!r} to {expected_comp_name!r}'
                    '.'))
        cid, qid = comp.extracted_avl_id or (0, 0)
        if comp.is_newly_added:
          report.name_changed_components.setdefault(comp_cls, []).append(
              NameChangedComponentInfo(comp.name, cid, qid, comp.status,
                                       bool(comp.extracted_avl_id)))

  def AnalyzeChange(self, db_contents_patcher) -> ChangeAnalysisReport:
    """Analyzes the HWID DB change.

    Args:
      db_contents_patcher: A function that patches / removes the header of the
          given HWID DB contents.

    Returns:
      An instance of `ChangeAnalysisReport`.
    """
    report = ChangeAnalysisReport([], [], {})
    if not self._curr_db.instance:
      report.precondition_errors.append(
          Error(ErrorCode.SCHEMA_ERROR, str(self._curr_db.load_error)))
      return report

    # To locate the HWID component name / status text part in the HWID DB
    # contents, we first dump a specialized HWID DB which has all cared parts
    # replaced by some magic placeholders.  Then we parse the raw string to
    # find out the location of those fields.

    all_comps = self._ExtractHWIDComponents()
    all_placeholders = []
    db_placeholder_options = database.MagicPlaceholderOptions({})
    for comp_cls, comps in all_comps.items():
      for comp in comps:
        comp_name_replacer = _GetComponentMagicPlaceholder(comp_cls, comp.name)
        comp_status_replacer = _GetSupportStatusMagicPlaceholder(
            comp_cls, comp.name)
        db_placeholder_options.components[(comp_cls, comp.name)] = (
            database.MagicPlaceholderComponentOptions(comp_name_replacer,
                                                      comp_status_replacer))

        all_placeholders.append(
            (comp_name_replacer,
             DBLineAnalysisResult.Part(
                 DBLineAnalysisResult.Part.Type.COMPONENT_NAME,
                 comp_name_replacer)))
        all_placeholders.append(
            (comp_status_replacer,
             DBLineAnalysisResult.Part(
                 DBLineAnalysisResult.Part.Type.COMPONENT_STATUS,
                 comp_name_replacer)))

        if (comp.extracted_seq_no is not None and
            comp.extracted_seq_no != str(comp.expected_seq_no)):
          comp_name_with_correct_seq_no = (
              f'{comp.extracted_noseq_comp_name}#{comp.expected_seq_no}')
        else:
          comp_name_with_correct_seq_no = None
        report.hwid_components[comp_name_replacer] = (
            HWIDComponentAnalysisResult(
                comp_cls, comp.name, comp.status, comp.is_newly_added,
                comp.extracted_avl_id, comp.expected_seq_no,
                comp_name_with_correct_seq_no))

    dumped_db_lines = db_contents_patcher(
        self._curr_db.instance.DumpData(
            suppress_support_status=False,
            magic_placeholder_options=db_placeholder_options)).splitlines()

    no_placeholder_dumped_db_lines = db_contents_patcher(
        self._curr_db.instance.DumpData(
            suppress_support_status=False)).splitlines()
    if len(dumped_db_lines) != len(no_placeholder_dumped_db_lines):
      # Unexpected case, skip deriving the line diffs.
      diff_view_line_it = itertools.repeat('  ', len(dumped_db_lines))
    elif not self._prev_db or not self._prev_db.instance:
      diff_view_line_it = itertools.repeat('  ', len(dumped_db_lines))
    else:
      prev_db_contents_lines = db_contents_patcher(
          self._prev_db.instance.DumpData()).splitlines()
      diff_view_line_it = difflib.ndiff(prev_db_contents_lines,
                                        no_placeholder_dumped_db_lines)

    removed_line_count = 0

    splitter = _LineSplitter(
        all_placeholders,
        functools.partial(DBLineAnalysisResult.Part,
                          DBLineAnalysisResult.Part.Type.TEXT))
    for line in dumped_db_lines:
      while True:
        diff_view_line = next(diff_view_line_it)
        if diff_view_line.startswith('? '):
          unused_next_line = next(diff_view_line_it)
          continue
        if not diff_view_line.startswith('- '):
          break
        removed_line_count += 1
      if diff_view_line.startswith('  '):
        removed_line_count = 0
        mod_status = DBLineAnalysisResult.ModificationStatus.NOT_MODIFIED
      elif removed_line_count > 0:
        removed_line_count -= 1
        mod_status = DBLineAnalysisResult.ModificationStatus.MODIFIED
      else:
        mod_status = DBLineAnalysisResult.ModificationStatus.NEWLY_ADDED

      parts = splitter.SplitText(line)
      report.lines.append(DBLineAnalysisResult(mod_status, parts))
    return report

  class _HWIDComponentMetadata(NamedTuple):
    name: str
    status: str
    extracted_noseq_comp_name: str
    extracted_seq_no: Optional[str]
    extracted_avl_id: Optional[Tuple[int, int]]
    expected_seq_no: int
    is_newly_added: bool

  def _ExtractHWIDComponents(
      self) -> Mapping[str, List[_HWIDComponentMetadata]]:
    ret = {}
    adapter = name_pattern_adapter.NamePatternAdapter()
    for comp_cls in self._curr_db.instance.GetActiveComponentClasses():
      ret[comp_cls] = []
      name_pattern = adapter.GetNamePattern(comp_cls)
      for expected_seq, (comp_name, comp_info) in enumerate(
          self._curr_db.instance.GetComponents(comp_cls).items(), 1):
        avl_id = name_pattern.Matches(comp_name)
        noseq_comp_name, sep, actual_seq = comp_name.partition('#')
        is_newly_added = False
        if self._prev_db is None or self._prev_db.instance is None:
          is_newly_added = True
        else:
          prev_comp = self._prev_db.instance.GetComponents(comp_cls).get(
              comp_name)
          if prev_comp is None:
            is_newly_added = True
          elif avl_id is not None and prev_comp.status != comp_info.status:
            is_newly_added = True
        ret[comp_cls].append(
            self._HWIDComponentMetadata(comp_name, comp_info.status,
                                        noseq_comp_name,
                                        actual_seq if sep else None, avl_id,
                                        expected_seq, is_newly_added))
    return ret

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


class _LineSplitter:

  def __init__(self, placeholders, text_part_factory):
    self._placeholders = placeholders
    self._text_part_factory = text_part_factory

  def SplitText(self, text):
    return self._SplitTextRecursively(text, 0)

  def _SplitTextRecursively(self, text, placeholder_idx):
    # Split the given text with i-th placeholder.  Then for each piece,
    # recursively split them with (i+1)-th placeholder.  This implementation
    # is slow in term of worst case scenario.  However, in real case, each
    # line often contains no more than two placeholders.
    if placeholder_idx >= len(self._placeholders):
      return [self._text_part_factory(text)] if text else []
    placeholder_str, placeholder_sample = self._placeholders[placeholder_idx]
    placeholder_idx += 1
    text_parts = text.split(placeholder_str)
    parts = []
    for i, text_part in enumerate(text_parts):
      parts.extend(self._SplitTextRecursively(text_part, placeholder_idx))
      if i + 1 < len(text_parts):
        parts.append(copy.deepcopy(placeholder_sample))
    return parts
