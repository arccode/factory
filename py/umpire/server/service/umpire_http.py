# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HTTP service for static images and RPC proxies."""

import os
import shutil

from cros.factory.umpire.server.service import umpire_service
from cros.factory.utils import file_utils


HTTP_BIN = '/usr/sbin/nginx'
HTTP_SERVICE_NAME = 'httpsvc'

# Nginx config filename with hash of the file.
NGINX_CONFIG_FILENAME = 'nginx_#%s#.conf'

# Prefixes use in nginx proxy config:
# Handles RPC requests to / and /RPC2.
ROOT_RPC_PREFIX = '/RPC2'
# Handles Umpire RPC.
UMPIRE_RPC_PREFIX = '/umpire'
# Handles /webapps request and dispatches to corresponding webapp.
WEB_APP_PREFIX = '/webapps'
# Handles legacy /resourcemap request which is moved under /webapps.
RESOURCE_MAP_PREFIX = '/resourcemap'
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
  proxy_pass http://localhost:%(port)d%(changed_path)s;
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
        'umpire_http' not in umpire_config['services']):
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
      os.chmod(config_path, 0o644)
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
    def _append_to_handlers(location_rule, port, changed_path=''):
      umpire_proxy_handlers.append((location_rule, port, changed_path))

    http_config = umpire_config['services']['umpire_http']
    httpd_port = int(env.umpire_base_port)

    # Umpire common RPCs
    umpire_proxy_handlers = []
    # python xmlrpclib calls http://host/RPC2 for ServerProxy('http://host')
    _append_to_handlers(ROOT_RPC_PREFIX, env.umpire_rpc_port)
    _append_to_handlers(UMPIRE_RPC_PREFIX, env.umpire_rpc_port)
    _append_to_handlers('= /', env.umpire_rpc_port)
    # Web applications
    _append_to_handlers(WEB_APP_PREFIX, env.umpire_webapp_port)
    # The legacy client would still access to /resourcemap so needs to pass to
    # /webapps/resourcemap.
    _append_to_handlers(RESOURCE_MAP_PREFIX, env.umpire_webapp_port,
                        WEB_APP_PREFIX + RESOURCE_MAP_PREFIX)
    # Instalog HTTP plugin
    _append_to_handlers(INSTALOG_PREFIX, env.umpire_instalog_http_port)

    config_proxies_str = [
        NGINX_PROXY_TEMPLATE % {
            'location_rule': location_rule,
            'port': port,
            'changed_path': changed_path
        } for location_rule, port, changed_path in umpire_proxy_handlers
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
