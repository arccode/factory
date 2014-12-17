# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provides interface for polling GPIO either locally or remotely via polld."""

import sys

import factory_common  # pylint: disable=W0611
from cros.factory.test.fixture.whale.host import poll_gpio
from cros.factory.test import utils
from cros.factory.utils import net_utils
from cros.factory.utils import type_utils


class PollClientError(Exception):
  """Exception class for poll_client."""
  pass


class PollClient(object):
  """Polls GPIO either locally or remotely via polld."""

  GPIO_EDGE_RISING = 'gpio_rising'
  GPIO_EDGE_FALLING = 'gpio_falling'
  GPIO_EDGE_BOTH = 'gpio_both'
  GPIO_EDGE_LIST = [GPIO_EDGE_RISING, GPIO_EDGE_FALLING, GPIO_EDGE_BOTH]

  def __init__(self, use_polld, host, tcp_port, timeout=10, verbose=False):
    """Constructor.

    Args:
      use_polld: True to use polld to poll GPIO port on remote server, or False
                 to poll local GPIO port directly.
      host: Name or IP address of servo server host.
      tcp_port: TCP port on which servod is listening on.
      timeout: Timeout for HTTP connection.
      verbose: Enables verbose messaging across xmlrpclib.ServerProxy.
    """
    self._use_polld = use_polld
    self._server = None
    if use_polld:
      remote = 'http://%s:%s' % (host, tcp_port)
      self._server = net_utils.TimeoutXMLRPCServerProxy(
          remote, timeout=timeout, verbose=verbose)

  def PollGPIO(self, gpio_port, edge, timeout_secs=None):
    """Polls a GPIO port.

    Args:
      gpio_port: GPIO port
      edge: value in GPIO_EDGE_LIST
      timeout_secs: (int) polling timeout in seconds.

    Returns:
      True if the GPIO port is edge triggered.
      False if timeout occurs.

    Raises:
      PollClientError: If error occurs when polling the GPIO port.
    """
    if edge not in self.GPIO_EDGE_LIST:
      raise PollClientError(
          'Invalid edge %r. Valid values: %r' % (edge, self.GPIO_EDGE_LIST))

    try:
      if self._use_polld:
        try:
          # TODO: Interrupting HTTP requests with Timeout() is problematic.
          #       Use with caution!
          with utils.Timeout(timeout_secs):
            self._server.poll_gpio(gpio_port, edge)
            return True
        except type_utils.TimeoutError:
          return False
      else:
        gpio = poll_gpio.PollGpio.GetInstance(gpio_port, edge)
        return gpio.Poll(timeout_secs)
    except Exception as e:
      exception_name = sys.exc_info()[0].__name__
      raise PollClientError('Problem to poll GPIO %s %s: %s(%s)' %
                            (str(gpio_port), edge, exception_name, str(e)))
