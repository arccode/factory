# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe import function
from cros.factory.probe.lib import combination_function
from cros.factory.utils.arg_utils import Arg


class InnerJoin(combination_function.CombinationFunction):
  """Inner join the result of functions.

  Description
  -----------
  ``InnerJoin`` combines the result by finding the same index. For example:
  Combine them by 'idx'::

    [{'idx': '1', 'foo': 'foo1'}, {'idx': '2', 'foo': 'foo2'}]
    [{'idx': '1', 'bar': 'bar1'}, {'idx': '2', 'bar': 'bar2'}]

  becomes::

    [{'idx': '1', 'foo': 'foo1', 'bar': 'bar1'},
     {'idx': '2', 'foo': 'foo2', 'bar': 'bar2'}]

  """
  ARGS = [
      Arg('functions', list, 'The list of the function expression.'),
      Arg('index', str, 'The index name for inner join.')
  ]

  def Combine(self, functions, data):
    idx_set = None
    result_list = []
    for func in functions:
      results = [item for item in func(data) if self.args.index in item]
      if not results:
        return function.NOTHING
      result_map = {result[self.args.index]: result for result in results}
      if idx_set is None:
        idx_set = set(result_map.keys())
      else:
        idx_set &= set(result_map.keys())
      result_list.append(result_map)

    if not idx_set:
      return function.NOTHING
    ret = []
    for idx in idx_set:
      joined_result = {}
      for result_item in result_list:
        joined_result.update(result_item[idx])
      ret.append(joined_result)
    return ret
