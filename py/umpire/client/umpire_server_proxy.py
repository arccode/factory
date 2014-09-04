#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""UmpireServerProxy handles connection to UmpireServer."""


import logging
import re
import sys
import traceback
import urllib2
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.client.umpire_client import UmpireClientInfo
from cros.factory.umpire.common import REQUIRED_RESOURCE_MAP_FIELDS
from cros.factory.umpire.common import UMPIRE_VERSION
from cros.factory.utils.string_utils import ParseDict
from cros.factory.utils import net_utils

class UmpireServerError(object):
  """Class to hold error code and message."""
  def __init__(self, code, message):
    self.code = code
    self.message = message

# This error is returned by server when token is invalid.
ERROR_TOKEN_INVALID = UmpireServerError(410, 'Gone')


def CheckProtocolError(protocol_error, umpire_server_error):
  """Checks if an xmlrpclib.ProtocalError equals to an UmpireServerError.

  Args:
    protocol_error: An xmlrpclib.ProtocalError.
    umpire_server_error: An UmpireServerError.

  Returns:
    True if error code and error message are the same.
  """
  return (protocol_error.errcode == umpire_server_error.code and
          protocol_error.errmsg == umpire_server_error.message)


class UmpireServerProxyException(Exception):
  """Exceptsion of UmpireServerProxy."""
  pass


