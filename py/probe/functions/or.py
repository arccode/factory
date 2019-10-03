# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe import function
from cros.factory.probe.lib import combination_function


class Or(combination_function.CombinationFunction):
  """Returns the first successful output.

  Description
  -----------
  The concept is::

    output = Func1(data) or Func2(data) or ...
  """
  def Combine(self, functions, data):
    for func in functions:
      ret = func(data)
      if ret:
        return ret
    return function.NOTHING
