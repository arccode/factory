# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common # pylint: disable=W0611

from cros.factory.rule import GetLogger, RuleFunction, Value, RuleException

@RuleFunction([])
def Assert(expr):
  """A wrapper method to test assertion.

  Args:
    expr: An expression that should evalute to True or False.

  Raises:
    HWIDException if the given expr does not evaluate to True."""
  if not expr:
    GetLogger().Error('Assertion failed.')


@RuleFunction([])
def Re(expr):
  """A wrapper method to create regular expression Value object.

  Args:
    expr: A string indicating the regular expression.

  Returns:
    A regular expression-enabled Value object.
  """
  return Value(expr, is_re=True)


@RuleFunction([])
def LookupMap(key, mapping):
  """A utility method for looking up value in a map.

  Args:
    key: The key to look up value of.
    mapping: A map object to look up value from. This must be of dict type.

  Returns:
    A value retrieved from the given map object with the given key.

  Raises:
    RuleException: If 'mapping' is not of dict tyep.
    KeyError: If 'key' is not found in 'mapping'.
  """
  if not isinstance(mapping, dict):
    raise RuleException('%r is not a dict' % mapping)
  return mapping[key]
