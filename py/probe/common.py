# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The module provides common variables and functions for probe framework.
"""


import os

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.probe.functions import match
from cros.factory.utils import config_utils


GENERIC_STATEMENT_FILE = 'generic_statement'
VOLATILE_STATEMENT_FILE = 'volatile_statement'
GENERIC_STATEMENT_SCHEMA_FILE = 'generic_statement'
STATEMENT_SCHEMA_FILE = 'statement'


def _LoadStatement(config_name):
  """Loads the config file containing the probe statement."""
  return config_utils.LoadConfig(
      config_name, schema_name=GENERIC_STATEMENT_SCHEMA_FILE)


def LoadGenericStatement():
  """Loads the config file of the generic probe statement."""
  return _LoadStatement(GENERIC_STATEMENT_FILE)


def LoadVolatileStatement():
  """Loads the config file of the volatile probe statement."""
  return _LoadStatement(VOLATILE_STATEMENT_FILE)


def LoadUserProbeStatementFile(config_file):
  """Loads the probe statement file specified by the user.

  Args:
    config_file: A string of name of the probe statement (with ext.)

  Returns:
    A json object of probe statements.
  """
  config_name = os.path.splitext(os.path.basename(config_file))[0]
  basedir = os.path.dirname(os.path.abspath(config_file))
  json_obj = config_utils.LoadConfig(
      config_name=config_name, schema_name=STATEMENT_SCHEMA_FILE,
      default_config_dirs=[basedir, config_utils.CALLER_DIR],
      allow_inherit=True)
  return json_obj


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
