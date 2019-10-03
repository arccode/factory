# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy

from cros.factory.probe import function


class ProbeFunction(function.Function):
  """The base class of probe functions.

  While evaluation, the function probes the result, and update to the input
  data by the probed results. If there are multiple probed results, the output
  list contains all the combination of the input and the probed data.
  """
  def Apply(self, data):
    results = self.Probe()
    if results is None:
      results = []
    elif not isinstance(results, list):
      results = [results]

    ret = []
    for result in results:
      for item in data:
        new_item = copy.copy(item)
        new_item.update(result)
        ret.append(new_item)
    return ret

  def Probe(self):
    """Return the probe result. It can be a dict or a list of dict."""
    raise NotImplementedError
