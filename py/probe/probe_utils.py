# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""functions for probing components."""

import logging

from cros.factory.probe import common
from cros.factory.utils import config_utils


def Probe(probe_statement, comps=None, approx_match=False, max_mismatch=0):
  """Probe components according the configuration file.

  Args:
    probe_statement: The probe statement for the components
    comps: None or a list of component class name.
    approx_match: a boolean to enable approximate matching.
    max_mismatch: a number of mismatched rules at most.

  Returns:
    A dict of probe results of each component.
  """
  if comps is None:
    comps = list(probe_statement)

  results = {}
  for comp_cls in probe_statement:
    if comp_cls not in comps:
      continue
    results[comp_cls] = []
    for comp_name, statement in probe_statement[comp_cls].items():
      logging.info('Probe %s: %s', comp_cls, comp_name)

      for probed_values in common.EvaluateStatement(statement,
                                                    approx_match=approx_match,
                                                    max_mismatch=max_mismatch):
        result = {'name': comp_name}
        result.update(probed_values)
        if 'information' in statement:
          result['information'] = statement['information']

        results[comp_cls].append(result)

  return results


def GenerateProbeStatement(config_file=None,
                           include_generic=False, include_volatile=False):
  """A helper function to generate the unioned probe statements.

  Args:
    config_file: None of a string of a path to the config file.
    include_generic: Whether to include the probe statements for generic
        components or not.
    include_volatile: Whether to include the probe statements for volatile
        components or not.

  Returns:
    A dict of probe statements.
  """
  statement_dict = {}
  if config_file:
    config_utils.OverrideConfig(statement_dict,
                                common.LoadUserProbeStatementFile(config_file))
  if include_generic:
    config_utils.OverrideConfig(statement_dict, common.LoadGenericStatement())
  if include_volatile:
    config_utils.OverrideConfig(statement_dict, common.LoadVolatileStatement())

  return statement_dict
