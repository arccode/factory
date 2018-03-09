# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


class CombinationFunction(function.Function):
  """The base class of combination functions.

  The argument of combination function is a list of the function expressions.
  The combination function combine the output of the functions in a certain way.
  """
  ARGS = [
      Arg('functions', list, 'The list of the function expression.')
  ]

  def __init__(self, **kwargs):
    super(CombinationFunction, self).__init__(**kwargs)
    # Interpret the function expressions to function instances.
    self.functions = [
        function.InterpretFunction(func) for func in self.args.functions]

  def Apply(self, data):
    return self.Combine(self.functions, data)

  def Combine(self, functions, data):
    raise NotImplementedError