class UmpireServerProxy(xmlrpclib.ServerProxy):
  """Class to maintain proxy to XMLRPC handler served on the server.

  UmpireServerProxy subclasses xmlrpclib.ServerProxy. If server is not an
  Umpire server, then UmpireServerProxy acts as an xmlrpclib.ServerProxy.
  If server is an Umpire server, then UmpireServerProxy will handle
  extra tasks for Umpire server.
  Whether a server is an Umpire server can be found by "Ping" it. If the return
  value is a dict with 'version=UMPIRE_VERSION', it is an Umpire server;
  otherwise, it is a Shopfloor v1/v2 server.

  At least four services running on an Umpire server the class needs to work
  with:
  1. Base Umpire XMLRPC handler to serve basic methods like Ping. Client can
    identify the version of server through this call.
  2. HTTP server for resource map and other resources like device toolkit.
    DUT needs to pass DUT info in X-Umpire-DUT in the header of GET request
    for resource map. The replied resource map contains all resource info that
    is suitable for DUT.
  3. Umpire XMLRPC handler to serve methods that are not specific to bundle,
    e.g. NeedUpdate. The supported list of methods is queried by introspection.
  4. Shopfloor XMLRPC handler to serve methods that are specific to bundle.
    There can be multiple shopfloor XMLRPC handlers. The URI to handler is
    specified in resource map.

  In operation mode, the four services are served on the same port. The request
  is routed by Umpire server. For example:
  1. Base Umpire XMLRPC handler: http://10.3.0.1:8080
  2. HTTP server: http://10.3.0.1:8080
  3. Umpire XMLRPC handler: http://10.3.0.1:8080/umpire
  4. Shopfloor XMLRPC handler: http://10.3.0.1:8080/shop_floor/1234/00000001

  In test mode, the four services are served on the same host, but using
  different ports. Check docstrings of _SetUmpireUri for details.

  The base class connects to Base Umpire XMLRPC handler at init time. This is
  to determine the server version. After that, base class will connect to
  Umpire XMLRPC handler. If server version can not be determined at init time,
  It should be determined when user calls methods (through _Request method
  implicitely).
  This class maintains an object which implements UmpireClientInfoInterface
  and a token.
  If client info is updated, or token is invalid, it will fetch resource map and
  update the properties accordingly.
  This class dispatches method calls to Umpire XMLRPC handler, or a shopfloor
  XMLRPC handler specified in the resource map automatically.

  Properties:
    _server_uri: A string containing Umpire server URI (including port).
      This is also the URI to request resource map and other resources.
      This URI may be shopfloor handler URI for backward compatibility.
    _umpire_http_server_uri = The URI of HTTP server on Umpire server. In
      operation mode, it is the same as Umpire server URI. In test mode, it is
      at the next port of Umpire server URI.
    _umpire_handler_uri: A string containing the Umpire handler URI.
     Check _test_mode for how this property is determined.
    _use_umpire: True if the object should work with an Umpire server; False if
      object should work with simple XMLRPC handler.
    _umpire_client_info: An object which implements UmpireClientInfoInterface.
    _resources: A dict containing parsed results in resource map.
    _token: A string used to identify if a cached shopfloor handler URI is
      valid.
    _umpire_methods: A set of method names that Umpire XMLRPC handler
      supports. It is queried from ServerProxy.system.listMethods.
    _shop_floor_handler_uri: A string containing the shopfloor handler URI.
    _shop_floor_handler_server_proxy: An xmlrpclib.ServerProxy object connecting
      to per-bundle shopfloor XMLRPC handler. This property is needed because
      the UmpireServerProxy object itself connects to Umpire handler.
    _args: A tuple containing args from __init__. This is used to init
      _shop_floor_handler_server_proxy.
    _kwargs: A dict containing kwargs from __init__. This is used to init
      _shop_floor_handler_server_proxy.
    _test_mode: True for testing. The difference is in _SetShopFloorHandlerUri
      and _SetUmpireUri. Check their docstring for details.
      In test mode, Umpire HTTP server, shopfloor handler and Umpire XMLRPC
      handler use different ports from Umpire server, while in operation mode,
      they are at different paths, which complicates unittest.
  """
  def __init__(self, server_uri, test_mode=False, max_retries=5,
               umpire_client_info=None, *args, **kwargs):
    """Initializes an UmpireServerProxy.
    Args:
      server_uri: A string containing Umpire server URI or shopfloor
        handler URI. By Ping method, UmpireServerProxy can determine
        if it is working with a simple shopfloor XMLRPC handler or an Umpire
        server. Checks docstring of this class for details.
      test_mode: True for testing. The difference is in _SetUmpireUri.
      max_retries: Maximum number of retries for a shopfloor call that needs to
        get a new resource map.
      umpire_client_info: An object which implements UmpireClientInfoInterface.
        This is useful when user wants to use implementation other than
        UmpireClientInfo, e.g. when UmpireServerProxy is used in chroot.
      Other args are for base class.
    """
    self._server_uri = server_uri
    self._umpire_http_server_uri = None
    self._use_umpire = None
    self._umpire_client_info = None
    self._resources = dict()
    self._token = None
    self._umpire_handler_uri = None
    self._umpire_methods = set()
    self._shop_floor_handler_uri = None
    self._shop_floor_handler_server_proxy = None
    self._args = args
    self._kwargs = kwargs
    self._test_mode = test_mode
    self._max_retries = max_retries

    if umpire_client_info:
      logging.warning('Using injected Umpire client info.')
      self._umpire_client_info = umpire_client_info

    if self._test_mode:
      logging.warning('Using UmpireServerProxy in test mode.')

    # Connect to server URI first. If the server is not an Umpire server,
    # keep the connection. Otherwise, reconnect it to Umpire handler URI.
    logging.debug('Connecting to %r', self._server_uri)
    xmlrpclib.ServerProxy.__init__(self, self._server_uri,
                                   *args, **kwargs)

    self._Init(raise_exception=False)

  def _Init(self, raise_exception=True):
    """Checks server version and initializes Umpire server proxy.

    Checks if server is an Umpire server. If it is an Umpire server, then
    initialize the proxies for Umpire server.

    Args:
      raise_exception: Raises exception if server version can not be decided.

    Raises:
      UmpireServerProxyException: If server version can not be decided,
        and raise_exception is True.
    """
    # Determine if server is an Umpire server or a v1 shopfloor server.
    self._use_umpire = self._CheckUsingUmpire()
    logging.debug('Using Umpire: %r', self._use_umpire)
    if self._use_umpire is None and raise_exception:
      raise UmpireServerProxyException(
          'Can not decide using Umpire or not.')

    if self._use_umpire:
      self._InitForUmpireProxy()

  def _InitForUmpireProxy(self):
    """Initializes properties to work with Umpire server.

    Initializes Umpire client info as an UmpireClientInfo object if it is
    not given from class init argument.
    Sets Umpire handler URI depending on test mode.
    Initializes the object itself connecting to Umpire XMLRPC handler.
    Gets resource map and initializes proxy to shopfloor handler.
    """
    if not self._use_umpire:
      raise UmpireServerProxyException(
          'Initializes Umpire proxies when not using Umpire.')

    if not self._umpire_client_info:
      self._umpire_client_info = UmpireClientInfo()

    # Sets Umpire Handler URI depending on test mode.
    self._SetUmpireUri()

    # Initializes the object itself connecting to Umpire XMLRPC handler.
    logging.debug('Connecting to Umpire handler at %r',
                  self._umpire_handler_uri)
    xmlrpclib.ServerProxy.__init__(self, self._umpire_handler_uri,
                                   *self._args, **self._kwargs)

    # Gets resource map and sets shopfloor handler URI.
    self._RequestUmpireForResourceMapAndSetHandler()

  @property
  def use_umpire(self):
    """Checks if this object is talking to an Umpire server.

    Returns:
      True if this object is talking to an Umpire server.
      False if it talks to ShopFloor v1 or v2 server. None if it cannot decide
      as it fails to get response for 'Ping'.

    Raises:
      UmpireServerProxyException: If server version can not be determined.
    """
    # Try to contact server to decide using Umpire or not.
    if self._use_umpire is None:
      self._use_umpire = self._CheckUsingUmpire()
    if self._use_umpire is None:
      raise UmpireServerProxyException('Can not decide server version')
    return self._use_umpire

  def __request(self, methodname, params):
    """Wrapper for base class __request method.

    Args:
      methodname: Name of the method to call that is registered on XMLRPC
        handler.
      params: A tuple containing the args to methodname call.

    Returns:
      The return value of the shopfloor call.
    """
    logging.debug('Using base class __request method with methodname: %r, '
                  'params: %r', methodname, params)
    # pylint: disable=E1101
    return xmlrpclib.ServerProxy._ServerProxy__request(self, methodname, params)

  def _CheckUsingUmpire(self):
    """Returns if the server is an Umpire server.

    Calls Ping method through XMLRPC server proxy in the object itself assuming
    it is connecting to Umpire server URI.

    Returns:
      True if the server is an Umpire server.
    """
    try:
      result = self.__request('Ping', ())
    except Exception:
      # This is pretty common and not necessarily an error because by the time
      # when proxy instance is initiated, connection might not be ready.
      logging.warning(
        'Unable to contact shopfloor server to decide using Umpire or not: %s',
        '\n'.join(traceback.format_exception_only(*sys.exc_info()[:2])).strip())
      return None
    if isinstance(result, dict) and result.get('version') == UMPIRE_VERSION:
      logging.debug('Got Umpire server version %r', result.get('version'))
      return True
    else:
      logging.debug('Got shopfloor server response %r', result)
      return False

  def _GetResourceMap(self):
    """Sends a GET request to Umpire server URI and gets resource map.

    Returns:
      contents in resource map.
    """
    logging.info('Getting resource map from Umpire server')
    request = urllib2.Request(
        '%s/resourcemap' % self._umpire_http_server_uri,
        headers={"X-Umpire-DUT" : self._umpire_client_info.GetXUmpireDUT()})
    content = urllib2.urlopen(request).read()
    logging.info('Got resource map: %r', content)
    return content

  def _SetUmpireUri(self):
    """Sets Umpire Handler URI.

    This call is used when server is an Umpire server.
    The URI in operation mode are in docstrings of this class.
    The URI in test mode are for example:
    Base Umpire XMLRPC handler: http://localhost:49998
      (This is Umpire server URI from init argument)
    HTTP server: http://localhost:49999
    Umpire XMLRPC handler: http://localhost:50000
    """
    if not self._use_umpire:
      raise UmpireServerProxyException(
          '_SetUmpireUri method should only be used when working with Umpire'
          ' server. ')
    if self._test_mode:
      umpire_scheme_host, port = urllib2.splitport(self._server_uri)
      test_http_server_port = int(port) + 1
      test_handler_port = int(port) + 2
      self._umpire_http_server_uri = '%s:%d' % (
          umpire_scheme_host, test_http_server_port)
      self._umpire_handler_uri = '%s:%d' % (
          umpire_scheme_host, test_handler_port)
    else:
      self._umpire_http_server_uri = self._server_uri
      self._umpire_handler_uri = '%s/umpire' % self._server_uri
    logging.debug('Set Umpire HTTP server URI to %s',
                  self._umpire_http_server_uri)
    logging.debug('Set Umpire handler URI to %s', self._umpire_handler_uri)

  def _SetShopFloorHandlerUri(self, shop_floor_handler):
    """Sets _shop_floor_handler_uri from shop_floor_handler.

    Operation mode:
      'http://<umpire ip>:<umpire port>/shop_floor/<sf_port>/<token>'
    Test mode: 'http://<umpire ip>:<sf_port>'

    Args:
      shop_floor_handler: A string containing the shopfloor handler information
        from parsed resource map like '/shop_floor/1234'.
    """
    if self._test_mode:
      umpire_scheme_host, _ = urllib2.splitport(self._server_uri)
      search_port = re.search(r'/shop_floor/(\d+)', shop_floor_handler)
      if not search_port:
        raise UmpireServerProxyException(
            'shopfloor handler format is not correct' % shop_floor_handler)
      shop_floor_handler_port = int(search_port.group(1))
      self._shop_floor_handler_uri = '%s:%d' % (
          umpire_scheme_host, shop_floor_handler_port)
    else:
      self._shop_floor_handler_uri = '%s%s/%s' % (
          self._server_uri, shop_floor_handler, self._token)

  def _ParseResourceMap(self, resource_map_content):
    """Parses resource map and returns a dict.

    The resource map contains the resources which belong to a bundle that
    should serve this DUT. E.g.

    id: 'spring_lte_fw1.44.31'
    note: 'Bundle for Spring LTE with firmware 1.44.31'
    __token__: fe8082c1
    shop_floor_handler: /shop_floor/9001
    server_factory_toolkit: factory.tar.bz2#[version]#[hash]
    device_factory_toolkit: factory.tar.bz2#[version]#[hash]
    netboot_vmlinux: 'vmlinux#[version]#[hash]'
    complete_script: 'complete.gz##[hash]'

    Args:
      resource_map_content: The content of resource map.

    Returns:
      A dict parsed from resource map.

    Raises:
      UmpireServerProxyException: If resource map is missing any
        field in REQUIRED_RESOURCE_MAP_FIELDS.
    """
    result = ParseDict(lines=resource_map_content.splitlines(),
                       delimeter=':')
    missing_fields = REQUIRED_RESOURCE_MAP_FIELDS - set(result)
    if missing_fields:
      logging.error('Missing fields in resource map: %r', missing_fields)
      raise UmpireServerProxyException(
          'Missing fields in resource map: %r' % missing_fields)
    logging.debug('Getting parsed resource map: %r', result)
    return result

  def _GetResources(self):
    """Gets resource map from umpire and set self._resources."""
    logging.info('Requesting Umpire for resource map')
    resourcemap = self._GetResourceMap()
    self._resources = self._ParseResourceMap(resourcemap)

  def _RequestUmpireForResourceMapAndSetHandler(self):
    """Gets new token and shopfloor handler URI from Umpire.

    Also, update Umpire handler methods queried from Umpire handler
    introspection.
    """
    # Gets resource map from Umpire server and sets token and shopfloor
    # handler URI.
    self._GetResources()
    token = self._resources['__token__']
    shop_floor_handler = self._resources['shop_floor_handler']
    logging.info('Receive token %r and shop_floor_handler %r', token,
                 shop_floor_handler)

    self._SetToken(token)
    self._SetShopFloorHandlerUri(shop_floor_handler)
    self._UpdateShopFloorHandler()
    self._UpdateUmpireHandlerMethods()

  def _UpdateUmpireHandlerMethods(self):
    """Updates _umpire_methods by querying Umpire XMLRPC handler.

    In this method, we assume token is valid since it was just updated in
    _RequestUmpireForResourceMapAndSetHandler.
    """
    self._umpire_methods = set(self.__request('system.listMethods', ()))
    logging.debug('Umpire server methods: %r', self._umpire_methods)

  def _UpdateShopFloorHandler(self):
    """Updates _shop_floor_handler_server_proxy for new URI."""
    logging.debug('Init a server proxy to shopfloor handler at %s',
                  self._shop_floor_handler_uri)
    self._shop_floor_handler_server_proxy = xmlrpclib.ServerProxy(
        self._shop_floor_handler_uri,
        *self._args, **self._kwargs)

  def _CallHandler(self, methodname, params):
    """Calls XMLRPC handler through server proxy.

    The handler will be either Umpire XMLRPC handler, or shopfloor handler,
    depending on the methodname. Note that this method is used when _use_umpire
    is True.
    Args:
      methodname: Name of the method to call that is registered on XMLRPC
        handler.
      params: A tuple containing the args to methodname call.

    Returns:
      The return value of the shopfloor call.
    """
    logging.debug('_CallHandler with methodname: %r, params: %r',
                  methodname, params)
    # Makes RPC request based on the category of the XMLRPC (either an
    # Umpire RPC or a ShopFloorHandler RPC).
    if methodname in self._umpire_methods:
      logging.debug(
          'Calling method %s with params %r using Umpire server proxy %s',
          methodname, params, self._umpire_handler_uri)
      result = self.__request(methodname, params)
    else:
      logging.debug(
          'Calling method %s with params %r using shopfloor server proxy %s',
          methodname, params, self._shop_floor_handler_uri)
      result = self._shop_floor_handler_server_proxy.__getattr__(
          methodname)(*params)
    logging.debug('Get result %r', result)
    return result

  def _Request(self, methodname, params):
    """Main entry point for this server proxy.

    Args:
      methodname: Name of the method to call that is registered on XMLRPC
        handler.
      params: A tuple containing the args to methodname call.

    Returns:
      The return value of the shopfloor call.
    """
    logging.debug(
        'Using UmpireServerProxy _Request method with methodname: %r,'
        ' params: %r', methodname, params)

    # Using Umpire or not is not decided yet. Tries to decide it and initializes
    # proxies if needed. Raises exception if it still can not be decided.
    if self._use_umpire is None:
      logging.warning('Need to decide using Umpire or not')
      self._Init(raise_exception=True)

    # Not using Umpire. Uses __request in base class.
    if not self._use_umpire:
      result = self.__request(methodname, params)
      return result

    # No current token yet. Requests shopfloor handler from Umpire server.
    if not self._token:
      self._RequestUmpireForResourceMapAndSetHandler()

    # Checks if there is change in client info.
    if self._umpire_client_info.Update():
      logging.info('Client info has changed')
      self._RevokeToken()
      self._RequestUmpireForResourceMapAndSetHandler()

    num_tries = 0
    success_called = False
    while num_tries < self._max_retries:
      invalid_token = False
      # Handles the invalid token case.
      try:
        result = self._CallHandler(methodname, params)
        success_called = True
        break
      except xmlrpclib.ProtocolError as e:
        # Token is invalid. Gets a new resource map and a new shopfloor handler.
        if CheckProtocolError(e, ERROR_TOKEN_INVALID):
          logging.warning(
              'Got ERROR_TOKEN_INVALID. Request handler from Umpire server'
              ' again')
          invalid_token = True
          num_tries += 1
          self._RequestUmpireForResourceMapAndSetHandler()

        else:
          raise UmpireServerProxyException(
              'ProtocolError: %s with code %d, message %s' % (
                  e, e.errcode, e.errmsg))
    if not success_called:
      if invalid_token:
        raise UmpireServerProxyException(
            'Invalid token after %d retries' % self._max_retries)

    return result

  def _SetToken(self, token):
    """Sets the token.

    Args:
      token: The token to be set.
    """
    self._token = token
    logging.info('Setting token: %r', self._token)

  def _RevokeToken(self):
    """Revokes the token."""
    logging.debug('Revoking token: %r', self._token)
    self._token = None

  def __getattr__(self, name):
    # Same magic dispatcher as that in xmpliclib.ServerProxybase but using
    # self._Request instead of  _request in the base class.
    return xmlrpclib._Method(self._Request, name)  # pylint: disable=W0212


class TimeoutUmpireServerProxy(UmpireServerProxy):
  """UmpireServerProxy supporting timeout."""
  def __init__(self, server_uri, timeout=10, *args, **kwargs):
    """Initializes UmpireServerProxy with its transport supporting timeout.

    Args:
      server_uri: server_uri passed to UmpireServerProxy. Checks the docstrings
        in UmpireServerProxy.
      timeout: Timeout in seconds for a method called through this proxy.
      *args: The arguments passed to UmpireServerProxy.
      **kwargs: The keyword arguments passed to UmpireServerProxy.

    Raises:
      socket.error: If timeout is reached before the call is finished.
    """
    if timeout:
      logging.debug('Using TimeoutUmpireServerProxy with timeout %r seconds',
                    timeout)
      kwargs['transport'] = net_utils.TimeoutXMLRPCTransport(
        timeout=timeout)
    UmpireServerProxy.__init__(self, server_uri, *args, **kwargs)
