# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Proxy to Chrome OS Factory Server.

This module provides a simple interface for all factory tests to access Chrome
OS factory server.

The URL to factory server will be stored as local config (using
``config_utils``) when you call ``server_proxy.SetServerURL(url)``.

To access factory server, first get a proxy object and then call the function
using object attribute. For example::

  proxy = server_proxy.GetServerProxy()
  proxy.Ping()

For what functions are available on factory server, please check
 ``py/umpire/server/dut_rpc.py`` and ``py/shopfloor/README.md``.
"""

import xmlrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event
from cros.factory.umpire.client import umpire_server_proxy
from cros.factory.utils import config_utils
from cros.factory.utils import webservice_utils


Fault = xmlrpclib.Fault

FACTORY_SERVER_CONFIG_NAME = 'factory_server'
CONFIG_KEY_URL = 'server_url'
CONFIG_KEY_TIMEOUT = 'server_timeout'
CONFIG_KEY_PROTOCOL = 'server_protocol'


class ServerProxyError(Exception):
  pass


def GetServerConfig():
  """Returns current configuration for connection to factory server."""
  return config_utils.LoadConfig(FACTORY_SERVER_CONFIG_NAME)


def UpdateServerConfig(new_config):
  """Updates server config to the new value."""
  config_utils.SaveRuntimeConfig(FACTORY_SERVER_CONFIG_NAME, new_config)
  # Notify config changes.
  try:
    with event.EventClient() as client:
      client.post_event(event.Event(
          event.Event.Type.FACTORY_SERVER_CONFIG_CHANGED,
          **new_config))
  except Exception:
    pass


def GetServerURL():
  """Returns current configuration of factory server URL."""
  return GetServerConfig().get(CONFIG_KEY_URL)


def SetServerURL(new_url):
  """Changes current configuration for new factory server URL."""
  config = GetServerConfig()
  if config.get(CONFIG_KEY_URL) == new_url:
    return
  config[CONFIG_KEY_URL] = new_url
  UpdateServerConfig(config)


def GetServerProxy(url=None, timeout=None, quiet=False):
  """Gets a proxy object to access the Chrome OS Factory Server.

  Args:
    url: URL of the factory server. If None, use the default config.
    timeout: Timeout of RPC calls in seconds. If None, use the default config.
    quiet: Suppresses error messages when factory server can not be reached.

  Returns:
    A TimeoutUmpireServerProxy object that can work with either
    simple XML-RPC server (legacy factory server) or Umpire server.
  """
  config = GetServerConfig()
  if url is None or timeout is None:
    url = config.get(CONFIG_KEY_URL) if url is None else url
    timeout = config.get(CONFIG_KEY_TIMEOUT) if timeout is None else timeout
  if not url:
    raise ServerProxyError('No URL specified for factory server proxy.')
  protocol = config.get(CONFIG_KEY_PROTOCOL)
  # The factory server may be different implementations, for example
  # legacy XML-RPC or Umpire. Currently the TimeoutUmpireServerProxy will
  # automatically try and decide the protocol, which will double timeout when
  # the server is not available by (1) protocol detection (2) first ping.
  # Adding a "protocol" identifier may help solving the problem.
  if protocol == 'legacy':
    return webservice_utils.CreateWebServiceProxy(url)
  else:
    return umpire_server_proxy.TimeoutUmpireServerProxy(
        url, quiet=quiet, allow_none=True, verbose=False, timeout=timeout)
