# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""WiFi throughput test.

Description
-----------
Accepts a list of wireless services, checks for their signal strength and
quality, connects to them, and tests data throughput rate using iperf3.

One notable difference about this test is how it processes arguments:
  1. Each service configuration must provide two required arguments "ssid"
     and "password".
  2. If a service configuration does not provide an argument, it defaults
     to the "test-level" argument.
  3. If it was not provided as a "test-level" argument, it takes the
     default value passed to the Arg() constructor.

Test Procedure
--------------

Accepts a list of wireless services.

For each service:
  1. Checks signal strength.
  2. Checks quality devices.
  3. Connects to devices.
  4. Tests data throughput rate using iperf3.

Dependency
----------
- `ifconfig` utility
- `iperf3` utility

Examples
--------
Here's an example of input arguments::

  {
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
            "min_strength": -40,
          }
      ],
      "min_strength": -20,
      "iperf_host": "10.0.0.1",
      "min_tx_throughput": 100,
  }

After processing, each service would effectively have a configuration that
looks like this::

  {
      "event_log_name": "wifi_throughput_in_chamber",
      "services": [
          {
            "ssid": "ap",
            "password": "pass1",
            "min_strength": -20,  # inherited from test-level arg
            "iperf_host": "10.0.0.1",  # inherited from test-level arg
            "min_tx_throughput": 100,  # inherited from test-level arg
            "min_rx_throughput": 80,
          },
          {
            "ssid": "ap_5g",
            "password": "pass2",
            "min_strength": -40,  # blocks test-level arg
            "iperf_host": "10.0.0.1",  # inherited from test-level arg
            "min_tx_throughput": 100,  # inherited from test-level arg
          }
      ],
  }
