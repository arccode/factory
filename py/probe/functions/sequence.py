# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.lib import combination_function


class Sequence(combination_function.CombinationFunction):
  """Sequential execute the functions.

  The input of the next function is the output of the previous function.
  The concept is:
    data = Func1(data)
    data = Func2(data)
    ...
  """
  def Combine(self, functions, data):
    for func in functions:
      data = func(data)
    return data
