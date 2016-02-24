# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""WiFi throughput test.

Accepts a list of wireless services, checks for their signal strength,
connects to them, and tests data throughput rate using iperf3.

One notable difference about this test is how it processes arguments:
  1. Each service configuration must provide two required arguments "ssid"
     and "password".
  2. If a service configuration does not provide an argument, it defaults
     to the "test-level" argument.
  3. If it was not provided as a "test-level" argument, it takes the
     default value passed to the Arg() constructor.

Here's an example of input arguments::

  ARGS={
      "event_log_name": "wifi_throughput_in_chamber",
      "services": [
          {
            "ssid": "ap",
            "password": "pass1",
            "min_rx_throughput": 80,
          },
          {
            "ssid": "ap_5g",
            "password": "pass2",
            "min_signal_strength": 40,
          }
      ],
      "min_signal_strength": 20,
      "iperf_host": "10.0.0.1",
      "min_tx_throughput": 100,
  }

After processing, each service would effectively have a configuration that
looks like this::

  ARGS={
      "event_log_name": "wifi_throughput_in_chamber",
      "services": [
          {
            "ssid": "ap",
            "password": "pass1",
            "min_signal_strength": 20, # inherited from test-level arg
            "iperf_host": "10.0.0.1",  # inherited from test-level arg
            "min_tx_throughput": 100,  # inherited from test-level arg
            "min_rx_throughput": 80,
          },
          {
            "ssid": "ap_5g",
            "password": "pass2",
            "min_signal_strength": 40, # blocks test-level arg
            "iperf_host": "10.0.0.1",  # inherited from test-level arg
            "min_tx_throughput": 100,  # inherited from test-level arg
          }
      ],
  }
