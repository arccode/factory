# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3.bom import BOM
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.rule import Context
from cros.factory.hwid.v3.rule import Value
from cros.factory.probe import probe_utils


DEFAULT_PROBE_STATEMENT_PATH = os.path.join(
    os.path.dirname(__file__), common.DEFAULT_PROBE_STATEMENT)


def ProbeDUT():
  """Probe the device to obtain the probed results.

  Returns:
    A dict of probed results.
  """
  try:
    probe_statement = probe_utils.GenerateProbeStatement(
        config_file=DEFAULT_PROBE_STATEMENT_PATH)
    return probe_utils.Probe(probe_statement)

  except Exception as e:
    raise common.HWIDException('Failed to execute the probe tool: %r.' % e)


def GenerateBOMFromProbedResults(database, probed_results, device_info, vpd,
                                 mode, allow_mismatched_components,
                                 use_name_match=False):
  """Generates a BOM object according to the given probed results.

  Args:
    database: An instance of a HWID database.
    probed_results: A JSON-serializable dict of the probe result, which is
        usually the output of the probe command.
    device_info: None or a dict of device info.
    vpd: None or a dict of vpd data.
    mode: None or "rma" or "normal".
    allow_mismatched_components: Whether to Allows some probed components to be
        ignored if no any component in the database matches with them.
    use_name_match: Use component name from probed results as matched component.

  Returns:
    A instance of BOM class and a sub-dictionary of the probed results contains
        the mismatched components.
  """
  def _IsValuesMatch(probed_values, comp_values):
    for key, value in comp_values.iteritems():
      if not isinstance(value, Value):
        value = Value(value)
      if key not in probed_values or not value.Matches(probed_values[key]):
        return False, None
    return True, -len(comp_values)

  def _GetDefaultComponent(comp_cls):
    if allow_mismatched_components:
      return None

    default_comp = database.GetDefaultComponent(comp_cls)

    # Always ignore the unsupported default components.
    if default_comp is not None:
      default_comp_info = database.GetComponents(comp_cls)[default_comp]
      if default_comp_info.status == common.COMPONENT_STATUS.unsupported:
        default_comp = None

    return default_comp

  if use_name_match:
    matched_components = {}
    mismatched_components = {}

    for comp_cls, comps in probed_results.iteritems():
      matched_components[comp_cls] = [comp['name'] for comp in comps]
  else:
    # Construct a dict of component classes to list of component names.
    matched_components = {comp_cls: []
                          for comp_cls in database.GetComponentClasses()}
    mismatched_components = {comp_cls: comps
                             for comp_cls, comps in probed_results.iteritems()
                             if comp_cls not in matched_components}

    for comp_cls in database.GetComponentClasses():
      default_comp = _GetDefaultComponent(comp_cls)

      for probed_comp in probed_results.get(comp_cls, []):
        matched_comp_name = None
        matched_comp_score = float('-inf')
        for comp_name, comp_info in database.GetComponents(
            comp_cls, include_default=False).iteritems():
          is_matched, score = _IsValuesMatch(probed_comp['values'],
                                             comp_info.values)
          if is_matched and score > matched_comp_score:
            matched_comp_name = comp_name
        if matched_comp_name is not None:
          matched_components[comp_cls].append(matched_comp_name)
        else:
          if default_comp is not None:
            matched_components[comp_cls].append(default_comp)
          else:
            mismatched_components.setdefault(comp_cls, [])
            mismatched_components[comp_cls].append(probed_comp)

      # If no any probed result of this component class, try add the default
      # one.
      if not matched_components[comp_cls] and default_comp is not None:
        matched_components[comp_cls].append(default_comp)

    if (not allow_mismatched_components and
        any(mismatched_components.itervalues())):
      raise common.HWIDException(
          'Probed components %r are not matched with any component records in '
          'the database.' % mismatched_components)

  bom = BOM(encoding_pattern_index=0,
            image_id=database.max_image_id,
            components=matched_components)

  # Evaluate device_info rules to fill unprobeable data in the BOM object.
  context = Context(database=database, bom=bom,
                    device_info=device_info, vpd=vpd, mode=mode)
  for rule in database.device_info_rules:
    rule.Evaluate(context)

  return bom, mismatched_components
