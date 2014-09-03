# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""HTTP service for static image and shopfloor frontend."""

import multiprocessing
import os
import shutil

import factory_common  # pylint: disable=W0611
from cros.factory.schema import FixedDict, List, Scalar
from cros.factory.umpire import common
from cros.factory.umpire.common import RESOURCE_HASH_DIGITS
from cros.factory.umpire.config import NUMBER_SHOP_FLOOR_HANDLERS
from cros.factory.umpire.service.indent_text_writer import IndentTextWriter
from cros.factory.umpire.service import umpire_service
from cros.factory.utils import file_utils


_LOCALHOST = '127.0.0.1'

CONFIG_SCHEMA = {
    'optional_items': {
        'reverse_proxies': List(
            'Reverse proxy list',
            FixedDict('Proxy IP range',
                      items={'proxy_addr': Scalar('IP address', str),
                             'remoteip': Scalar('DUT ip range', str)}))}}

HTTP_BIN = '/usr/sbin/lighttpd'
HTTP_SERVICE_NAME = 'httpsvc'
LIGHTY_MODULES = ['mod_access', 'mod_accesslog', 'mod_alias', 'mod_fastcgi',
                  'mod_proxy', 'mod_rewrite', 'mod_redirect']

# Lighty config filename with hash of the file.
LIGHTY_CONFIG_FILENAME = 'lighttpd_#%s#.conf'

# String template for handlers.
# %d is the binding port of its corresponding shop floor handler FastCGI
# running locally.
SHOP_FLOOR_HANDLER_PATH = '/shop_floor/%d/'
# It is used for lighttpd fastcgi module. With leading and trailing shash,
# it is treated as prefix and reques URL's path is passing to FastCGI as
# SCRIPT_NAME.
# See http://redmine.lighttpd.net/projects/1/wiki/Docs_ModFastCGI for
# reference.

# Prefixes use in lighty proxy config:
# Handles RPC requests to / and /RPC2.
ROOT_RPC_PREFIX = '/RPC2'
# Handles Umpire RPC.
UMPIRE_RPC_PREFIX = '/umpire'
# Handles /resourcemap request
RESOURCEMAP_APP_PREFIX = '/resourcemap'

# Maximum number of file descriptors when run as root
HTTPD_MAX_FDS = 32768
# Maximum number of connections
HTTPD_MAX_CONN = HTTPD_MAX_FDS / 2


class LightyConditional(str):

  """A str wrapper to tag the string as a Lighty conditional.

  For ordinary (key, value), its output is "key = value".
  For Lighty conditional (key, value), its output is "key value".
  Note that the key should be of the form "<field> <operator> <value>",
  e.g. '$SERVER["socket"] == ":8080"'.
  """
  pass


