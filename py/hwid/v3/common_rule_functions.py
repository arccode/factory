# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.hwid.v3.rule import GetLogger
from cros.factory.hwid.v3.rule import RuleException
from cros.factory.hwid.v3.rule import RuleFunction
from cros.factory.hwid.v3.rule import Value


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


@RuleFunction([])
def CallIf(cond, func, *args, **kwargs):
  """A utility function to conditionally call a function.

  Args:
    cond: The conditional variable.
    func: The function to call if cond evaluates to True.
    *args: Positional arguments to pass to func.
    **kwargs: Keyword arguments to pass to func.
  """
  if cond:
    func(*args, **kwargs)