"""

import contextlib
import json
import logging
import subprocess
import sys
import time

from cros.factory.device import CalledProcessError
from cros.factory.device import device_utils
from cros.factory.test import event_log  # TODO(chuntsen): Deprecate event log.
from cros.factory.test.fixture import arduino
from cros.factory.test.i18n import _
from cros.factory.test import session
from cros.factory.test import test_case
from cros.factory.test import test_ui
from cros.factory.test.utils import kbd_leds
from cros.factory.testlog import testlog
from cros.factory.utils import arg_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils.schema import JSONSchemaDict
from cros.factory.utils import net_utils
from cros.factory.utils import sync_utils
from cros.factory.utils import type_utils


_WIFI_TIMEOUT_SECS = 20
_DEFAULT_POLL_INTERVAL_SECS = 1
_IPERF_TIMEOUT_SECS = 5

_ARG_SERVICES_SCHEMA = JSONSchemaDict('services schema object', {
    'definitions': {
        'service': {
            'type': 'object',
            'properties': {
                'ssid': {'type': 'string'},
                'password': {'type': 'string'},
                'min_strength': {'type': 'number'},
                'min_quality': {'type': 'number'},
                'iperf_host': {'type': 'string'},
                'transmit_time': {'type': 'number'},
                'transmit_interval': {'type': 'number'},
                'min_rx_throughput': {'type': 'number'},
                'min_tx_throughput': {'type': 'number'}
            },
            'required': ['ssid'],
            'additionalProperties': False
        }
    },
    'oneOf': [
        {'$ref': '#/definitions/service'},
        {
            'type': 'array',
            'items': {'$ref': '#/definitions/service'}
        }
    ]
})


def _MbitsToBits(x):
  return x * 1.e6


def _BitsToMbits(x):
  return x / 1.e6


def _BytesToMbits(x):
  return _BitsToMbits(x * 8)


@contextlib.contextmanager
def DummyContextManager():
  yield


class Iperf3Server:
  """Provides a context manager for running the iperf3 command as a server."""

  def __init__(self, port):
    self._port = port
    self._process = None

  def __enter__(self):
    session.console.info('Start iperf3 server at local side')
    net_utils.EnablePort(self._port)
    self._process = subprocess.Popen(
        ['iperf3', '--server', '--port', str(self._port)])
    # Insert a short pause to ensure that the process is up and ready
    # for testing.
    time.sleep(1)

  def __exit__(self, exc_type, exc_value, exc_tb):
    del exc_type, exc_value, exc_tb
    if self._process:
      session.console.info('Stop iperf3 server at local side')
      self._process.kill()
      self._process.wait()


class Iperf3Client:
  """Wraps around spawning the iperf3 command as a client.

  Allows running the iperf3 command and checks its resulting JSON dict for
  validity.
  """
  ERROR_MSG_BUSY = 'error - the server is busy running a test. try again later'
  DEFAULT_PORT = 5201
  DEFAULT_TRANSMIT_TIME = 5
  DEFAULT_TRANSMIT_INTERVAL = 1
  # Wait (transmit_time + _TIMEOUT_KILL_BUFFER) before killing iperf3.
  _TIMEOUT_KILL_BUFFER = 5

  def __init__(self, dut_object):
    self._dut = dut_object

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
        'timeout',  # sends TERM signal after timeout
        # Add _TIMEOUT_KILL_BUFFER seconds to allow for process overhead and
        # connection time.
        str(transmit_time + self._TIMEOUT_KILL_BUFFER)] + iperf_cmd

    logging.info(
        'Running iperf3 connecting to host %s for %d seconds',
        server_host, transmit_time)

    try:
      output = self._dut.CallOutput(timeout_cmd, log=True)
      logging.info('iperf3 output: %s', output)
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


class _ServiceTest:
  """Collection of tests to be run on each service.

  Provides a "flow" mechanism for tests to be run on each service, with the
  overall control in the self.Run method.  Takes care of utility objects,
  carrying forward state, and logging to session.console.

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

  # State to be carried along from test to test.
  _ap = None
  _conn = None
  _ap_config = None
  _service = None
  _log = None

  def __init__(self, wifi, interface, aps, iperf3, ui,
               bind_wifi, use_ui_retry):
    self._wifi = wifi
    self._interface = interface
    self._aps = aps
    self._iperf3 = iperf3
    self._bind_wifi = bind_wifi
    self._ui = ui
    self._use_ui_retry = use_ui_retry

  def _Log(self, text, *args):
    f_name = sys._getframe(1).f_code.co_name  # pylint: disable=protected-access
    session.console.info(u'[%s] INFO [%s] ' + text,
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
        except Exception:
          return self._log # next try/except block depends on this one's success
          pass             # OR: next try/except block should be executed anyway

    Args:
      ap_config: The configuration dict for testing this particular service.
          E.g. ssid, password, min_strength, min_quality, transmit_time

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
        'pass_strength': None,
        'pass_quality': None,
        'pass_iperf_tx': None,
        'pass_iperf_rx': None,
        'iw_connection_status': None,
        'failures': []}
    self._ui.SetState(_('Running, please wait...'))

    def DoTest(fn, abort=False, **kwargs):
      """Runs a test and reports its success/failure to the session.console.

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
          session.console.info('[%s] PASS [%s] %s',
                               ap_config.ssid, fn.__name__, status)
      except self._TestException as e:
        logging.exception('Failed to run %s(**kwargs=%s)', fn.__name__, kwargs)
        message = '[%s] FAIL [%s] %s' % (
            ap_config.ssid, fn.__name__, str(e))
        self._log['failures'].append(message)
        session.console.error(message)
        if abort:
          raise

    # Try connecting to the service.  If we can't connect, then don't log
    # connection details, and abort this service's remaining tests.
    try:
      DoTest(self._Find, abort=True, ssid=ap_config.ssid)

      DoTest(self._CheckStrength, min_strength=ap_config.min_strength)

      DoTest(self._CheckQuality, min_quality=ap_config.min_quality)

      DoTest(self._Connect, abort=True,
             ssid=ap_config.ssid, password=ap_config.password)

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
               ssid=ap_config.ssid,
               tx_rx=tx_rx,
               log_key=('iperf_%s' % tx_rx.lower()),
               log_pass_key=('pass_iperf_%s' % tx_rx.lower()),
               min_throughput=min_throughput)
      except self._TestException:
        pass  # continue to next test (TX/RX)

    DoTest(self._LogConnectionSummaryStatus)

    # Attempt to disconnect from the WiFi network.
    try:
      DoTest(self._Disconnect, ssid=ap_config.ssid)
    except self._TestException:
      pass

    # Need to return service's log state.
    return self._log

  def _Find(self, ssid):
    # Look for requested service.
    self._Log(u'Trying to connect to service %s...', ssid)
    for ap in self._aps:
      if ap.ssid == ssid:
        self._ap = ap
        return u'Found service %s' % ssid
    raise self._TestException(u'Unable to find service %s' % ssid)

  def _CheckStrength(self, min_strength):
    # Check signal strength.
    if min_strength is None:
      return None
    strength = self._ap.strength
    self._log['pass_strength'] = (
        strength is not None and strength >= min_strength)
    if not self._log['pass_strength']:
      raise self._TestException('strength %s < %d [fail]'
                                % (strength, min_strength))
    return 'strength %s >= %d [pass]' % (strength, min_strength)

  def _CheckQuality(self, min_quality):
    # Check signal quality.
    if min_quality is None:
      return None
    quality = self._ap.quality
    self._log['pass_quality'] = (
        quality is not None and quality >= min_quality)
    if not self._log['pass_quality']:
      raise self._TestException('quality %s < %d [fail]'
                                % (quality, min_quality))
    return 'quality %s >= %d [pass]' % (quality, min_quality)

  def _Connect(self, ssid, password):
    # Try connecting.
    self._Log('Connecting to %s...', ssid)
    try:
      self._conn = self._wifi.Connect(
          interface=self._interface,
          ap=self._ap,
          passkey=password,
          connect_timeout=_WIFI_TIMEOUT_SECS,
          dhcp_timeout=_WIFI_TIMEOUT_SECS)
    except self._wifi.WiFiError:
      unused_exc_class, exc, tb = sys.exc_info()
      exc_message = '%s: %s' % (exc.__class__.__name__, str(exc))
      new_exc = self._TestException('Unable to connect to %s: %s'
                                    % (ssid, exc_message))
      raise new_exc.__class__(new_exc).with_traceback(tb)
    else:
      return 'Successfully connected to %s' % ssid

  def _LogConnection(self):
    # Save network ssid details.
    self._log['ap'] = {
        'ssid': self._ap.ssid,
        'bssid': self._ap.bssid,
        'encryption': self._ap.encryption_type,
        'strength': self._ap.strength,
        'quality': self._ap.quality,
        'frequency': self._ap.frequency}
    return 'Saved connection information'

  def _LogConnectionSummaryStatus(self):
    # Save network ssid details.
    self._log['iw_connection_status'] = self._conn.GetStatus()
    return 'Saved connection summary status'

  def _RunIperf(
      self, iperf_host, bind_wifi, reverse, tx_rx, log_key,
      transmit_time, transmit_interval):
    # Determine the IP address to bind to (in order to prevent the test from
    # running on a wired device).
    if bind_wifi:
      bind_dev = self._interface
      bind_ip = self._conn.ip
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
                (x.get('error') == Iperf3Client.ERROR_MSG_BUSY)),
            timeout_secs=_IPERF_TIMEOUT_SECS,
            poll_interval_secs=_DEFAULT_POLL_INTERVAL_SECS,
            condition_name=log_msg)
      except type_utils.TimeoutError as e:
        iperf_output = e.output

      if (iperf_output.get('error') == Iperf3Client.ERROR_MSG_BUSY and
          self._use_ui_retry):
        self._Log('%s iperf3 error: %s', tx_rx, iperf_output.get('error'))
        self._Log('iperf3 server is currently busy running a test, please wait '
                  'for it to finish and try again.')
        self._Log('Hit space bar to retry...')
        self._ui.SetState(
            _('Please wait for other DUTs to finish WiFiThroughput test, '
              'and press spacebar to continue.'))
        self._ui.WaitKeysOnce(test_ui.SPACE_KEY)
        time.sleep(1)
        self._ui.SetState(_('Running, please wait...'))
      else:
        break

    # Save output.
    self._log[log_key] = iperf_output

    # Show any errors from iperf, but only fail if NO intervals.
    if 'error' in iperf_output:
      error_msg = '%s iperf3 error: %s' % (tx_rx, iperf_output['error'])
      if 'intervals' not in iperf_output:
        raise self._TestException(error_msg)
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

    # Show information about the data transferred.
    iperf_avg = iperf_output['end']['sum_sent']
    return (
        '%s transferred: %.2f Mbits, time spent: %d sec, '
        'throughput: %.2f Mbits/sec' % (
            tx_rx,
            _BytesToMbits(iperf_avg['bytes']),
            transmit_time,
            _BitsToMbits(iperf_avg['bits_per_second'])))

  def _CheckIperfThroughput(self, ssid, tx_rx, log_key, log_pass_key,
                            min_throughput):
    iperf_avg = self._log[log_key]['end']['sum_sent']

    # Ensure the average throughput is over its minimum.
    param_name = '%s_%s_avg_bits_per_second' % (ssid, tx_rx.lower())
    testlog.CheckNumericParam(
        name=param_name,
        value=iperf_avg['bits_per_second'],
        min=_MbitsToBits(min_throughput) if min_throughput else None)
    testlog.UpdateParam(
        name=param_name,
        description='Average speed of %s throughput test on AP %s' % (
            tx_rx.upper(), ssid),
        value_unit='Bits/second')

    if min_throughput is None:
      return None

    self._log[log_pass_key] = (
        _BitsToMbits(iperf_avg['bits_per_second']) > min_throughput)
    if not self._log[log_pass_key]:
      raise self._TestException(
          '%s throughput %.2f < %.2f Mbits/s didn\'t meet the minimum' %
          (tx_rx, _BitsToMbits(iperf_avg['bits_per_second']), min_throughput))

    return ('%s throughput %.2f >= %.2f Mbits/s meets the minimum' %
            (tx_rx, _BitsToMbits(iperf_avg['bits_per_second']),
             min_throughput))

  def _Disconnect(self, ssid):
    # Try disconnecting.
    self._Log('Disconnecting from %s...', ssid)
    try:
      self._conn.Disconnect()
    except self._wifi.WiFiError as e:
      raise self._TestException('Unable to disconnect from %s: %s'
                                % (ssid, e.message))
    else:
      return 'Successfully disconnected from %s' % ssid


class WiFiThroughput(test_case.TestCase):
  """WiFi throughput test.

  Accepts a list of wireless services, checks for their signal strength and
  quality, connects to them, and tests data throughput rate using iperf3.
  """
  # Arguments that can only be applied to each WiFi service connection.  These
  # will be checked as key-values in the test's "service" argument (see below).
  _SERVICE_ARGS = [
      Arg('ssid', str, 'SSID of WiFi service.'),
      Arg('password', str, 'Password of WiFi service.', default=None)
  ]

  # Arguments that can be directly applied to each WiFi service connection, OR
  # directly provided as a "test-level" argument.  "service-level" arguments
  # take precedence.
  _SHARED_ARGS = [
      Arg('iperf_host', str,
          'Host running iperf3 in server mode, used for testing data '
          'transmission speed. If it is CIDR format (IP/prefix), then '
          'interfaces will be scanned to find the one with an IP within the '
          'given CIDR, and iperf_host will take on this value. Useful for '
          'cases where the host\'s IP may change (from using DHCP). '
          'The CIDR format is valid only when `enable_iperf_server` argument '
          'is enabled.',
          default=None),
      Arg('enable_iperf_server', bool,
          'Start iperf server locally. In station-based testing we can run '
          'iperf server at the test station directly, instead of preparing '
          'another machine.',
          default=False),
      Arg('min_strength', int,
          'Minimum signal strength required (measured in dBm).  If the driver '
          'does not report this value, setting a limit always fail.',
          default=None),
      Arg('min_quality', int,
          'Minimum link quality required (out of 100).  If the driver '
          'does not report this value, setting a limit always fail.',
          default=None),
      Arg('transmit_time', int,
          'Time in seconds for which to transmit data.',
          default=Iperf3Client.DEFAULT_TRANSMIT_TIME),
      Arg('transmit_interval', (int, float),
          'There will be an overall average of transmission speed.  But it may '
          'also be useful to check bandwidth within subintervals of this time. '
          'This argument can be used to check bandwidth for every interval of '
          'n seconds.  Assuming nothing goes wrong, there will be '
          'ceil(transmit_time / n) intervals reported.',
          default=Iperf3Client.DEFAULT_TRANSMIT_INTERVAL),
      Arg('min_tx_throughput', int,
          'Required DUT-to-host (TX) minimum throughput in Mbits/sec.  If the '
          'average throughput is lower than this, will report a failure.',
          default=None),
      Arg('min_rx_throughput', int,
          'Required host-to-DUT (RX) minimum throughput in Mbits/sec.  If the '
          'average throughput is lower than this, will report a failure.',
          default=None),
  ]

  # "Test-level" arguments.  _SHARED_ARGS is concatenated at the end, since we
  # want the option to provide arguments as global defaults (as in the example
  # above).
  ARGS = [
      Arg('event_log_name', str,
          'Name of the event_log.  We might want to re-run the conductive '
          'test at different points in the factory, so this can be used to '
          'separate them.  e.g. "wifi_throughput_in_chamber"'),
      Arg('pre_command', str,
          'Command to be run before executing the test.  For example, this '
          'could be used to run "insmod" to load a WiFi module on the DUT.  '
          'Does not check output of the command.',
          default=None),
      Arg('post_command', str,
          'Command to be run after executing the test.  For example, this '
          'could be used to run "rmmod" to unload a WiFi module on the DUT.  '
          'Does not check output of the command.',
          default=None),
      Arg('interface', str,
          'WLAN interface being used.  e.g. wlan0.  If not specified, it will'
          'fail if multiple devices are found, otherwise use the only one '
          'device it found.',
          default=None),
      Arg('arduino_high_pins', list,
          'A list of ints.  If not None, set arduino pins in the list to high.',
          default=None),
      Arg('blink_leds', bool,
          'Whether or not to blink keyboard LEDs while running the test.  '
          'Useful when running with DUT inside of a chamber, and using an '
          'external keyboard to show test status.',
          default=False),
      Arg('bind_wifi', bool,
          'Whether we should restrict iperf3 to running on the WiFi interface.',
          default=True),
      Arg('disable_eth', bool,
          'Whether we should disable ethernet interfaces while running the '
          'test.',
          default=False),
      Arg('use_ui_retry', bool,
          'In the case that the iperf3 server is currently busy running a '
          'test, use the goofy UI to show a message forcing the tester to '
          'retry indefinitely until it can connect or until another error is '
          'received.  When running at the command-line, this behaviour is not '
          'available.',
          default=False),
      Arg('services', (list, dict),
          'A list of dicts, each representing a WiFi service to test.  At '
          'minimum, each must have a "ssid" field.  Usually, a "password" '
          'field is also included.  (Omit or set to None or "" for an open '
          'network.)  Additionally, the following fields can be provided to '
          'override arguments passed to this test (refer to _SHARED_ARGS): '
          'min_strength, min_quality, iperf_host, transmit_time, '
          'transmit_interval, min_rx_throughput, min_tx_throughput.  If '
          'services are not specified, this test will simply list APs.  Also '
          'note that each service may only be specified once.',
          default=[], schema=_ARG_SERVICES_SCHEMA),
  ] + _SHARED_ARGS  # note the concatenation of "shared" arguments

  def _Log(self):
    event_log.Log(self.args.event_log_name, **self.log)

  def _StartOperatorFeedback(self):
    # In case we're in a chamber without a monitor, store blinking keyboard LEDs
    # object to inform the operator that we're still working.
    if self.args.blink_leds:
      self._leds_blinker = kbd_leds.Blinker(
          [(0, 0.5),
           (kbd_leds.LED_NUM | kbd_leds.LED_CAP | kbd_leds.LED_SCR, 0.5)])
      # This starts a thread running in the background until
      # self._leds_blinker.Stop is called in self._EndOperatorFeedback.
      # We must ensure that Stop will always be called, otherwise the test will
      # hang after completion.
      self._leds_blinker.Start()

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
      found_aps = self._wifi.FilterAccessPoints(interface=self._interface)
      found_ssids = list({ap.ssid for ap in found_aps})
      session.console.info('Found services: %s', ', '.join(found_ssids))
    except self._wifi.WiFiError:
      error_msg = 'Timed out while searching for WiFi services'
      self.log['failures'].append(error_msg)
      self._Log()
      self.fail(error_msg)
    return found_aps

  def _ProcessArgs(self):
    """Sets up service arguments inheritance.

    "service-level" arguments inherit from "test-level" arguments.  See the
    documentation of this class for details.
    """
    # When Iperf server is executed on the host machine, and the IP is retrieved
    # from DHCP server, we can fill the CIDR at iperf_host first, then replace
    # it with the DHCP IP when running the pytest.
    if isinstance(self.args.iperf_host, str) and '/' in self.args.iperf_host:
      if not self.args.enable_iperf_server:
        self.fail('CIDR format is valid only when '
                  '`enable_iperf_server` argument is enabled')
      ip, _unused_char, prefix = self.args.iperf_host.partition('/')
      cidr = net_utils.CIDR(ip, int(prefix))
      session.console.info('Try to find the host IP in CIDR: %s...', cidr)
      for interface in net_utils.GetNetworkInterfaces():
        ip, unused_prefix_number = net_utils.GetEthernetIp(interface)
        if ip is None:
          continue
        if net_utils.IP(ip).IsIn(cidr):
          session.console.info('Set the iperf host IP: %s', ip)
          self.args.iperf_host = str(ip)
          break
      else:
        self.fail('There is no host IP in CIDR: %s' % cidr)

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
      service_args.append(Arg(
          name=arg.name,
          type=arg.type,
          help=arg.help,
          default=args_dict.get(arg.name, arg.default)))

    service_arg_parser = arg_utils.Args(*service_args)
    if not isinstance(self.args.services, list):
      self.args.services = [self.args.services]
    new_services = []
    for service_dict in self.args.services:
      new_services.append(service_arg_parser.Parse(service_dict))
    self.args.services = new_services

  def setUp(self):
    self._leds_blinker = None

    # Services should inherit from provided "test-level" arguments.
    self._ProcessArgs()
    self._dut = device_utils.CreateDUTInterface()

    # Run our pre-command.
    if self.args.pre_command:
      session.console.info('Running pre-command: %s', self.args.pre_command)
      try:
        output = self._dut.CheckOutput(self.args.pre_command)
      except CalledProcessError as e:
        session.console.info('Exit code: %d', e.returncode)
      else:
        session.console.info('Success. Output: %s', output)

    # Initialize the log dict, which will later be fed into event log.
    self.log = {
        'args': self.args.ToDict(),
        'run': {
            'path': session.GetCurrentTestPath(),
            'invocation': session.GetCurrentTestInvocation()},
        'dut': {
            'device_id': session.GetDeviceID(),
            'serial_number': self._dut.storage.LoadDict().get(
                'serial_number', None),
            'sub_serial_number': self._dut.storage.LoadDict().get(
                'sub_serial_number', None),
            'mlb_serial_number': self._dut.storage.LoadDict().get(
                'mlb_serial_number', None)},
        'ssid_list': {},
        'test': {},
        'failures': []}

    # Keyboard lights and arduino pins.
    self._StartOperatorFeedback()

    # Disable ethernet interfaces if needed.
    if self.args.disable_eth:
      logging.info('Disabling ethernet interfaces')
      net_utils.SwitchEthernetInterfaces(False)

    # Initialize our WifiProxy library and Iperf3 library.
    self._interface = None
    self._wifi = self._dut.wifi
    self._iperf3 = Iperf3Client(self._dut)

    self.ui.ToggleTemplateClass('font-large', True)

    # Group checker and details for Testlog.
    self._group_checker = testlog.GroupParam(
        'connection_data',
        ['log_type', 'ap_ssid', 'throughput', 'start_time', 'end_time',
         'computed_rssi', 'antenna_rssi'])
    testlog.UpdateParam(
        'throughput', description='TX/RX throughput test on AP over time',
        value_unit='Bits/second')
    testlog.UpdateParam('start_time', value_unit='seconds')
    testlog.UpdateParam('end_time', value_unit='seconds')
    testlog.UpdateParam('log_type', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('ap_ssid', param_type=testlog.PARAM_TYPE.argument)
    testlog.UpdateParam('computed_rssi', value_unit='dBm')
    testlog.UpdateParam('antenna_rssi', value_unit='dBm')

  def tearDown(self):
    logging.info('Tear down...')
    self._EndOperatorFeedback()

    # Run our post-command.
    if self.args.post_command:
      session.console.info('Running post-command: %s', self.args.post_command)
      try:
        output = self._dut.CheckOutput(self.args.post_command)
      except CalledProcessError as e:
        session.console.info('Exit code: %d', e.returncode)
      else:
        session.console.info('Success. Output: %s', output)

    # Enable ethernet interfaces if needed.
    if self.args.disable_eth:
      logging.info('Enabling ethernet interfaces')
      net_utils.SwitchEthernetInterfaces(True)

  def runTest(self):
    # Choose the WLAN interface to use for this test, either from the test
    # arguments, or by choosing the only one listed on the device.
    self._interface = self._wifi.SelectInterface(self.args.interface)
    session.console.info('Selected interface: %s', self._interface)

    # Run a basic SSID list test (if none found will fail).
    found_aps = self._RunBasicSSIDList()

    # Test WiFi signal and throughput speed for each service.
    if self.args.services:
      with (Iperf3Server(Iperf3Client.DEFAULT_PORT)
            if self.args.enable_iperf_server else DummyContextManager()):
        service_test = _ServiceTest(
            self._wifi, self._interface, found_aps, self._iperf3, self.ui,
            self.args.bind_wifi, self.args.use_ui_retry)

        for ap_config in self.args.services:
          test_result = service_test.Run(ap_config)
          self.log['test'][ap_config.ssid] = test_result

          # log throughput data
          for tx_rx in ('tx', 'rx'):
            iperf_key = 'iperf_%s' % tx_rx
            # pylint:disable=unsupported-membership-test
            for interval in test_result[iperf_key].get('intervals', []):
              self._LogIperfParams(ap_config.ssid, tx_rx, interval['sum'])
            if 'end' in test_result[iperf_key]:
              # pylint:disable=unsubscriptable-object
              self._LogIperfParams(ap_config.ssid, '%s_summary' % tx_rx,
                                   test_result[iperf_key]['end']['sum_sent'])

          # log RSSI data
          self._LogParams(
              ap_config.ssid, 'rssi',
              computed_rssi=test_result['iw_connection_status'].signal.computed,
              antenna_rssi=test_result['iw_connection_status'].signal.antenna)

    # Log this test run via event_log.
    self._Log()

    # Check for any failures and report an aggregation.
    all_failures = []
    for ssid, ap_log in self.log['test'].items():
      for error_msg in ap_log['failures']:
        all_failures.append((ssid, error_msg))
    if all_failures:
      error_msg = ('Error in connecting and/or running iperf3 '
                   'on one or more services')
      session.console.error(error_msg)
      session.console.error('Error summary:')
      for (ssid, failure) in all_failures:
        session.console.error(failure)
      self.fail(error_msg)

  def _LogIperfParams(self, ap_ssid, log_type, iperf_data):
    self._LogParams(ap_ssid, log_type, throughput=iperf_data['bits_per_second'],
                    start_time=iperf_data['start'], end_time=iperf_data['end'])

  def _LogParams(self, ap_ssid, log_type, throughput=None, start_time=None,
                 end_time=None, computed_rssi=None, antenna_rssi=None):
    with self._group_checker:
      testlog.LogParam('ap_ssid', ap_ssid)
      testlog.LogParam('log_type', log_type)
      testlog.LogParam('throughput', throughput)
      testlog.LogParam('start_time', start_time)
      testlog.LogParam('end_time', end_time)
      testlog.LogParam('computed_rssi', computed_rssi)
      testlog.LogParam('antenna_rssi', antenna_rssi)
