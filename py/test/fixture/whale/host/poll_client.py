# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Client of Polld running on Whale BeagleBone.

It is basically a copy from third_party/hdctools/polld/poll_client.py.
"""

import sys

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils import net_utils


class PollClientError(Exception):
  """Exception class for poll_client."""
  pass


class PollClient(object):
  """Class to interface with polld via XMLRPC."""

  GPIO_EDGE_RISING = 'gpio_rising'
  GPIO_EDGE_FALLING = 'gpio_falling'
  GPIO_EDGE_BOTH = 'gpio_both'
  GPIO_EDGE_LIST = [GPIO_EDGE_RISING, GPIO_EDGE_FALLING, GPIO_EDGE_BOTH]

  def __init__(self, host, tcp_port, timeout=10, verbose=False):
    """Constructor.

    Args:
      host: Name or IP address of servo server host.
      tcp_port: TCP port on which servod is listening on.
      timeout: Timeout for HTTP connection.
      verbose: Enables verbose messaging across xmlrpclib.ServerProxy.
    """
    remote = 'http://%s:%s' % (host, tcp_port)
    self._server = net_utils.TimeoutXMLRPCServerProxy(
        remote, timeout=timeout, verbose=verbose)

  def PollGPIO(self, gpio_port, edge, timeout_secs=None):
    """Long-polls a GPIO port.

    Args:
      gpio_port: GPIO port
      edge: value in GPIO_EDGE_LIST
      timeout_secs: (int) polling timeout in seconds.

    Returns:
      True if the GPIO edge is polled.
      False if timeout occurs.

    Raises:
      PollClientError: If error occurs when polling the GPIO port.
    """
    if edge not in self.GPIO_EDGE_LIST:
      raise PollClientError(
          'Invalid edge %r. Valid values: %r' % (edge, self.GPIO_EDGE_LIST))

    try:
      with utils.Timeout(timeout_secs):
        self._server.poll_gpio(gpio_port, edge)
        return True
    except utils.TimeoutError:
      return False
    except Exception as e:
      exception_name = sys.exc_info()[0].__name__
      raise PollClientError('Problem to poll GPIO %s %s: %s(%s)' %
                            (str(gpio_port), edge, exception_name, str(e)))
