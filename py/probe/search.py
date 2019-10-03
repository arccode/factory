# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The module searches the components in generic way.

We provide a generic probe function for each component, which can find most of
common components. The generic probe function for each component is defined at
generic_statement.json.
"""

import logging

from cros.factory.hwid.v3 import builder
from cros.factory.probe import common
from cros.factory.probe import function


_generic_statement = None


def _LoadGenericProbeStatement():
  """Loads the generic probe statement once."""
  global _generic_statement  # pylint: disable=global-statement
  if _generic_statement is not None:
    return _generic_statement
  logging.info('Load generic statement file.')
  _generic_statement = common.LoadGenericStatement()
  return _generic_statement


def GetGenericComponentClasses():
  """Gets the list of components classes which have generic probe function."""
  return list(_LoadGenericProbeStatement())


def GenerateProbeStatement(comp_cls):
  """Generates the probe statement for the component class."""
  if comp_cls not in GetGenericComponentClasses():
    return {}
  statement = {comp_cls: {}}
  func_expression = _generic_statement[comp_cls]['generic']['eval']
  logging.debug('Function expression for component [%s]: %s',
                comp_cls, func_expression)
  results = function.InterpretFunction(func_expression)()
  if results:
    results = list(map(
        dict, set(frozenset(result.items()) for result in results)))
    for result in results:
      comp_name = builder.DetermineComponentName(
          comp_cls, result, list(statement[comp_cls]))
      statement[comp_cls][comp_name] = {
          'eval': func_expression,
          'expect': result}
  return statement
