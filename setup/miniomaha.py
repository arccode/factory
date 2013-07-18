#!/usr/bin/python

# Copyright (c) 2009-2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A CherryPy-based webserver to host factory installation."""

# This a special fork from devserver for serving factory and may be executed in
# a very limited environment without full CrOS source tree.

import cherrypy
import optparse
import os
import socket
import sys
import time

import miniomaha_engine

CACHED_ENTRIES = 12

# Sets up global to share between classes.

def _GetConfig(opts):
  """Returns the configuration for the miniomaha."""
  base_config = { 'global':
                  { 'server.log_request_headers': True,
                    'server.protocol_version': 'HTTP/1.1',
                    'server.socket_host':
                      '::' if socket.has_ipv6 else '0.0.0.0',
                    'server.socket_port': int(opts.port),
                    'server.socket_timeout': 6000,
                    'response.timeout': 6000,
                    'tools.staticdir.root':
                      os.path.dirname(os.path.abspath(sys.argv[0])),
                  },
                  '/api':
                  {
                    # Gets rid of cherrypy parsing post file for args.
                    'request.process_request_body': False,
                  },
                  '/update':
                  {
                    # Gets rid of cherrypy parsing post file for args.
                    'request.process_request_body': False,
                    'response.timeout': 10000,
                  },
                  # Sets up the static dir for file hosting.
                  '/static':
                  { 'tools.staticdir.dir': 'static',
                    'tools.staticdir.on': True,
                    'response.timeout': 10000,
                  },
                }

  return base_config


class ApiRoot(object):
  """RESTful API for Dev Server information."""
  exposed = True

  @cherrypy.expose
  def hostinfo(self, ip):
    """Returns a JSON dictionary containing information about the given ip.

    Not all information may be known at the time the request is made. The
    possible keys are:

        last_event_type: int
            Last update event type received.

        last_event_status: int
            Last update event status received.

        last_known_version: string
            Last known version recieved for update ping.

        forced_update_label: string
            Update label to force next update ping to use. Set by setnextupdate.

    See the OmahaEvent class in update_engine/omaha_request_action.h for status
    code definitions. If the ip does not exist an empty string is returned."""
    return updater.HandleHostInfoPing(ip)

  @cherrypy.expose
  def setnextupdate(self, ip):
    """Allows the response to the next update ping from a host to be set.

    Takes the IP of the host and an update label as normally provided to the
    /update command."""
    body_length = int(cherrypy.request.headers['Content-Length'])
    label = cherrypy.request.rfile.read(body_length)

    if label:
      label = label.strip()
      if label:
        return updater.HandleSetUpdatePing(ip, label)
    raise cherrypy.HTTPError(400, 'No label provided.')


class DevServerRoot(object):
  """The Root Class for the Dev Server.

  CherryPy works as follows:
    For each method in this class, cherrpy interprets root/path
    as a call to an instance of DevServerRoot->method_name.  For example,
    a call to http://myhost/build will call build.  CherryPy automatically
    parses http args and places them as keyword arguments in each method.
    For paths http://myhost/update/dir1/dir2, you can use *args so that
    cherrypy uses the update method and puts the extra paths in args.
  """
  api = ApiRoot()
  fail_msg = 'Session from %s, start at %s did not complete\n'
  time_string = '%d/%b/%Y %H:%M:%S'

  def __init__(self, log):
    self.client_table = {}
    self.log = log

  @cherrypy.expose
  def index(self):
    return 'Welcome to the Dev Server!'

  @cherrypy.expose
  def update(self):
    body_length = int(cherrypy.request.headers['Content-Length'])
    data = cherrypy.request.rfile.read(body_length)
    return updater.HandleUpdatePing(data)

  @cherrypy.expose
  def greetings(self, label):
    # Temporarily use ip as identifier.
    # This may be changed if we found better session ids
    client_ip = cherrypy.request.remote.ip.split(':')[-1]

    if label == 'hello':
      if client_ip in self.client_table:
        # previous session did not complete, print error to log
        start_time = time.strftime(
            self.time_string,
            time.localtime(self.client_table[client_ip]['start_time']))
        self.log.write(self.fail_msg % (client_ip, start_time))

      self.client_table[client_ip] = {}
      self.client_table[client_ip]['start_time'] = time.time()
      self.log.write('Start a install session for %s\n' % client_ip)
      return 'hello'

    elif label == 'goodbye':
      if client_ip not in self.client_table:
        print 'Unexpected goodbye from %s' % client_ip
      else:
        elapse_time = time.time() - self.client_table[client_ip]['start_time']
        self.log.write(
            'Session from %s has been completed, elapse time is %s seconds\n'
             % (client_ip, elapse_time))
        self.client_table.pop(client_ip)
      return 'goodbye'

  def __del__(self):
    # Write log for those incomplete session
    for client_ip in self.client_table:
      start_time = time.strftime(
          self.time_string,
          time.localtime(self.client_table[client_ip]['start_time']))
      self.log.write(self.fail_msg % (client_ip, start_time))


if __name__ == '__main__':
  base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
  usage = 'usage: %prog [options]'
  parser = optparse.OptionParser(usage)
  parser.add_option('--data_dir', dest='data_dir',
                    help='Writable directory where static lives',
                    default=os.path.join(base_path,'static'))
  parser.add_option('--factory_config', dest='factory_config',
                    help='Config file for serving images from factory floor.',
                    default=None)
  parser.add_option('--port', default=8080,
                    help='Port for the dev server to use.')
  parser.add_option('--proxy_port', default=None,
                    help='Port to have the client connect to (testing support)')
  parser.add_option('--validate_factory_config', action="store_true",
                    dest='validate_factory_config',
                    help='Validate factory config file, then exit.')
  parser.add_option('--log', dest='log_path',
                    help='Path for server execution log',
                    default=os.path.join(base_path, 'miniomaha.log'))
  parser.set_usage(parser.format_help())
  (options, _) = parser.parse_args()

  static_dir = os.path.realpath(options.data_dir)
  os.system('mkdir -p %s' % static_dir)

  cherrypy.log('Data dir is %s' % options.data_dir, 'DEVSERVER')
  cherrypy.log('Serving from %s' % static_dir, 'DEVSERVER')

  log_file = open(options.log_path)
  updater = miniomaha_engine.ServerEngine(
      static_dir=static_dir,
      factory_config_path=options.factory_config,
      proxy_port=options.proxy_port,
  )

  # Sanity-check for use of validate_factory_config.
  # In previous version, the default configuration file is in base_path,
  # but now it is in data_dir,
  # so we want to check both for backward compatibility
  if not options.factory_config:
    config_files = (os.path.join(base_path, 'miniomaha.conf'),
                    os.path.join(options.data_dir, 'miniomaha.conf'))
    exists = map(os.path.exists, config_files)
    if all(exists):
      parser.error('Confusing factory config files')
    elif any(exists):
      options.factory_config = config_files[exists.index(True)]
    else:
      parser.error('No factory files found')

  updater.ImportFactoryConfigFile(options.factory_config,
                                  options.validate_factory_config)
  if not options.validate_factory_config:
    cherrypy.quickstart(DevServerRoot(log_file), config=_GetConfig(options))

  log_file.close()