class HTTPService(umpire_service.UmpireService):

  """HTTP service.

  Example:
    svc = SimpleService()
    procs = svc.CreateProcesses(umpire_config_dict)
    svc.Start(procs)
  """

  def __init__(self):
    super(HTTPService, self).__init__()

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """
    lighty_conf = self.GenerateLightyConfig(umpire_config, env)
    # Shall we raise UmpireError if there's no http server?
    if not lighty_conf:
      return []
    proc_config = {
        'executable': HTTP_BIN,
        'name': HTTP_SERVICE_NAME,
        'args': ['-D', '-f', lighty_conf],
        'path': '/tmp'}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]

  @staticmethod
  def GenerateLightyConfig(umpire_config, env):
    """Generates a lighty config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      Path to lighty config (w/ the config's hash in filename).
      None if a lighty config failed to generate.
    """
    if ('services' not in umpire_config or
        'http' not in umpire_config['services']):
      return None

    with file_utils.UnopenedTemporaryFile() as temp_path:
      HTTPService._GenerateLightyConfigImpl(umpire_config, env, temp_path)
      md5 = file_utils.Md5sumInHex(temp_path)
      config_path = os.path.join(
          env.config_dir,
          LIGHTY_CONFIG_FILENAME % md5[:RESOURCE_HASH_DIGITS])
      # Use shutil.move() instead of os.rename(). os.rename calls OS
      # rename() function. And under Linux-like OSes, this system call
      # creates and removes hardlink, that only works when source path and
      # destination path are both on same filesystem.
      shutil.move(temp_path, config_path)
    return config_path

  @staticmethod
  def _GenerateLightyConfigImpl(umpire_config, env, config_path):
    """Real implemtation of GenerateLightyConfig.

    It writes config to config_path.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.
      config_path: path to config file to write.
    """
    config_writer = LightyConfigWriter(config_path)

    http_config = umpire_config['services']['http']
    httpd_bind_address = umpire_config['ip']
    httpd_port = int(umpire_config['port'])
    fcgi_port = env.fastcgi_start_port
    cpu_count = multiprocessing.cpu_count()

    # A minimal lighty config
    lighty_conf = {
        # Network binding.
        'server.bind': httpd_bind_address,
        'server.port': httpd_port,
        # Aliases.
        'alias.url': {'/res': env.resources_dir},
        # Server tag and modules.
        'server.tag': 'usf-httpd',
        'server.modules': LIGHTY_MODULES,
        # Document root, files and dirs.
        # TODO(deanliao): check if the document-root is still valid.
        'index-file.names': ['index.html'],
        'dir-listing.activate': 'enable',
        'server.follow-symlink': 'enable',
        'server.range-requests': 'enable',
        'server.document-root': os.path.join(env.base_dir, 'dashboard'),
        # PID and logs
        'server.pid-file': os.path.join(env.pid_dir, 'httpd.pid'),
        'accesslog.filename': os.path.join(env.log_dir, 'httpd_access.log'),
        'server.errorlog': os.path.join(env.log_dir, 'httpd_error.log'),
        # Performance options
        'server.max-worker': cpu_count * 2,
        'server.max-fds': HTTPD_MAX_FDS,
        'server.max-connections': HTTPD_MAX_CONN,
        'connection.kbytes-per-second': 0,
        'server.kbytes-per-second': 0,
    }

    config_writer.Write(lighty_conf)

    # Service FastCGI bindings.
    fastcgi_conf = {}
    for instance in umpire_service.FindServicesWithProperty(
        env.config, 'fastcgi_handlers'):
      for handler in instance.properties['fastcgi_handlers']:
        match_path = handler.get('path', None)
        port_offset = handler.get('port_offset', None)
        if match_path and port_offset:
          fastcgi_conf[match_path] = [{
              'host': _LOCALHOST,
              'port': port_offset + env.config['port'],
              'check-local': 'disable'}]
        else:
          raise common.UmpireError('empty fastcgi handler in %s' %
                                   instance.modulename)
    # Shop floor handlers FastCGI bindings.
    for port in xrange(fcgi_port, fcgi_port + NUMBER_SHOP_FLOOR_HANDLERS):
      match_path = SHOP_FLOOR_HANDLER_PATH % port
      fastcgi_conf[match_path] = [{
          'host': _LOCALHOST,
          'port': port,
          'check-local': 'disable'}]
    config_writer.Write({'fastcgi.server': fastcgi_conf})
    # Umpire common RPCs
    umpire_proxy_handlers = {}
    umpire_proxy_handlers[ROOT_RPC_PREFIX] = [{
        'host': _LOCALHOST,
        'port': env.umpire_rpc_port}]
    umpire_proxy_handlers[UMPIRE_RPC_PREFIX] = [{
        'host': _LOCALHOST,
        'port': env.umpire_rpc_port}]
    # Web applications
    umpire_proxy_handlers[RESOURCEMAP_APP_PREFIX] = [{
        'host': _LOCALHOST,
        'port': env.umpire_webapp_port}]
    config_writer.Write({'proxy.server': umpire_proxy_handlers})

    # Generate conditional HTTP accelerator blocks.
    if 'reverse_proxies' in http_config:
      reverse_proxy_conf = {}
      for proxy in http_config['reverse_proxies']:
        cond = LightyConditional(
            '$HTTP["remoteip"] == "%s"' % proxy['remoteip'])
        redirect = {'url.redirect': {
            '^/res/(.*)': 'http://%s/res/$1' % proxy['proxy_addr']}}
        reverse_proxy_conf[cond] = redirect
      config_writer.Write(reverse_proxy_conf)

    config_writer.Close()


# Create a dummy HTTPService object.
# During the first instantiate process, its parent constructor registers its
# class name to _INSTANCE_MAP, a global variable.
dummy_http_service = HTTPService()


class LightyConfigWriter(object):

  """Writer for Lighty httpd config.

  It opens a file for write (or append) in constructor, and uses Write() to
  write a top-level Lighty config (key-value pairs) to the file.

  Usage:
    writer = LightyConfigWriter('/var/umpire/conf/httpd.conf')
    conf = {'server.bind': '10.0.0.1',
            'server.port': 9001,
            ...}
    writer.Write(conf)
    writer.Close()
  """

  def __init__(self, path, append=False):
    """Opens a file for http config.

    Args:
      path: path to Lighty config file.
      append: True to append the config.
    """
    self._file = open(path, 'a' if append else 'w')
    self._writer = IndentTextWriter(indent_first_line=False)

  def __del__(self):
    self.Close()

  def Close(self):
    """Closes the file."""
    if self._file:
      self._file.close()

  def Write(self, conf):
    """Writes a top-level Lighty config into lighty config file.

    Args:
      conf: a top-level Lighty config in key-value pairs.
    """
    self._file.write(
        self.LightyBlock(conf, self._writer, top_block=True))
    self._file.write('\n')

  @staticmethod
  def LightyBlock(input_dict, parent_writer, top_block=False):
    """Converts an input dict to a Lighty config block.

    If it is not top-level block, the block is indented and a pair of bracket
    is added before and after the block. Also, for each item, a ',' is appended
    in each key-value pair, too.

    Args:
      input_dict: input to convert.
      parent_writer: its parent's IndentTextWriter. Used to set indentation
          level and base indentation for the block.
      top_block: True to set it as top-level block.

    Returns:
      A string in Lighty config block format.
    """
    if top_block:
      writer = parent_writer
      colon = ''
    else:
      writer = IndentTextWriter.Factory(parent_writer)
      colon = ','
      writer.EnterBlock('{}')

    # Sort key for determininistic output.
    for key in sorted(input_dict):
      if isinstance(key, LightyConditional):
        op = ' '
        value = LightyConfigWriter.LightyBlock(input_dict[key], writer)
      else:
        op = ' = '
        value = LightyConfigWriter.LightyAuto(input_dict[key], writer)
      writer.Write(''.join([key, op, value, colon]))

    if not top_block:
      writer.ExitBlock()
    return writer.Flush()

  @staticmethod
  def LightyAuto(input_value, parent_writer):
    """Detects input value type and converts to a Lighty config string.

    Args:
      input_value: input value.
      parent_writer: its parent's IndentTextWriter.

    Returns:
      A string in Lighty config format.
    """
    def LightyDict():
      writer = IndentTextWriter.Factory(parent_writer)
      writer.EnterBlock('()')
      # Sort key for determininistic output.
      for key in sorted(input_value):
        writer.Write('"%s" => %s,' % (
            key,
            LightyConfigWriter.LightyAuto(input_value[key], writer)))
      writer.ExitBlock()
      return writer.Flush()

    def LightyList():
      writer = IndentTextWriter.Factory(parent_writer)
      writer.EnterBlock('()')
      for v in input_value:
        writer.Write('%s,' % LightyConfigWriter.LightyAuto(v, writer))
      writer.ExitBlock()
      return writer.Flush()

    if isinstance(input_value, dict):
      return LightyDict()
    elif isinstance(input_value, list):
      return LightyList()
    elif isinstance(input_value, (int, long)):
      return str(input_value)
    elif isinstance(input_value, basestring):
      return '"%s"' % input_value
    else:
      raise ValueError('Invalid Lighty configuration value')
