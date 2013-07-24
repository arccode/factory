# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import numpy


def GetStatistic(data):
  """Calculate some statistics of input data.

  Args:
    data: A list of floating numbers.

  Return:
    A dict with keys ['min', 'max', 'avg', 'median', 'stddev'], which has value
    of minimum, maximum, average, median, standard deviation of the input,
    respectively, or 'No Data' if the input list is empty.
  """
  if not data:
    return dict((k, 'No Data')
                for k in ['min', 'max', 'avg', 'median', 'stddev'])
  return {
    'min': min(data),
    'max': max(data),
    'avg': numpy.mean(data),
    'median': numpy.median(data),
    'stddev': numpy.std(data),
  }

