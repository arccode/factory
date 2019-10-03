# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe import function
from cros.factory.utils.arg_utils import Arg


class CombinationFunction(function.Function):
  """The base class of combination functions.

  While evaluation, the function first evaluates the functions specified
  in the ``functions`` arguments and then combines the outputs in a certain
  way.
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
