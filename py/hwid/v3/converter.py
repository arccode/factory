# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3.rule import Value
from cros.factory.probe import probe_utils


DEFAULT_PROBE_STATEMENT_PATH = os.path.join(
    os.path.dirname(__file__), common.DEFAULT_PROBE_STATEMENT)


def ConvertToProbeStatement(database):
  """Gets the components of the specific component class.

  Args:
    database: A Database object to be used.

  Returns:
    A dict of project specific probe statements.
  """
  def _ConvertValue(v):
    if isinstance(v, Value):
      if v.is_re:
        return "!re {}".format(v.raw_value)
      else:
        return v.raw_value
    return v

  probe_statement = probe_utils.GenerateProbeStatement(
      config_file=DEFAULT_PROBE_STATEMENT_PATH)
  converted_probe_statement = {}
  for comp_cls, statements in probe_statement.items():
    converted_components = {}
    generic_statement = statements['generic']
    for comp_name, comp_info in database.GetComponents(comp_cls).items():
      if comp_info.values is None:
        continue
      converted_components[comp_name] = generic_statement.copy()
      expect = {k: _ConvertValue(v) for k, v in comp_info.values.items()}
      converted_components[comp_name]['expect'] = expect
      converted_components[comp_name]['information'] = {'status':
                                                        comp_info.status}
    converted_probe_statement[comp_cls] = converted_components

  return converted_probe_statement
