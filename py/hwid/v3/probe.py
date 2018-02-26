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
    os.path.dirname(__file__), 'default_probe_statement.json')


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
                                 mode, allow_mismatched_components):
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

  Returns:
    A instance of BOM class and a sub-dictionary of the probed results contains
        the mismatched components.
  """
  def _IsValuesMatch(probed_values, comp_values):
    for key, value in comp_values.iteritems():
      if not isinstance(value, Value):
        value = Value(value)
      if key not in probed_values or not value.Matches(probed_values[key]):
        return False
    return True

  # Construct a dict of component classes to list of component names.
  matched_components = {comp_cls: []
                        for comp_cls in database.GetComponentClasses()}
  mismatched_components = {comp_cls: value
                           for comp_cls, value in probed_results.iteritems()
                           if comp_cls not in matched_components}

  for comp_cls in database.GetComponentClasses():
    default_comp = database.GetDefaultComponent(comp_cls)
    for probed_comp_name, probed_comp_items in probed_results.get(
        comp_cls, {}).iteritems():
      for probed_comp_item in probed_comp_items:
        for comp_name, comp_info in database.GetComponents(
            comp_cls).iteritems():
          if comp_info.values is None:
            continue
          if _IsValuesMatch(probed_comp_item, comp_info.values):
            matched_components[comp_cls].append(comp_name)
            break
        else:
          if default_comp is not None:
            matched_components[comp_cls].append(default_comp)
          else:
            mismatched_components.setdefault(comp_cls, {})
            mismatched_components[comp_cls].setdefault(probed_comp_name, [])
            mismatched_components[comp_cls][
                probed_comp_name].append(probed_comp_item)

    # If no any probed result of this component class, try add the default one.
    if not matched_components[comp_cls] and default_comp is not None:
      matched_components[comp_cls].append(default_comp)

  if not allow_mismatched_components and any(
      sum(comps.values(), []) for comps in mismatched_components.itervalues()):
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