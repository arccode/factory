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

import logging
import xmlrpc.client

from cros.factory.test import event
from cros.factory.utils import config_utils
from cros.factory.utils import net_utils


Fault = xmlrpc.client.Fault

FACTORY_SERVER_CONFIG_NAME = 'factory_server'
CONFIG_KEY_URL = 'server_url'
CONFIG_KEY_EXPECTED_PROJECT = 'server_expected_project'
CONFIG_KEY_TIMEOUT = 'server_timeout'


class ServerProxyError(Exception):
  pass


def GetServerConfig():
  """Returns current configuration for connection to factory server."""
  return config_utils.LoadConfig(FACTORY_SERVER_CONFIG_NAME)


def ValidateServerConfig():
  """Validates factory server config.

  Factory server config is usually stored in runtime directory and may have been
  corrupted, so this is a helper function to delete runtime configuration if
  needed.
  """
  try:
    GetServerConfig()
  except ValueError:
    logging.exception('Failed reading factory server config, retry by '
                      'removing runtime config...')
    config_utils.DeleteRuntimeConfig(FACTORY_SERVER_CONFIG_NAME)
    GetServerConfig()


def UpdateServerConfig(new_config):
  """Updates server config to the new value."""
  config_utils.SaveRuntimeConfig(FACTORY_SERVER_CONFIG_NAME, new_config)
  # Notify config changes.
  try:
    event.PostNewEvent(event.Event.Type.FACTORY_SERVER_CONFIG_CHANGED,
                       **new_config)
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


def GetServerProxy(url=None, expected_project=None, timeout=None):
  """Gets a proxy object to access the Chrome OS Factory Server.

  Args:
    url: URL of the factory server. If None, use the default config.
    expected_project: If the server is an Umpire server, would check if the
        target Umpire server's Ping return expected project. If None, use the
        default config. To disable checking, set this to empty string "".
    timeout: Timeout of RPC calls in seconds. If None, use the default config.

  Returns:
    A TimeoutXMLRPCServerProxy object.
  """
  config = GetServerConfig()
  if url is None:
    url = config.get(CONFIG_KEY_URL)
  if timeout is None:
    timeout = config.get(CONFIG_KEY_TIMEOUT)
  if expected_project is None:
    expected_project = config.get(CONFIG_KEY_EXPECTED_PROJECT)
  if not url:
    raise ServerProxyError('No URL specified for factory server proxy.')
  if expected_project is None:
    logging.warning('"%s" not set in config %s, please set the config '
                    'to the project name of Umpire server, or set it to "" '
                    'to disable this warning.', CONFIG_KEY_EXPECTED_PROJECT,
                    FACTORY_SERVER_CONFIG_NAME)

  proxy = net_utils.TimeoutXMLRPCServerProxy(
      url, allow_none=True, verbose=False, timeout=timeout)
  if expected_project:
    project = proxy.Ping().get('project')
    if project is not None and project != expected_project:
      raise ServerProxyError(
          "The expected_project (%s) doesn't match the "
          'project returned from Umpire (%s). The URL (%s) might be wrong.' %
          (expected_project, project, url))
  return proxy
