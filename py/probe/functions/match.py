# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


class MatchFunction(function.Function):
  """Filter the results which does not match the rule.

  The rule might be a dict or a string. A result is matched if every value of
  the rule is matched. If the rule is a string, then the matched result should
  only contain one item and the value is matched to the string.

  If the string starts with "!re ", then the remaining string is treated as a
  regular expression. Otherwise, the value of the result should be the same.
  """

  RE_TYPE = type(re.compile(''))
  REGEX_PREFIX = '!re '
  ARGS = [
      Arg('rule', (str, dict), 'The matched rule.')]

  def __init__(self, **kwargs):
    super(MatchFunction, self).__init__(**kwargs)

    self.is_dict = isinstance(self.args.rule, dict)
    if self.is_dict:
      self.args.rule = {key: self.TryTransferRegex(value)
                        for key, value in self.args.rule.iteritems()}
    else:
      self.args.rule = self.TryTransferRegex(self.args.rule)

  def Apply(self, data):
    return filter(self.Match, data)

  def Match(self, item):
    def _Match(rule, value):
      if isinstance(rule, self.RE_TYPE):
        try:
          return rule.match(value) is not None
        except TypeError:
          return False
      else:
        return rule == value

    if not self.is_dict:
      return len(item) == 1 and _Match(self.args.rule, item.values()[0])
    else:
      return all([key in item and _Match(rule, item[key])
                  for key, rule in self.args.rule.iteritems()])

  @classmethod
  def TryTransferRegex(cls, value):
    assert isinstance(value, str)
    if value.startswith(cls.REGEX_PREFIX):
      return re.compile(value[len(cls.REGEX_PREFIX):])
    return value
