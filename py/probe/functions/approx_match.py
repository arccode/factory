# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe.functions import match
from cros.factory.utils.arg_utils import Arg


class ApproxMatchFunction(match.MatchFunction):
  """Return the items which match the most rules.

  Description
  -----------
  This function is like :ref:`match function <MatchFunction>`, but it returns
  the items that match the most rules when there's no items that match all
  rules.

  Examples
  --------
  There are 5 rules, 5 items and ``max_mismatch = 1`` in the following examples.

  The number of matched rules are ``[0, 1, 2, 3, 4]``,
  this function returns the last item that matches 4 rules.

  The number of matched rules are ``[0, 1, 4, 4, 4]``,
  this function returns the last 3 items that match 4 rules.

  The number of matched rules are ``[0, 0, 0, 0, 0]``,
  this function returns an empty list because there's no items that mismatch
  less equal than 1 rule.

  Result
  ------
  The result is a list which contains the items that match the most rules.

  For each result, the schema is like::

    {
      "perfect_match": a boolean indicating if the item matches all rules,
      "approx_match": {
        "matched_num": number of matched rules,
        "rule": {
          "rule_name": {
            "info": the rule string,
            "result": a boolean indicating if the item matches the rule
          },...
        }
      },
      "values": the probed results
    }
  """

  ARGS = [
      Arg('rule', (str, dict), 'The matched rule.'),
      Arg('max_mismatch', int, 'The number of mismatched rules at most.',
          default=1)]

  def Apply(self, data):
    match_results = self.ApproxMatchFilter(list(map(self.Match, data)))
    return list(map(self.GenerateResult, match_results))

  def Match(self, item):
    def _Match(matcher, value):
      return matcher(value)

    if not self.is_dict:
      matched = len(item) == 1 and _Match(self.rule, next(iter(item.values())))
      matched = {list(item)[0]: matched}
      matched_rule = {key: {'result': value, 'info': self.args.rule}
                      for key, value in matched.items()}
    else:
      matched = {key: key in item and _Match(rule, item[key])
                 for key, rule in self.rule.items()}
      matched_rule = {key: {'result': value, 'info': self.args.rule[key]}
                      for key, value in matched.items()}
    return (all(matched.values()), sum(matched.values()), matched_rule, item)

  def ApproxMatchFilter(self, match_results):
    # Items which match no rules should not be considered as filtered results.
    if not self.is_dict:
      max_matched_num = 1
    else:
      max_matched_num = max(1, len(self.args.rule) - self.args.max_mismatch)
    for _, matched_num, _, _ in match_results:
      max_matched_num = max(max_matched_num, matched_num)

    return [res for res in match_results if res[1] == max_matched_num]

  @classmethod
  def GenerateResult(cls, match_result):
    perfect_match, matched_num, matched_rule, item = match_result
    return {
        'approx_match': {
            'matched_num': matched_num,
            'rule': matched_rule,
        },
        'perfect_match': perfect_match,
        'values': item
    }
