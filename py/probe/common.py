# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The module provides common variables and functions for probe framework.
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.functions import match
from cros.factory.utils import config_utils


GENERIC_STATEMENT_FILE = 'generic_statement'
VOLATILE_STATEMENT_FILE = 'volatile_statement'
STATEMENT_SCHEMA_FILE = 'statement'


def LoadStatement(config_name):
  """Loads the config file containing the probe statement."""
  return config_utils.LoadConfig(
      config_name, schema_name=STATEMENT_SCHEMA_FILE)


def LoadGenericStatement():
  """Loads the config file of the generic probe statement."""
  return LoadStatement(GENERIC_STATEMENT_FILE)


def LoadVolatileStatement():
  """Loads the config file of the volatile probe statement."""
  return LoadStatement(VOLATILE_STATEMENT_FILE)


def EvaluateStatement(statement):
  """Evaluates the function expression and filters it by the rule expression.

  Args:
    statement: a dict containing the probe function and expected result.
      {
        "eval" : <Function expression>,
        "expect" : <Rule expression>
      }

  Returns:
    the probe results.
  """
  probe_func = function.InterpretFunction(statement['eval'])
  match_func = match.MatchFunction(rule=statement.get('expect', {}))
  return match_func(probe_func())
