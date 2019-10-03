# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe import function


class ActionFunction(function.Function):
  """The base class of action functions.

  While evaluation, an action function executes a side-effect action. If the
  action is successfully executed, it returns the input data. Otherwise it
  returns an empty list to notify the computation failed.
  """
  def Apply(self, data):
    if self.Action():
      return data
    return function.NOTHING

  def Action(self):
    """Execute an action and return the action is successfully or not."""
    raise NotImplementedError