"""

from __future__ import print_function

import json
import logging
import os
import string  # pylint: disable=W0402
import sys
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import dut
from cros.factory.test import event_log
from cros.factory.test import factory, leds
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test.args import Arg, Args
from cros.factory.test.fixture import arduino
from cros.factory.test.ui_templates import OneSection
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import service_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


# pylint: disable=W0611, F0401
import cros.factory.test.autotest_common
from autotest_lib.client.cros.networking import wifi_proxy
# pylint: enable=W0611, F0401


_SERVICE_LIST = ['shill', 'shill_respawn', 'wpasupplicant', 'modemmanager']
_WIFI_TIMEOUT_SECS = 20
_DEFAULT_POLL_INTERVAL_SECS = 1
_IPERF_TIMEOUT_SECS = 5

_DEFAULT_WIRELESS_TEST_CSS = '.wireless-info {font-size: 2em;}'

_MSG_SPACE = test_ui.MakeLabel(
    'Please wait for other DUTs to finish WiFiThroughput test, '
    'and press spacebar to continue.',
    u'请等其它的 DUT 完成测试後按空白键继续。',
    'wireless-info')
_MSG_RUNNING = test_ui.MakeLabel(
    'Running, please wait...',
    u'测试中，请稍後。', 'wireless-info')


def _BitsToMbits(x):
  return x / (10.0 ** 6)


def _BytesToMbits(x):
  return _BitsToMbits(x * 8)


class Iperf3(object):
  """Wraps around spawning the iperf3 command.

  Allows running the iperf3 command and checks its resulting JSON dict for
  validity.
  """
  ERROR_MSG_BUSY = 'error - the server is busy running a test. try again later'
  DEFAULT_TRANSMIT_TIME = 5
  DEFAULT_TRANSMIT_INTERVAL = 1
  # Wait (transmit_time + _TIMEOUT_KILL_BUFFER) before killing iperf3.
  _TIMEOUT_KILL_BUFFER = 5

  def InvokeClient(
      self, server_host, bind_ip=None,
      transmit_time=DEFAULT_TRANSMIT_TIME,
      transmit_interval=DEFAULT_TRANSMIT_INTERVAL,
      reverse=False):
    """Invoke iperf3 and return its result.

    Args:
      server_host: Host of the machine running iperf3 server. Can optionally
          include a port in the format '<server_host>:<server_port>'.
      bind_ip: Local IP address to bind to when opening a connection to the
          server.  If provided, this should correspond to the IP address of the
          device through which the server can be accessed (e.g. eth0 or wlan0).
          If iperf3 can connect through any device, None or '0.0.0.0' should be
          provided.
      transmit_time: Time in seconds for which to transmit data.
      transmit_interval: Interval in seconds by which to split iperf3 results.
          Assuming nothing goes wrong, there will be ceil(transmit_time / n)
          intervals reported.
      reverse:
          False transfers data from the the client to the server.
          True transfers data from the server to the client.

    Returns:
      A dict representing the JSON-parsed result output from iperf3.  If an
      'error' key exits, the validity of results cannot be guaranteed.  If an
      'error' key does not exist, there are guaranteed to be more than one
      interval reported, with all intervals containing non-zero transfer sizes
      and speeds.

      Note that iperf3 allows you to test data with multiple connections
      simultaneously.  We only use one connection, so in the example output
      below, the "streams" keys are ignored, and we use "sum" and "sum_sent"
      instead.

      Example of data returned for a 5-second run with 1-second intervals
      (with much data omitted):
        {
          "intervals":  [{
              "streams": [{ ... }, { ... }]
              "sum":  {
                "start":  0,
                "end":  1.00006,
                "seconds":  1.00006,
                "bytes":  11863464,
                "bits_per_second":  9.49017e+07,
              }
            },
            # ... more intervals ...
            ],
          "end":  {
            "streams": [{ ... }, { ... }]
            "sum_sent":  {
              "start":  0,
              "end":  5.00002,
              "seconds":  5.00002,
              "bytes":  59074056,
              "bits_per_second":  9.4518e+07,
            },
          }
        }
    """
    if ':' in server_host:
      server_host, server_port = server_host.split(':')
      host_args = ['--client', server_host, '--port', server_port]
    else:
      host_args = ['--client', server_host]
    iperf_cmd = ['iperf3'] + host_args + [
        '--time', str(transmit_time),
        '--interval', str(transmit_interval),
        '--json']
    if reverse:
      iperf_cmd.append('--reverse')
    if bind_ip:
      iperf_cmd.extend(['--bind', bind_ip])

    # We enclose the iperf3 call in timeout, since when given an unreachable
    # host, hangs for an inacceptably long period of time.  TERM causes iperf3
    # to quit, but it will still output the following error:
    #
    #   "interrupt - the client has terminated"
    #
    # (In older versions, the process just ends without any output.  So we
    # emulate this behaviour for the convenience of the caller in the
    # try/catch exception below.)
    timeout_cmd = [
        'timeout',
        '--signal', 'TERM',
        # Add _TIMEOUT_KILL_BUFFER seconds to allow for process overhead and
        # connection time.
        str(transmit_time + self._TIMEOUT_KILL_BUFFER)] + iperf_cmd

    logging.info(
        'Running iperf3 connecting to host %s for %d seconds',
        server_host, transmit_time)

    try:
      output = process_utils.SpawnOutput(timeout_cmd, log=True)
      logging.info(output)
      json_output = json.loads(output)

      # Basic sanity checks before return.
      return self._CheckOutput(json_output)
    except Exception:
      return {'error': 'interrupt - the client has terminated'}

  def _CheckOutput(self, output):
    """Ensure that output dict passes some basic sanity checks."""

    # If there are errors, we should not check for output validity.
    if 'error' in output:
      return output

    # Check that there is one or more interval.
    if 'intervals' not in output:
      output['error'] = 'output error - no intervals'
      return output

    # Ensure each interval is valid.
    for interval in output['intervals']:
      # 'sum' key exists
      if not interval.get('sum'):
        output['error'] = 'output error - no interval sum'
        return output

      # bytes > 0 and bits_per_second > 0
      if (interval['sum']['bytes'] <= 0
          or interval['sum']['bits_per_second'] <= 0):
        output['error'] = 'output error - non-zero transfer'
        return output

    # No problems with output!
    return output


class _ServiceTest(object):
  """Collection of tests to be run on each service.

  Provides a "flow" mechanism for tests to be run on each service, with the
  overall control in the self.Run method.  Takes care of utility objects,
  carrying forward state, and logging to factory console.

  Each test should be contained within a method.  If the test passes, it should
  return None or optionally a string containing a success message.  If the test
  fails, it should throw a self._TestException with a description of the error.

  E.g. _Find(ssid) looks for the existence of a particular SSID.
    If it exists, this string will be returned:
      'Found service %s' % ssid
    If it does not exist, this exception will be thrown:
      self._TestException('Unable to find service %s' % ssid)
  """
  class _TestException(Exception):
    pass

  # Utility objects that most tests will make use of.
  _wifi = None
  _iperf3 = None
  _ui = None
  _bind_wifi = None

  # State to be carried along from test to test.
  _ap_config = None
  _service = None
  _log = None

  def __init__(self, wifi, iperf3, ui, bind_wifi):
    self._wifi = wifi
    self._iperf3 = iperf3
    self._ui = ui
    self._bind_wifi = bind_wifi

  def _Log(self, text, *args):
    f_name = sys._getframe(1).f_code.co_name  # pylint: disable=W0212
    factory.console.info('[%s] INFO [%s] ' + text,
                         self._ap_config.ssid, f_name, *args)

  def Run(self, ap_config):
    """Controls the overall flow of the service's tests.

    Tests are called by passing a class method into DoTest with the method's
    corresponding arguments.

    Here is an example of how flow is controlled:
        try:
          DoTest(self._Test1, ...)        # if fails, will continue
          DoTest(self._Test2, abort=True) # if fails, will not execute _Test3
          DoTest(self._Test3, ...)        # if fails, will continue
        except:
          return self._log # next try/except block depends on this one's success
          pass             # OR: next try/except block should be executed anyway

    Args:
      ap_config: The configuration dict for testing this particular service.
          E.g. ssid, password, min_signal_strength, transmit_time

    Returns:
      A log representing the result of testing this service.  The log's
      structure is described at the beginning of the method.
    """
    self._ap_config = ap_config
    self._log = {
        'ifconfig': None,
        'iwconfig': None,
        'ap': None,
        'iperf_tx': None,
        'iperf_rx': None,
        'pass_signal_strength': None,
        'pass_iperf_tx': None,
        'pass_iperf_rx': None,
        'failures': []}

    def DoTest(fn, abort=False, **kwargs):
      """Runs a test and reports its success/failure to the factory console.

      Args:
        fn: Reference to function to be run.
        abort: Whether or not to pass the function's raised exception through to
            DoTest's caller.
        kwargs: Arguments to pass into the test function.

      Raises:
        Exception iff abort == True and fn(...) raises exception.
      """
      try:
        logging.info('running %s(**kwargs=%s)', fn.__name__, kwargs)
        status = fn(**kwargs)
        if status:
          factory.console.info('[%s] PASS [%s] %s',
                               ap_config.ssid, fn.__name__, status)
      except self._TestException as e:
        e.message = '[%s] FAIL [%s] %s' % (
            ap_config.ssid, fn.__name__, e.message)
        self._log['failures'].append(e.message)
        factory.console.error(e.message)
        if abort:
          raise e

    # Try connecting to the service.  If we can't connect, then don't log
    # connection details, and abort this service's remaining tests.
    try:
      DoTest(self._Find, abort=True,
             ssid=ap_config.ssid)

      DoTest(self._CheckSignalStrength,
             min_signal_strength=ap_config.min_signal_strength)

      DoTest(self._Connect, abort=True,
             ssid=ap_config.ssid,
             password=ap_config.password)

      DoTest(self._LogConnection)
    except self._TestException:
      return self._log  # if can't connect, short-circuit and return

    # Try running iperf3 on this service, for both TX and RX.  If it succeeds,
    # check the throughput speed against its minimum threshold.
    for reverse, tx_rx, min_throughput in [
        (False, 'TX', ap_config.min_tx_throughput),
        (True, 'RX', ap_config.min_rx_throughput)]:
      try:
        DoTest(self._RunIperf, abort=True,
               iperf_host=ap_config.iperf_host,
               bind_wifi=self._bind_wifi,
               reverse=reverse,
               tx_rx=tx_rx,
               log_key=('iperf_%s' % tx_rx.lower()),
               transmit_time=ap_config.transmit_time,
               transmit_interval=ap_config.transmit_interval)

        DoTest(self._CheckIperfThroughput, abort=True,
               tx_rx=tx_rx,
               log_key=('iperf_%s' % tx_rx.lower()),
               log_pass_key=('pass_iperf_%s' % tx_rx.lower()),
               min_throughput=min_throughput)
      except self._TestException:
        pass  # continue to next test (TX/RX)

    # Need to return service's log state.
    return self._log

  def _Find(self, ssid):
    # Manually request a scan of WiFi services.
    self._wifi.manager.RequestScan('wifi')

    # Look for requested service.
    self._Log('Trying to connect to service %s...', ssid)
    try:
      self._service = sync_utils.PollForCondition(
          poll_method=lambda: self._wifi.find_matching_service({
              self._wifi.SERVICE_PROPERTY_TYPE: 'wifi',
              self._wifi.SERVICE_PROPERTY_NAME: ssid}),
          timeout_secs=_WIFI_TIMEOUT_SECS,
          poll_interval_secs=_DEFAULT_POLL_INTERVAL_SECS,
          condition_name='Looking for service %s...' % ssid)
    except Exception:
      raise self._TestException('Unable to find service %s' % ssid)
    return 'Found service %s' % ssid

  def _CheckSignalStrength(self, min_signal_strength):
    # Check signal strength.
    if min_signal_strength is not None:
      strength = self._wifi.get_dbus_property(self._service, 'Strength')
      self._log['pass_signal_strength'] = (strength >= min_signal_strength)
      if not self._log['pass_signal_strength']:
        raise self._TestException(
            'strength %d < %d [fail]' % (strength, min_signal_strength))
      else:
        return 'strength %d >= %d [pass]' % (strength, min_signal_strength)

  def _Connect(self, ssid, password):
    # Manually request a scan of WiFi services.
    self._wifi.manager.RequestScan('wifi')

    # Check for connection state.
    is_active = self._wifi.get_dbus_property(self._service, 'IsActive')
    if is_active:
      raise self._TestException('Unexpectedly already connected to %s' % ssid)

    # Try connecting.
    self._Log('Connecting to %s...', ssid)
    security_dict = {
        self._wifi.SERVICE_PROPERTY_PASSPHRASE: password}
    (success, _, _, _, reason) = self._wifi.connect_to_wifi_network(
        ssid=ssid,
        security=('psk' if password else 'none'),
        security_parameters=(security_dict if password else {}),
        save_credentials=False,
        autoconnect=False,
        discovery_timeout_seconds=_WIFI_TIMEOUT_SECS,
        association_timeout_seconds=_WIFI_TIMEOUT_SECS,
        configuration_timeout_seconds=_WIFI_TIMEOUT_SECS)
    if not success:
      raise self._TestException('Unable to connect to %s: %s' % (ssid, reason))
    else:
      return 'Successfully connected to %s' % ssid

  def _LogConnection(self):
    # Show ifconfig and iwconfig output.
    self._log['ifconfig'] = process_utils.SpawnOutput(
        ['ifconfig'], check_call=True, log=True)
    logging.info(self._log['ifconfig'])
    self._log['iwconfig'] = process_utils.SpawnOutput(
        ['iwconfig'], check_call=True, log=True)
    logging.info(self._log['iwconfig'])

    # Save network ssid details.
    self._log['ap'] = {
        'ssid': self._wifi.get_dbus_property(self._service, 'Name'),
        'security': self._wifi.get_dbus_property(self._service, 'Security'),
        'strength': self._wifi.get_dbus_property(self._service, 'Strength'),
        'bssid': self._wifi.get_dbus_property(self._service, 'WiFi.BSSID'),
        'frequency': self._wifi.get_dbus_property(
            self._service, 'WiFi.Frequency')}
    return 'Saved connection information'

  def _RunIperf(
      self, iperf_host, bind_wifi, reverse, tx_rx, log_key,
      transmit_time, transmit_interval):

    # Determine the IP address to bind to (in order to prevent the test from
    # running on a wired device).
    if bind_wifi:
      bind_dev = net_utils.GetWLANInterface()
      bind_ip = net_utils.GetEthernetIp(bind_dev)
      logging.info('%s binding to %s on device %s', tx_rx, bind_ip, bind_dev)

    # Invoke iperf3.  If another client is currently running a test, wait
    # indefinitely, asking the user to press space bar to try again.  If any
    # other error message is received, try again over the period of
    # _IPERF_TIMEOUT_SECS.
    log_msg = '%s running iperf3 on %s (%s seconds)...' % (
        tx_rx, iperf_host, transmit_time)
    self._Log(log_msg)
    while True:
      try:
        iperf_output = sync_utils.PollForCondition(
            poll_method=lambda: self._iperf3.InvokeClient(
                server_host=iperf_host,
                bind_ip=bind_ip if bind_wifi else None,
                reverse=reverse,
                transmit_time=transmit_time,
                transmit_interval=transmit_interval),
            condition_method=lambda x: (
                # Success if no error, or if non-busy error.
                ('error' not in x) or
                (x.get('error') == Iperf3.ERROR_MSG_BUSY)),
            timeout_secs=_IPERF_TIMEOUT_SECS,
            poll_interval_secs=_DEFAULT_POLL_INTERVAL_SECS,
            condition_name=log_msg)
      except type_utils.TimeoutError as e:
        iperf_output = e.output

      if iperf_output.get('error') == Iperf3.ERROR_MSG_BUSY and self._ui:
        self._Log('%s iperf3 error: %s', tx_rx, iperf_output.get('error'))
        self._Log('iperf3 server is currently busy running a test, please wait '
                  'for it to finish and try again.')
        self._Log('Hit space bar to retry...')
        self._ui.PromptSpace()
        time.sleep(1)
      else:
        break

    # Save output.
    self._log[log_key] = iperf_output

    # Show any errors from iperf, but only fail if NO intervals.
    if 'error' in iperf_output:
      error_msg = '%s iperf3 error: %s' % (tx_rx, iperf_output['error'])
      if 'intervals' not in iperf_output:
        raise self._TestException(error_msg)
      else:
        self._Log(error_msg)

    # Count, print, and log number of zero-transfer intervals.
    throughputs = [
        x['sum']['bits_per_second'] for x in iperf_output['intervals']]
    throughputs_string = ' '.join(
        ['%d' % _BitsToMbits(x) for x in throughputs])
    self._Log('%s iperf throughputs (Mbits/sec): %s' % (
        tx_rx, throughputs_string))
    num_zero_throughputs = len([x for x in throughputs if x == 0])
    self._log[log_key]['num_zero_throughputs'] = num_zero_throughputs

    # Test for success based on number of intervals transferred.
    min_intervals = transmit_time / transmit_interval
    if len(iperf_output['intervals']) < min_intervals:
      raise self._TestException(
          '%s iperf3 intervals too few: %d (expected %d)' % (
              tx_rx, len(iperf_output['intervals']), min_intervals))

    else:
      # Show information about the data transferred.
      iperf_avg = iperf_output['end']['sum_sent']
      return (
          '%s transferred: %.2f Mbits, time spent: %d sec, '
          'throughput: %.2f Mbits/sec' % (
              tx_rx,
              _BytesToMbits(iperf_avg['bytes']),
              transmit_time,
              _BitsToMbits(iperf_avg['bits_per_second'])))

  def _CheckIperfThroughput(self, tx_rx, log_key, log_pass_key, min_throughput):
    iperf_avg = self._log[log_key]['end']['sum_sent']
    # Ensure the average throughput is over its minimum.
    if min_throughput is not None:
      self._log[log_pass_key] = (
          _BitsToMbits(iperf_avg['bits_per_second']) > min_throughput)
      if not self._log[log_pass_key]:
        raise self._TestException(
            '%s throughput %.2f < %.2f Mbits/s didn\'t meet the minimum' % (
                tx_rx,
                _BitsToMbits(iperf_avg['bits_per_second']),
                min_throughput))
      else:
        return (
            '%s throughput %.2f >= %.2f Mbits/s meets the minimum' % (
                tx_rx,
                _BitsToMbits(iperf_avg['bits_per_second']),
                min_throughput))


class _Ui(object):
  def __init__(self):
    # Set up UI.
    self._ui = test_ui.UI()
    self._template = OneSection(self._ui)
    self._ui.AppendCSS(_DEFAULT_WIRELESS_TEST_CSS)
    self._template.SetState(_MSG_RUNNING)
    self._space_event = threading.Event()
    self._done = threading.Event()

  def PromptSpace(self):
    """Prompts a message to ask operator to press space."""
    self._done.clear()
    self._space_event.clear()
    self._template.SetState(_MSG_SPACE)
    self._ui.BindKey(' ', lambda _: self.OnSpacePressed())
    self._ui.Run(blocking=False, on_finish=self.Done)
    self._space_event.wait()
    return self._done.isSet()

  def Done(self):
    """The callback when ui is done.

    This will be called when test is finished, or if operator presses
    'Mark Failed'.
    """
    self._done.set()
    self._space_event.set()

  def OnSpacePressed(self):
    """The handler of space key."""
    logging.info('Space pressed by operator.')
    self._template.SetState(_MSG_RUNNING)
    self._space_event.set()


class WiFiThroughput(unittest.TestCase):
  """WiFi throughput test.

  Accepts a list of wireless services, checks for their signal strength,
  connects to them, and tests data throughput rate using iperf3.
  """
  # Arguments that can only be applied to each WiFi service connection.  These
  # will be checked as key-values in the test's "service" argument (see below).
  _SERVICE_ARGS = [
      Arg('ssid', str,
          'SSID of WiFi service.',
          optional=False),
      Arg('password', str,
          'Password of WiFi service.',
          optional=True, default=None)
  ]

  # Arguments that can be directly applied to each WiFi service connection, OR
  # directly provided as a "test-level" argument.  "service-level" arguments
  # take precedence.
  _SHARED_ARGS = [
      Arg('iperf_host', str,
          'Host running iperf3 in server mode, used for testing data '
          'transmission speed.',
          optional=True, default=None),
      Arg('min_signal_strength', int,
          'Minimum signal strength required (range from 0 to 100).',
          optional=True),
      Arg('transmit_time', int,
          'Time in seconds for which to transmit data.',
          optional=True, default=Iperf3.DEFAULT_TRANSMIT_TIME),
      Arg('transmit_interval', (int, float),
          'There will be an overall average of transmission speed.  But it may '
          'also be useful to check bandwidth within subintervals of this time. '
          'This argument can be used to check bandwidth for every interval of '
          'n seconds.  Assuming nothing goes wrong, there will be '
          'ceil(transmit_time / n) intervals reported.',
          optional=True, default=Iperf3.DEFAULT_TRANSMIT_INTERVAL),
      Arg('min_tx_throughput', int,
          'Required DUT-to-host (TX) minimum throughput in Mbits/sec.  If the '
          'average throughput is lower than this, will report a failure.',
          optional=True, default=None),
      Arg('min_rx_throughput', int,
          'Required host-to-DUT (RX) minimum throughput in Mbits/sec.  If the '
          'average throughput is lower than this, will report a failure.',
          optional=True, default=None),
  ]

  # "Test-level" arguments.  _SHARED_ARGS is concatenated at the end, since we
  # want the option to provide arguments as global defaults (as in the example
  # above).
  ARGS = [
      Arg('event_log_name', str, 'Name of the event_log.  We might want to '
          're-run the conductive test at different points in the factory, so '
          'this can be used to separate them.  '
          'e.g. "wifi_throughput_in_chamber"',
          optional=False),
      Arg('arduino_high_pins', list,
          'A list of ints.  If not None, set arduino pins in the list to high.',
          optional=True, default=None),
      Arg('bind_wifi', bool,
          'Whether we should restrict iperf3 to running on the WiFi interface.',
          optional=True, default=True),
      Arg('disable_eth', bool,
          'Whether we should disable ethernet interfaces while running the '
          'test.',
          optional=True, default=False),
      Arg('use_ui_retry', bool,
          'In the case that the iperf3 server is currently busy running a '
          'test, use the goofy UI to show a message forcing the tester to '
          'retry indefinitely until it can connect or until another error is '
          'received.  When running at the command-line, this behaviour is not '
          'available.',
          optional=True, default=False),
      Arg('services', (list, dict),
          'A list of dicts, each representing a WiFi service to test.  At '
          'minimum, each must have a "ssid" field.  Usually, a "password" '
          'field is also included.  (Omit or set to None or "" for an open '
          'network.)  Additionally, the following fields can be provided to '
          'override arguments passed to this test (refer to _SHARED_ARGS): '
          'min_signal_strength, iperf_host, transmit_time, transmit_interval, '
          'min_rx_throughput, min_tx_throughput.  If services are not '
          'specified, this test will simply list APs.  Also note that each '
          'service may only be specified once.',
          optional=True, default=[]),
  ] + _SHARED_ARGS  # note the concatenation of "shared" arguments

  def __init__(self, *args, **kwargs):
    super(WiFiThroughput, self).__init__(*args, **kwargs)
    self._leds_blinker = None

  def _Log(self):
    event_log.Log(self.args.event_log_name, **self.log)

  def _StartOperatorFeedback(self):
    # In case we're in a chamber without a monitor, store blinking keyboard LEDs
    # object to inform the operator that we're still working.  We'll run this in
    # runTest using a 'with' statement.
    self._leds_blinker = leds.Blinker(
        [(0, 0.5), (leds.LED_NUM | leds.LED_CAP | leds.LED_SCR, 0.5)])

    # If arduino_high_pins is provided as an argument, then set the requested
    # pins in the list to high.
    if self.args.arduino_high_pins:
      arduino_controller = arduino.ArduinoDigitalPinController()
      arduino_controller.Connect()
      for high_pin in self.args.arduino_high_pins:
        arduino_controller.SetPin(high_pin)
      arduino_controller.Disconnect()

  def _EndOperatorFeedback(self):
    # Stop blinking LEDs.
    if self._leds_blinker:
      self._leds_blinker.Stop()

  def _RunBasicSSIDList(self):
    # Basic WiFi test -- returns available APs.
    try:
      found_ssids = sync_utils.PollForCondition(
          poll_method=self._wifi.get_active_wifi_SSIDs,
          timeout_secs=_WIFI_TIMEOUT_SECS,
          poll_interval_secs=_DEFAULT_POLL_INTERVAL_SECS,
          condition_name='Looking for WiFi services...')
      factory.console.info('Found services: %s', ', '.join(found_ssids))
    except Exception:
      error_msg = 'Timed out while searching for WiFi services'
      self.log['failures'].append(error_msg)
      self._Log()
      self.fail(error_msg)
    return found_ssids

  def _ProcessArgs(self):
    """Sets up service arguments inheritance.

    "service-level" arguments inherit from "test-level" arguments.  See the
    documentation of this class for details.
    """
    # If only one service is provided as a dict, wrap a list around it.
    # Ensure that each service SSID is only specified once.
    if not isinstance(self.args.services, list):
      self.args.services = [self.args.services]
    ssids = [service['ssid'] for service in self.args.services]
    if len(ssids) != len(set(ssids)):
      raise ValueError("['services'] argument may only specify each SSID once")

    # Process service arguments with the Args class, taking "test-level"
    # argument values as default if "service-level" argument is absent.  Now,
    # we only need to read the self.args.services dictionary to get any
    # _SERVICE_ARGS or _SHARED_ARGS values.
    args_dict = self.args.ToDict()
    service_args = []
    for arg in self._SERVICE_ARGS + self._SHARED_ARGS:
      # iperf_host is optional at "test-level", but required at "service-level".
      if arg.name == 'iperf_host':
        arg.optional = False
      service_args.append(Arg(
          name=arg.name,
          type=arg.type,
          help=arg.help,
          default=args_dict.get(arg.name, arg.default),
          optional=arg.optional))
    service_arg_parser = Args(*service_args)
    if not isinstance(self.args.services, list):
      self.args.services = [self.args.services]
    new_services = []
    for service_dict in self.args.services:
      new_services.append(service_arg_parser.Parse(service_dict))
    self.args.services = new_services

  def setUp(self):
    # Services should inherit from provided "test-level" arguments.
    self._ProcessArgs()
    self.dut = dut.Create()

    # Initialize the log dict, which will later be fed into event log.
    self.log = {
        'args': self.args.ToDict(),
        'run': {
            'path': os.environ.get('CROS_FACTORY_TEST_PATH'),
            'invocation': os.environ.get('CROS_FACTORY_TEST_INVOCATION')},
        'dut': {
            'device_id': event_log.GetDeviceId(),
            'mac_address': net_utils.GetWLANMACAddress(),
            'serial_number': shopfloor.GetDeviceData().get(
                'serial_number', None),
            'mlb_serial_number': shopfloor.GetDeviceData().get(
                'mlb_serial_number', None)},
        'ssid_list': {},
        'test': {},
        'failures': []}

    # Keyboard lights and arduino pins.
    self._StartOperatorFeedback()

    # Ensure all required services are enabled.
    for service in _SERVICE_LIST:
      if (service_utils.GetServiceStatus(service, self.dut) ==
          service_utils.Status.STOP):
        service_utils.SetServiceStatus(
            service, service_utils.Status.START, self.dut)

    # Disable ethernet interfaces if needed.
    if self.args.disable_eth:
      logging.info('Disabling ethernet interfaces')
      net_utils.SwitchEthernetInterfaces(False)

    # Initialize our WifiProxy library and Iperf3 library.
    self._wifi = wifi_proxy.WifiProxy()
    self._iperf3 = Iperf3()

    # If use_ui_retry and we are running the UI (will except when run on
    # command-line), then use a retry-loop in the goofy UI when an iperf3 server
    # is currently busy running another client's test.
    self._ui = None
    if self.args.use_ui_retry:
      try:
        self._ui = _Ui()
      except Exception:
        pass

  def tearDown(self):
    logging.info('Tear down...')
    self._EndOperatorFeedback()

    # Enable ethernet interfaces if needed.
    if self.args.disable_eth:
      logging.info('Enabling ethernet interfaces')
      net_utils.SwitchEthernetInterfaces(True)

  def _RunTestChecks(self):
    # Check that we have an online WLAN interface.
    dev = net_utils.GetWLANInterface()
    if not dev:
      error_str = 'No wireless interface available'
      self.log['failures'].append(error_str)
      self._Log()
      self.fail(error_str)
    else:
      logging.info('ifconfig %s up', dev)
      process_utils.Spawn(['ifconfig', dev, 'up'], check_call=True, log=True)

    # Ensure that WiFi is in a disconnected state.
    service = self._wifi.find_matching_service({
        self._wifi.SERVICE_PROPERTY_TYPE: 'wifi',
        'IsActive': True})
    if service:
      logging.info('First disconnect from current WiFi service...')
      if not self._wifi.disconnect_service_synchronous(
          service, _WIFI_TIMEOUT_SECS):
        error_str = 'Failed to disconnect from current WiFi service'
        self.log['failures'].append(error_str)
        self._Log()
        self.fail(error_str)
      else:
        logging.info('Disconnected successfully from current WiFi service')

  def runTest(self):
    # Ensure that our WiFi device is in a known disconnected state.
    self._RunTestChecks()

    # Blink LEDs while test is running.
    with self._leds_blinker:
      # Run a basic SSID list test (if none found will fail).
      found_ssids = self._RunBasicSSIDList()
      # TODO(kitching): Remove this hack to take out Unicode characters, which
      #                 works around crbug.com/443073.
      found_ssids = [
          [x for x in ssid if x in string.printable] for ssid in found_ssids]
      self.log['ssid_list'] = found_ssids

      # Test WiFi signal strength for each service.
      if self.args.services:
        service_test = _ServiceTest(self._wifi, self._iperf3, self._ui,
                                    self.args.bind_wifi)
        for ap_config in self.args.services:
          self.log['test'][ap_config.ssid] = service_test.Run(ap_config)

      # Log this test run.
      self._Log()

      # Check for any failures and report an aggregation.
      all_failures = []
      for ssid, ap_log in self.log['test'].iteritems():
        for error_msg in ap_log['failures']:
          all_failures.append((ssid, error_msg))
      if all_failures:
        error_msg = ('Error in connecting and/or running iperf3 '
                     'on one or more services')
        factory.console.error(error_msg)
        factory.console.error('Error summary:')
        for (ssid, failure) in all_failures:
          factory.console.error(failure)
        self.fail(error_msg)
