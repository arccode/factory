# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re

from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


class MatchFunction(function.Function):
  """Filter the results which does not match the rule.

  Description
  -----------
  The rule might be a dict or a string. A result is matched if every value of
  the rule is matched. If the rule is a string, then the matched result should
  only contain one item and the value is matched to the string.

  If the string starts with ``!re``, then the remaining string is treated as a
  regular expression.

  If the string starts with ``!num``, the probed value will be treated as
  floating point number, and the remaining of rule string should be
  ``< '==' | '>' | '<' | '>=' | '<=' | '!=' > ' ' NUMBER``, e.g.
  ``!num >= 10``.

  Otherwise, the value of the result should be the same.

  Examples
  --------
  This function is used by the probe framework itself to filter the outputs
  of the evaluated functions by ``expect`` field in the probe statement.
  Below is a probe statement which simply asks the probe framework to output
  all usb devices::

    {
      "eval": "usb"
    }

  Let's assume the probed output is::

    [
      {
        "idVendor": "01ab",
        "idProduct": "1122",
        ...
      },
      {
        "idVendor": "01ac",
        "idProduct": "3344",
        ...
      },
      {
        "idVendor": "23cd",
        "idProduct": "3344",
        ...
      }
    ]

  If we modify the probe statement to::

    {
      "eval": "usb",
      "expect": {
        "idVendor": "01ab"
      }
    }

  , then the probed results will become::

    [
      {
        "idVendor": "01ab",
        "idProduct": "1122",
        ...
      }
    ]

  We can also use the regular expression described in above.  For example,
  if we modify ``expect`` field in the probe statement to::

    "expect": {
      "idVendor": "!re ^01.*$"
    }

  , then the probed results will contain both the item with ``idVendor=01ab``
  and the item with ``idVendor=01ac``.
  """

  REGEX_PREFIX = '!re'
  NUM_CMP_PREFIX = '!num'
  NUM_CMP_OPERATOR = {
      '==': lambda a, b: a == b,
      '>': lambda a, b: a > b,
      '<': lambda a, b: a < b,
      '>=': lambda a, b: a >= b,
      '<=': lambda a, b: a <= b,
      '!=': lambda a, b: a != b,
  }

  ARGS = [
      Arg('rule', (str, dict), 'The matched rule.')]

  def __init__(self, **kwargs):
    super(MatchFunction, self).__init__(**kwargs)

    self.is_dict = isinstance(self.args.rule, dict)
    if self.is_dict:
      self.rule = {key: self.ConstructRule(value)
                   for key, value in self.args.rule.items()}
    else:
      self.rule = self.ConstructRule(self.args.rule)

  def Apply(self, data):
    results = list(filter(self.Match, data))
    return [{'values': res} for res in results]

  def Match(self, item):
    def _Match(matcher, value):
      return matcher(value)

    if not self.is_dict:
      return len(item) == 1 and _Match(self.rule, next(iter(item.values())))
    return all([key in item and _Match(rule, item[key])
                for key, rule in self.rule.items()])

  @classmethod
  def ConstructRule(cls, rule):
    assert isinstance(rule, str)

    transformers = {
        cls.REGEX_PREFIX: cls.TryTransferRegex,
        cls.NUM_CMP_PREFIX: cls.TryTransferNumberCompare,
    }

    prefix, unused_sep, rest = rule.partition(' ')
    if prefix in transformers:
      return transformers[prefix](rest)
    return lambda v: v == rule

  @classmethod
  def TryTransferRegex(cls, value):
    regexp = re.compile(value)
    def matcher(v):
      try:
        return regexp.match(v) is not None
      except TypeError:
        return False
    return matcher

  @classmethod
  def TryTransferNumberCompare(cls, value):
    op, unused_sep, num = value.partition(' ')
    num = float(num)
    if op not in cls.NUM_CMP_OPERATOR:
      raise ValueError('invalid operator %s' % op)
    def matcher(v):
      try:
        v = float(v)
      except ValueError:
        return False
      return cls.NUM_CMP_OPERATOR[op](v, num)
    return matcher
