# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Implementation for Agilent ENA Series Network Analyzer (E5071C) device.
"""

# TODO(itspeter): write unittest and verify it on a real E5071C

import bisect
import itertools
import logging
import urllib.request

from cros.factory.test.rf import agilent_scpi
from cros.factory.test.rf import lan_scpi
from cros.factory.utils import type_utils


def CheckTraceValid(x_values, y_values):
  """Checks validity of trace.

  Raises an exception if x_values and y_values cannot form a valid trace.

  Args:
    x_values: A list of X values.
    y_values: A list of Y values.

  Raises:
    ValueError:
      (1) x_values is empty.
      (2) x_values is not an increasing sequence.
      (3) len(x_values) != len(y_values).
  """
  if not x_values:
    raise ValueError('Parameter x_values is empty')
  if len(x_values) != len(y_values):
    raise ValueError('Parameter x_values and y_values are not equal in length')
  if not all(x <= y for x, y in zip(x_values, x_values[1:])):
    raise ValueError('Parameter x_values is not an increasing sequence')


def Interpolate(x_values, y_values, x_position):
  """Interpolates y-values.

  Returns an interpolated (linear) y-value at x_position.

  This function is especially designed for interpolating values from a
  Network Analyzer. It happens in practice that x_values will have
  sorted, duplicated values. In addition, y_values may be different for
  identical x value. The function behavior under this situation is as follows:
      (1) The function finds a right sentinel for interpolating, which is the
          smallest index that less of equal to the x_position.
      (2) If it is exactly the x_position, returns the y_value.
      (3) Otherwise, interpolate values as the left sentinel is just the
          one before right sentinel.
  Example used in the unittest elaborates more on this.

  Args:
    x_values: A list of X values.
    y_values: A list of Y values.
    x_position: The position where we want to interpolate.

  Returns:
    Interpolated value. For example:
    Interpolate([10, 20], [0, 10], 15) returns 5.0

  Raises:
    ValueError:
      (1) x_position is not in the range of x_values.
      (2) Arguments failed to pass CheckTraceValid().
  """
  CheckTraceValid(x_values, y_values)

  # Check if the x_position is inside some interval in the trace
  if x_position < x_values[0] or x_position > x_values[-1]:
    raise ValueError(
        'x_position is not in the current range of x_values[%s,%s]' %
        (x_values[0], x_values[-1]))

  # Binary search where to interpolate the x_position
  right_index = bisect.bisect_left(x_values, x_position)
  if x_position == x_values[right_index]:
    return y_values[right_index]

  # Interpolate the value according to the x_position
  delta_interval = ((x_position - x_values[right_index - 1]) /
                    (x_values[right_index] - x_values[right_index - 1]))
  return (y_values[right_index - 1] +
          (y_values[right_index] - y_values[right_index - 1]) * delta_interval)


class Traces:

  def __init__(self):
    self.parameters = None
    self.x_axis = None
    self.traces = {}

  def __repr__(self):
    """Returns a representation of the object, including its properties."""
    return (self.__class__.__name__ + '(' +
            ', '.join('%s=%s' % (k, repr(getattr(self, k)))
                      for k in sorted(self.__dict__.keys())
                      if k[0] != '_')
            + ')')

  def GetFreqResponse(self, freq, parameter):
    """Returns corresponding frequency response.

    Returns corresponding frequency response given the parameter.
    If the particular frequency was not sampled, uses linear
    interpolation to estimate the response.

    Args:
      freq: The frequency we want to obtain from the traces.
      parameter: One of the parameters provided in
          ENASCPI.PARAMETERS.

    Returns:
      A floating point value in dB at freq.
    """
    if parameter not in self.traces:
      raise lan_scpi.Error('No trace available for parameter %s' % parameter)
    return Interpolate(self.x_axis, self.traces[parameter], freq)


class ENASCPI(agilent_scpi.AgilentSCPI):
  """An Agilent ENA (E5071C) device."""
  PARAMETERS = type_utils.Enum(['S11', 'S12', 'S21', 'S22'])

  def __init__(self, *args, **kwargs):
    # The first few commands need some warm up time in real E5071C based
    # on experimental result. Pass the timeout arguement so initialization
    # will be a success.
    kwargs_copy = dict(kwargs)
    kwargs_copy.setdefault('timeout', 10)
    super(ENASCPI, self).__init__('E5071C', *args, **kwargs_copy)

  def SaveScreen(self, filename):
    """Saves the screenshot.

    Saves the current screen to a portable network graphics (PNG) file.
    The default store path in E5071C is under disk D.
    """
    self.Send(':MMEMory:STORe:IMAGe "%s.png"' % filename)

  def SetMarker(self, channel, marker_num, marker_freq):
    """Sets the marker at channel.

    The marker will only be showed if it is checked on the ENA already.
    This function is used to set marker position, not to enable markers.

    Example usage:
      Set marker 5 to 600MHz on channel 1.
      SetMarker(1, 5, 600*1e6)
    """
    # TODO(itspeter): understand why channel doesn't make a difference.

    # http://ena.tm.agilent.com/e5061b/manuals/webhelp/eng/
    # programming/command_reference/calculate/scpi_calculate
    # _ch_selected_marker_mk_x.htm#Syntax

    #:CALCulate{[1]-4}[:SELected]:MARKer{[1]-10}:X <numeric>
    buffer_str = ':CALCulate%d:SELected:MARKer%d:X %f' % (
        channel, marker_num, float(marker_freq))
    self.Send(buffer_str)

  def SetLinearSweep(self, min_freq, max_freq):
    """Sets linear sweep mode.

    Sets the mode to be a linear sweep between min_freq and max_freq.

    Args:
      min_freq: The minimum frequency in Hz.
      max_freq: The maximum frequency in Hz.
    """
    self.Send([':SENS:SWEep:TYPE LINear',
               ':SENS:FREQ:STAR %d' % min_freq,
               ':SENS:FREQ:STOP %d' % max_freq])

  def SetSweepSegments(self, segments):
    """Sets a collection of sweep segments.

    Args:
      segments: An array of 3-tuples.  Each tuple is of the
          form (min_freq, max_freq, points) as follows:

          min_freq: The segment's minimum frequency in Hz.
          max_freq: The segment's maximum frequency in Hz.
          points: The number of points in the segment.

          The frequencies must be monotonically increasing.
    """
    # Check that the segments are all 3-tuples and that they are
    # in increasing order of frequency.
    for i, segment in enumerate(segments):
      # pylint: disable=unused-variable
      min_freq, max_freq, pts = segment
      assert max_freq >= min_freq
      if i < len(segments) - 1:
        assert segments[i + 1][0] >= min_freq

    data = [
        5,              # Magic number from the device documentation
        0,              # Stop/stop values
        0,              # No per-segment IF bandwidth setting
        0,              # No per-segment sweep delay setting
        0,              # No per-segment sweep mode setting
        0,              # No per-segment sweep time setting
        len(segments),  # Number of segments
    ] + list(sum(segments, ()))
    self.Send([':SENS:SWEep:TYPE SEGMent',
               (':SENS:SEGMent:DATA %s' %
                ','.join(str(x) for x in data))])

  def GetTraces(self, parameters):
    """Collects a set of traces based on the current sweep.

    Returns:
      A Traces object containing the following attributes:
        x_axis: An array of X-axis values.
        traces: A map from each parameter name to an array
            of values for that trace.

    Example Usage:
      ena.set_linear_sweep(700e6, 2200e6)
      data = ena.get_traces(['S11', 'S12', 'S22'])
      print zip(data.x_axis, data.traces['S11'])
    """
    assert parameters
    assert len(parameters) <= 4

    commands = [':CALC:PAR:COUN %d' % len(parameters)]
    for i, p in zip(itertools.count(1), parameters):
      commands.append(':CALC:PAR%d:DEF %s' % (i, p))
    self.Send(commands)

    ret = Traces()
    ret.parameters = parameters
    ret.x_axis = self.Query(':CALC:SEL:DATA:XAX?', lan_scpi.FLOATS)
    ret.traces = {}
    # Force the FDATA to be updated immediatedly.
    self.Send(':INITiate1:CONTinuous OFF')
    self.Send(':INITiate1:IMMediate')
    for i, p in zip(itertools.count(1), parameters):
      ret.traces[p] = (
          self.Query(':CALC:TRACE%d:DATA:FDAT?' % i, lan_scpi.FLOATS)[0::2])
      if len(ret.x_axis) != len(ret.traces[p]):
        raise lan_scpi.Error('x_axis has %d elements but trace has %d' %
                             (len(ret.x_axis), len(ret.traces[p])))
      CheckTraceValid(ret.x_axis, ret.traces[p])
    # Unfreeze the trace.
    self.Send(':INITiate1:CONTinuous ON')
    return ret

  def CheckCalibration(self, min_frequency, max_frequency, sample_points,
                       min_threshold, max_threshold):
    """Checks if the trace is as flat as expected.

    This function uniformly samples "sample_points" from the ENA between
    [min_frequency, max_frequency], and checks if the response values on all
    these points are between [min_threshold, max_threshold].

    Args:
      min_frequency: a Frequency instance indicating the minimum frequency.
      max_frequency: a Frequency instance indicating the maximum frequency.
      sample_points: an int indicating how many points to sample.
      min_threshold: a float indicating the lowest threshold.
      max_threshold: a float indicating the highest threshold.

    Returns:
      A tuple. The 1st element is True if the values of all sample points
      between [min_frequency, max_frequency] are between [min_threshold,
      max_threshold], otherwise, False. The 2nd element is the trace data
      obtained by the ENA.
    """
    logging.info(
        'Checking calibration from %.2f to %.2f with threshold (%f, %f)...',
        min_frequency.Hzf(), max_frequency.Hzf(), min_threshold, max_threshold)

    self.SetSweepSegments([(
        min_frequency.Hzf(), max_frequency.Hzf(), sample_points)])
    TRACES_TO_CHECK = ['S11', 'S22']
    traces = self.GetTraces(TRACES_TO_CHECK)

    calibration_check_passed = True
    for trace_name in TRACES_TO_CHECK:
      trace_data = traces.traces[trace_name]
      for index, freq in enumerate(traces.x_axis):
        if not min_threshold <= trace_data[index] <= max_threshold:
          # Do not stop, continue to find all failing parts.
          logging.info(
              'Calibration check failed at %s-%15.2f', trace_name, freq)
          calibration_check_passed = False

    if calibration_check_passed:
      return (True, traces)
    return (False, traces)

  def CaptureScreenshot(self):
    """Return the screenshot content in PNG format."""
    # Save a screenshot copy in ENA.
    self.SaveScreen('screenshot')

    # The SaveScreen above has saved a screenshot inside ENA, but it does not
    # allow reading that file directly (see SCPI protocol for details). To save
    # a copy locally, we need to make another screenshot using ENA's HTTP
    # service (image.asp) which always puts the file publicly available as
    # "disp.png".
    urllib.request.urlopen('http://%s/image.asp' % self.host).read()
    return urllib.request.urlopen('http://%s/disp.png' % self.host).read()
