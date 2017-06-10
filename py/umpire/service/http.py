# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HTTP service for static image and shopfloor frontend."""

import os
import shutil

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire import config
from cros.factory.umpire.service import umpire_service
from cros.factory.utils import file_utils
from cros.factory.utils.schema import FixedDict
from cros.factory.utils.schema import List
from cros.factory.utils.schema import Scalar


CONFIG_SCHEMA = {
    'optional_items': {
        'reverse_proxies': List(
            'Reverse proxy list',
            FixedDict('Proxy IP range',
                      items={'proxy_addr': Scalar('IP address', str),
                             'remoteip': Scalar('DUT ip range', str)}))}}

HTTP_BIN = '/usr/sbin/nginx'
HTTP_SERVICE_NAME = 'httpsvc'

# Nginx config filename with hash of the file.
NGINX_CONFIG_FILENAME = 'nginx_#%s#.conf'

# String template for handlers.
# %d is the binding port of its corresponding shop floor handler XMLRPC
# running locally.
SHOP_FLOOR_HANDLER_PATH = common.HANDLER_BASE + '/%d/'

# Prefixes use in nginx proxy config:
# Handles RPC requests to / and /RPC2.
ROOT_RPC_PREFIX = '/RPC2'
# Handles Umpire RPC.
UMPIRE_RPC_PREFIX = '/umpire'
# Handles /resourcemap request
RESOURCEMAP_APP_PREFIX = '/resourcemap'
# Handles POST request
POST_PREFIX = '/post'
LEGACY_POST_PREFIX = '/upload'
# Handles Instalog HTTP plugin request
INSTALOG_PREFIX = '/instalog'

NGINX_CONFIG_TEMPLATE = """
user root;
worker_processes auto;
daemon off;

error_log %(error_log)s warn;
pid %(pid_file)s;

events {
  worker_connections 1024;
}

http {
  include /etc/nginx/mime.types;

  log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                  '$status $body_bytes_sent "$http_referer" '
                  '"$http_user_agent" "$http_x_forwarded_for"';
  access_log %(access_log)s main;

  sendfile on;
  tcp_nopush on;

  keepalive_timeout 65;

  gzip on;
  autoindex on;

  geo $reverse_proxy_ip_range {
    default 0;
    %(reverse_proxy_ips)s
  }

  server {
    listen %(http_port)s;

    server_name localhost;
    charset utf-8;

    client_max_body_size 8G;

    location /res {
      %(reverse_proxies)s

      alias %(resources_dir)s;
    }

    %(http_proxies)s
  }
}
"""

NGINX_PROXY_TEMPLATE = """
location %(location_rule)s {
  proxy_pass http://localhost:%(port)d;
  proxy_set_header Host $http_host;
}
"""

NGINX_REVERSE_PROXY_TEMPLATE = """
if ($reverse_proxy_ip_range = %(reverse_proxy_ip_index)d) {
  return 307 $scheme://%(proxy_addr)s$request_uri;
}
"""


class HTTPService(umpire_service.UmpireService):
  """HTTP service.

  Example:
    svc = SimpleService()
    procs = svc.CreateProcesses(umpire_config_dict)
    svc.Start(procs)
  """

  def CreateProcesses(self, umpire_config, env):
    """Creates list of processes via config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      A list of ServiceProcess.
    """
    nginx_conf = self.GenerateNginxConfig(umpire_config, env)
    # Shall we raise UmpireError if there's no http server?
    if not nginx_conf:
      return []
    proc_config = {
        'executable': HTTP_BIN,
        'name': HTTP_SERVICE_NAME,
        'args': ['-c', nginx_conf],
        'path': '/tmp'}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(proc_config)
    return [proc]

  @staticmethod
  def GenerateNginxConfig(umpire_config, env):
    """Generates a nginx config.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.

    Returns:
      Path to nginx config (w/ the config's hash in filename).
      None if a nginx config failed to generate.
    """
    if ('services' not in umpire_config or
        'http' not in umpire_config['services']):
      return None

    with file_utils.UnopenedTemporaryFile() as temp_path:
      HTTPService._GenerateNginxConfigImpl(umpire_config, env, temp_path)
      md5 = file_utils.MD5InHex(temp_path)
      config_path = os.path.join(env.config_dir, NGINX_CONFIG_FILENAME % md5)
      # Use shutil.move() instead of os.rename(). os.rename calls OS
      # rename() function. And under Linux-like OSes, this system call
      # creates and removes hardlink, that only works when source path and
      # destination path are both on same filesystem.
      shutil.move(temp_path, config_path)
    return config_path

  @staticmethod
  def _GenerateNginxConfigImpl(umpire_config, env, config_path):
    """Real implementation of GenerateNginxConfig.

    It writes config to config_path.

    Args:
      umpire_config: Umpire config dict.
      env: UmpireEnv object.
      config_path: path to config file to write.
    """
    http_config = umpire_config['services']['http']
    httpd_port = int(env.umpire_base_port)
    shopfloor_port = env.shopfloor_start_port

    # Umpire common RPCs
    umpire_proxy_handlers = []
    # python xmlrpclib calls http://host/RPC2 for ServerProxy('http://host')
    umpire_proxy_handlers.append((ROOT_RPC_PREFIX, env.umpire_rpc_port))
    umpire_proxy_handlers.append((UMPIRE_RPC_PREFIX, env.umpire_rpc_port))
    umpire_proxy_handlers.append(('= /', env.umpire_rpc_port))
    # Web applications
    umpire_proxy_handlers.append(
        (RESOURCEMAP_APP_PREFIX, env.umpire_webapp_port))
    # POSTrequests
    umpire_proxy_handlers.append((POST_PREFIX, env.umpire_http_post_port))
    # POST (legacy URL)
    umpire_proxy_handlers.append(
        (LEGACY_POST_PREFIX, env.umpire_http_post_port))
    # Instalog HTTP plugin
    umpire_proxy_handlers.append(
        (INSTALOG_PREFIX, env.umpire_instalog_http_port))
    # Shop floor handlers XMLRPC proxy bindings.
    for port in xrange(shopfloor_port,
                       shopfloor_port + config.NUMBER_SHOP_FLOOR_HANDLERS):
      match_path = SHOP_FLOOR_HANDLER_PATH % port
      umpire_proxy_handlers.append((match_path, port))

    config_proxies_str = [
        NGINX_PROXY_TEMPLATE % {
            'location_rule': location_rule,
            'port': port
        } for location_rule, port in umpire_proxy_handlers
    ]

    reverse_proxy_ips = []
    reverse_proxies_str = []

    if 'reverse_proxies' in http_config:
      for idx, proxy in enumerate(http_config['reverse_proxies'], start=1):
        reverse_proxy_ips.append('%s %d;' % (proxy['remoteip'], idx))
        reverse_proxies_str.append(
            NGINX_REVERSE_PROXY_TEMPLATE %
            {'reverse_proxy_ip_index': idx, 'proxy_addr': proxy['proxy_addr']})

    config_str = NGINX_CONFIG_TEMPLATE % {
        'pid_file': os.path.join(env.pid_dir, 'httpd.pid'),
        'http_port': httpd_port,
        'access_log': os.path.join(env.log_dir, 'httpd_access.log'),
        'error_log': os.path.join(env.log_dir, 'httpd_error.log'),
        'resources_dir': env.resources_dir,
        'reverse_proxy_ips': '\n'.join(reverse_proxy_ips),
        'http_proxies': '\n'.join(config_proxies_str),
        'reverse_proxies': '\n'.join(reverse_proxies_str)
    }
    file_utils.WriteFile(config_path, config_str)
