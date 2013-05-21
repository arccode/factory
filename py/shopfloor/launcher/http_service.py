# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""HTTP service for static image and shopfloor frontend"""

import multiprocessing
import os

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants
from cros.factory.shopfloor.launcher import env
from cros.factory.shopfloor.launcher.service import ServiceBase


class LightyConditionalType(str):
  pass

class HttpService(ServiceBase):

  # Indent shift width for the generated lighttpd.conf file
  _INDENT_SPACE = 2

  def __init__(self, yamlconf):
    """Generates http server configuration file and sets service args"""
    # Old-style python class, cannot use super() to init.
    ServiceBase.__init__(self)

    self._indent = 0
    httpd_conf = os.path.join(env.runtime_dir, 'lighttpd.conf')
    self._GenerateConfigFile(yamlconf, httpd_conf)
    # Setup a non-daemon mode lighttpd
    svc_conf = {
      'executable': '/usr/sbin/lighttpd',
      'name': 'httpsvc',
      'args': ['-D', '-f', httpd_conf]
    }
    self.SetConfig(svc_conf)

  def _GenerateConfigFile(self, yaml_conf, conf_file):
    """Generates lighty config from YamlConfig."""
    httpd_port = yaml_conf['shopfloor']['port']
    lighty_modules = [
        'mod_access', 'mod_accesslog', 'mod_alias',
        'mod_fastcgi', 'mod_rewrite', 'mod_redirect']
    cpu_count = multiprocessing.cpu_count()
    dashboard_dir = os.path.join(env.runtime_dir, 'dashboard')
    pid_file = os.path.join(env.runtime_dir, 'run', 'httpd.pid')
    access_log = os.path.join(env.runtime_dir, 'log', 'httpd_access.log')
    error_log = os.path.join(env.runtime_dir, 'log', 'httpd_error.log')

    # Verify port
    self.CheckPortPrivilage(httpd_port)
    self.CheckPortPrivilage(env.fcgi_port)
    # A minimal lighty config
    lighty_conf = {
        # Server tag and modules
        'server.tag': 'usf-httpd',
        'server.modules': lighty_modules,
        # Document root, files and dirs
        'index-file.names': ['index.html'],
        'dir-listing.activate': 'enable',
        'server.follow-symlink': 'enable',
        'server.range-requests': 'enable',
        'server.document-root': dashboard_dir,
        'server.pid-file': pid_file,
        # Access log
        'accesslog.filename': access_log,
        'server.errorlog': error_log,
        # Performance options
        'server.max-worker': cpu_count * 2,
        'server.max-fds': constants.HTTPD_MAX_FDS,
        'server.max-connections': constants.HTTPD_MAX_CONN,
        'connection.kbytes-per-second': 0,
        'server.kbytes-per-second': 0,
        # Network options
        'server.bind': env.bind_address,
        'server.port': httpd_port,
        # Blocks section, keep the order
        'alias.url': {'/res': env.GetResourcesDir()},
        LightyConditionalType('$HTTP["url"] =~ "^/$"'): {
          'fastcgi.server': {
              '/': [{
                  'host': '127.0.0.1',
                  'port': env.fcgi_port,
                  'check-local': 'disable' }]}}}

    self._WriteLightyConf(lighty_conf, conf_file)

    if 'network_install' in yaml_conf:
      download_port = yaml_conf['network_install']['port']
      if httpd_port != download_port:
        download_conf = {
            LightyConditionalType(
                '$SERVER["socket"] == ":%d"' % download_port): {}}
        self._WriteLightyConf(download_conf, conf_file, append=True)
      # Generate conditional HTTP accelerator blocks.
      if 'reverse_proxies' in yaml_conf['network_install']:
        map((lambda proxy: self._WriteLightyConf(
            self._ProxyBlock(proxy), conf_file, append=True)),
            yaml_conf['network_install']['reverse_proxies'])
      # Generate default download conf symlink.
      for board, resmap in yaml_conf['network_install']['board'].iteritems():
        link_name = os.path.join(env.GetResourcesDir(), board + '.conf')
        conf_name = os.path.join(env.GetResourcesDir(), resmap['config'])
        try:
          os.unlink(link_name)
        except os.error:
          pass
        os.symlink(conf_name, link_name)

  def _ProxyBlock(self, proxy):
    return {
        LightyConditionalType(
            '$HTTP["remoteip"] == "%s"' % proxy['remoteip']): {
                'url.redirect': {
                    '^/res/(.*)': 'http://%s/res/$1' % proxy['proxy_addr']}}}

  def _WriteLightyConf(self, conf, name, append=False):
    """Writes top level key-value pairs to lighty.conf."""
    mode = 'a' if append else 'w'
    self._ResetIndent()
    with open(name, mode) as f:
      for key, value in conf.iteritems():
        if isinstance(key, LightyConditionalType):
          f.write("%s %s\n" % (key, self._LightyConfBlock(value)))
        else:
          f.write("%s = %s\n" % (key, self._LightyConfAuto(value)))

  def _LightyConfAuto(self, value):
    """Detects and writes value in lighty conf format."""
    if isinstance(value, dict):
      return self._LightyConfDict(value)
    elif isinstance(value, list):
      return self._LightyConfList(value)
    elif isinstance(value, (int, long)):
      return str(value)
    elif isinstance(value, basestring):
      return '"%s"' % value
    else:
      raise ValueError('Invalid lighty configuration value')

  def _LightyConfBlock(self, value_dict):
    """Converts dictionary into light conf block."""
    output = ['{']
    self._IncIndent()
    for key, value in value_dict.iteritems():
      output.append('%s%s = %s,' % (self._GetIndent(), key,
                    self._LightyConfAuto(value)))
    self._DecIndent()
    output.append(self._GetIndent() + '}')
    return '\n'.join(output)

  def _LightyConfDict(self, value_dict):
    """Converts dictionary into lighty conf string."""
    output = ['(']
    self._IncIndent()
    for key, value in value_dict.iteritems():
      output.append('%s"%s" => %s,' % (self._GetIndent(), key,
                    self._LightyConfAuto(value)))
    self._DecIndent()
    output.append(self._GetIndent() + ')')
    return '\n'.join(output)

  def _LightyConfList(self, value_list):
    """Converts python list to lighty conf string."""
    output = ['(']
    self._IncIndent()
    for value in value_list:
      output.append('%s%s,\n' % (self._GetIndent(),
                    self._LightyConfAuto(value)))
    self._DecIndent()
    output.append(self._GetIndent() + ')')
    return '\n'.join(output)

  def _ResetIndent(self):
    self._indent = 0

  def _IncIndent(self):
    self._indent += self._INDENT_SPACE

  def _DecIndent(self):
    self._indent = max(0, self._indent - self._INDENT_SPACE)

  def _GetIndent(self):
    return ' ' * self._indent


Service = HttpService
