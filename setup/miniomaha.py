#!/usr/bin/python

# Copyright (c) 2009-2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A CherryPy-based webserver to host factory installation."""

# This a special fork from devserver for serving factory and may be executed in
# a very limited environment without full CrOS source tree.

import cherrypy
import glob
import optparse
import os
import shutil
import socket
import sys
import threading
import time

import get_recovery_image
import miniomaha_engine

CACHED_ENTRIES = 12


def _LogUpdateMessage(message):
  cherrypy.log(message, 'UPDATE')


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


class UpdateChecker(object):
  """Class for doing peridically update check."""

  def __init__(self, opts, script_dir, cache_dir, _updater, lock):
    self.opts = opts
    self.script_dir = script_dir
    self.cache_dir = cache_dir
    self.updater = _updater
    self.update_lock = lock
    self.timer = None
    self.base_dir = os.path.realpath(self.opts.data_dir)
    self.next_version = 1
    self._UpdateCheck()

  def _CleanUpConfig(self):
    """Put the updated files into initial position"""
    if self.updater.GetActiveConfigIndex() == 1:
      # No update
      return
    initial_config = self.updater.GetConfig(0)
    last_config = self.updater.GetConfig(self.updater.GetActiveConfigIndex())
    # Parse initial dir for initial_dir/board/release_image
    initial_dir = os.path.dirname(initial_config[0]['release_image'])
    initial_dir = os.path.dirname(initial_dir)
    initial_dir = os.path.join(self.base_dir, initial_dir)

    # Move the final version of each board into initial dir
    for board_conf in last_config:
      board_dir = os.path.dirname(board_conf['release_image'])
      board_dir = os.path.join(self.base_dir, board_dir)
      board_name = os.path.basename(board_dir)
      target_dir = os.path.join(initial_dir, board_name)

      if os.path.samefile(board_dir, target_dir):
        continue
      if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)
      shutil.move(board_dir, target_dir)

      # Correct the file path and pop unnecessary keys
      for key in board_conf.copy().iterkeys():
        if key.endswith('_image'):
          board_conf[key] = os.path.join(target_dir,
                                         os.path.basename(board_conf[key]))
        elif key.endswith('_size'):
          board_conf.pop(key)

    # Overwrite the config file
    with open(self.opts.factory_config, 'w') as file_handle:
      file_handle.write('config=%s\n' % last_config)

    # Remove _ver*/
    for version in glob.glob(os.path.join(self.base_dir, '_ver*')):
      shutil.rmtree(version)

  def _UpdateCheck(self):
    """Do update check periodically."""
    # Initialize preparer and updater
    if not os.path.exists(self.cache_dir):
      os.makedirs(self.cache_dir)
    image_updater = get_recovery_image.ImageUpdater()
    image_preparer = get_recovery_image.OmahaPreparer(self.script_dir,
                                                      self.cache_dir)
    # Try to update all boards in config
    updated_boards = []
    active_config = self.updater.GetConfig(self.updater.GetActiveConfigIndex())
    for board_conf in active_config:
      # The format in config is qual_id: set(['board'])
      for board in board_conf['qual_ids']:
        updated = image_updater.update_image(board, self.cache_dir)
        if updated:
          updated_boards.append(board)
          _LogUpdateMessage('Detect update for board %s' % board)

    if not updated_boards:
      _LogUpdateMessage('Everything up-to-date, update check finished')
    else:
      _LogUpdateMessage('Start updating')
      version_offset = '_ver%s' % self.next_version
      self.next_version += 1

      # Prepare the files for the newly downloaded boards
      image_preparer.set_boards_to_update(updated_boards)
      image_preparer.set_version_offset(version_offset)
      image_preparer.generate_miniomaha_files()
      image_preparer.setup_miniomaha_files()

      data_dir = self.base_dir
      # Change config, critical session
      with self.update_lock:
        # Read config
        config_dir = os.path.join(data_dir, version_offset)
        config_path = os.path.join(config_dir, 'miniomaha.conf')
        self.updater.ImportFactoryConfigFile(config_path , False)

    # Restart timers
    # Time interval between each update check, by seconds
    self.timer = threading.Timer(self.opts.interval, self._UpdateCheck)
    self.timer.daemon = True
    self.timer.start()

  def cleanup(self):
    self.timer.cancel()
    self._CleanUpConfig()

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
  fail_msg = 'Previous session from %s, uuid: %s, start at %s did not complete'
  time_string = '%d/%b/%Y %H:%M:%S'

  def __init__(self, lock, auto_update):
    self.client_table = {}
    self.update_lock = lock
    self.auto_update = auto_update

  def GetClientConfigIndex(self, ip):
    return self.client_table[ip]['config_index']

  def SetClientConfigIndex(self, ip, index):
    self.client_table[ip]['config_index'] = index

  def GetClientStartTime(self, ip):
    return self.client_table[ip]['start_time']

  def SetClientStartTime(self, ip, start_time):
    self.client_table[ip]['start_time'] = start_time

  @cherrypy.expose
  def index(self):
    return 'Welcome to the Dev Server!'

  @cherrypy.expose
  def update(self):
    client_ip = cherrypy.request.remote.ip.split(':')[-1]
    body_length = int(cherrypy.request.headers['Content-Length'])
    data = cherrypy.request.rfile.read(body_length)

    # For backward compatibility of old install shim.
    # Updater should work anyway.
    if client_ip not in self.client_table:
      if self.auto_update:
        _LogUpdateMessage(
            'WARNING: Detect unrecorded ip: %s. '
            'If you are using an old factory install shim, '
            'there may be unexpected outcome in --auto_update mode' %
            client_ip)
      return updater.HandleUpdatePing(data, updater.GetActiveConfigIndex())

    return updater.HandleUpdatePing(data,
                                    self.GetClientConfigIndex(client_ip))

  @cherrypy.expose
  def greetings(self, label, uuid):
    # Temporarily use ip as identifier.
    # This may be changed if we found better session ids
    client_ip = cherrypy.request.remote.ip.split(':')[-1]

    if label != 'hello' and client_ip not in self.client_table:
      _LogUpdateMessage('Unexpected %s notification from %s, uuid: %s' %
                        (label, client_ip, uuid))
      return 'Wrong notification'

    if label == 'hello':
      if client_ip in self.client_table:
        # previous session did not complete, print error to log
        start_time = time.strftime(
            self.time_string,
            time.localtime(self.GetClientStartTime(client_ip)))
        _LogUpdateMessage(self.fail_msg % (client_ip, uuid, start_time))

      self.client_table[client_ip] = {}
      self.SetClientStartTime(client_ip, time.time())
      _LogUpdateMessage('Start a install session for %s, uuid: %s' %
                        (client_ip, uuid))

      with self.update_lock:
        self.SetClientConfigIndex(client_ip, updater.GetActiveConfigIndex())

      return 'hello'

    elif label == 'download_complete':
      _LogUpdateMessage(
          'Session from %s, uuid: %s, '
          'successfully downloaded all necessary files' %
          (client_ip, uuid))
      return 'download complete'

    elif label == 'goodbye':
      elapse_time = time.time() - self.GetClientStartTime(client_ip)
      _LogUpdateMessage(
          'Session from %s, uuid: %s, '
          'has been completed, elapse time is %s seconds' %
          (client_ip, uuid, elapse_time))
      self.client_table.pop(client_ip)
      return 'goodbye'

  #TODO(chunyen): move this to cherrypy exit callback
  def __del__(self):
    # Write log for those incomplete session
    for client_ip in self.client_table:
      start_time = time.strftime(
          self.time_string,
          time.localtime(self.GetClientStartTime(client_ip)))
      _LogUpdateMessage(self.fail_msg % (client_ip, start_time))


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
  parser.add_option('--auto_update', action='store_true', dest='auto_update',
                    help='Enable auto updating image from server')
  parser.add_option('--cache', dest='cache_dir', default=None,
                    help='Cache_dir for auto update images')
  parser.add_option('--interval', dest='interval', default=1800, type=int,
                    help='Interval between each update check')
  parser.set_usage(parser.format_help())
  (options, _) = parser.parse_args()

  static_dir = os.path.realpath(options.data_dir)
  os.system('mkdir -p %s' % static_dir)

  cherrypy.log('Data dir is %s' % options.data_dir, 'DEVSERVER')
  cherrypy.log('Serving from %s' % static_dir, 'DEVSERVER')

  updater = miniomaha_engine.ServerEngine(
      static_dir=static_dir,
      proxy_port=options.proxy_port
  )

  # Sanity-check for use of validate_factory_config.
  # In previous version, the default configuration file is in base_path,
  # but now it is in data_dir,
  # so we want to check both for backward compatibility.
  if not options.factory_config:
    config_files = (os.path.join(base_path, 'miniomaha.conf'),
                    os.path.join(options.data_dir, 'miniomaha.conf'))
    exists = map(os.path.exists, config_files)
    if all(exists):
      parser.error('Confusing factory config files.\n'
                   'Please remove the old config file in %s' % base_path)
    elif any(exists):
      options.factory_config = config_files[exists.index(True)]
    else:
      parser.error('No factory files found')

  updater_lock = threading.Lock()
  updater.ImportFactoryConfigFile(options.factory_config,
                                  options.validate_factory_config)
  if options.auto_update:
    # Set up cache directory.
    options.cache_dir = (options.cache_dir or
                         os.path.join(base_path, 'cache_dir'))
    # Ensure that the configure file in cache directory is the same as that
    # in data directory.
    shutil.copy(options.factory_config, options.cache_dir)
    update_checker = UpdateChecker(options, base_path, options.cache_dir,
                                   updater, updater_lock)

  if not options.validate_factory_config:
    # Since cheerypy need an existing file to append log,
    # here we make sure the log file path exist and ready for writing.
    with open(options.log_path, 'a'):
      pass
    cherrypy.log.screen = True
    cherrypy.log.access_file = options.log_path
    cherrypy.log.error_file = options.log_path
    cherrypy.quickstart(DevServerRoot(updater_lock, options.auto_update),
                        config=_GetConfig(options))
    if options.auto_update:
      update_checker.cleanup()
