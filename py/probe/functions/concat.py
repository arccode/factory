# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.lib import combination_function


class Concat(combination_function.CombinationFunction):
  """Returns the concatenation of output.

  Description
  -----------
  Concat the outputs of the functions.
  The type of all the outputs of functions must be a list.
  The concept is::

    res = []
    res.extend(Func1(data))
    res.extend(Func2(data))
    ...

  """
  def Combine(self, functions, data):
    res = []
    for func in functions:
      ret = func(data)
      if not isinstance(ret, list):
        raise TypeError
      res.extend(ret)
    return res
