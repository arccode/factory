#!/usr/bin/python -u
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""ServiceManager is a standalone program running in Docker environment.
It is used to pull whole Factory repostiory and manage the life cycle of
Factory HWID Service. This file should have no dependency with factory
python modules.
"""


import argparse
import logging  # TODO(yllin): Replace logging with testlog
from multiprocessing.connection import Listener
import os
import subprocess
import sys
import threading
import time
import traceback

from common import Command, CreateRequest

# Paths in docker host.
_CROS_ROOT = '/usr/src/app/cros/'
_FACTORY_DIR = os.path.join(_CROS_ROOT, 'src/platform/factory')
_RPC_SERVER = os.path.join(_FACTORY_DIR, 'py/hwid/service/rpc_server.py')

# Repo urls
_CHROMIUM_URL = 'https://chromium.googlesource.com/chromiumos/'
_CHROME_INTERNAL_URL = 'https://chrome-internal.googlesource.com/chromeos/'

# A list of (repo_url, targetdirectory) tuple.
_MANAGED_REPOS = [
    (os.path.join(_CHROMIUM_URL, 'platform/factory'), _FACTORY_DIR),
    (os.path.join(_CHROMIUM_URL, 'platform2'),
     os.path.join(_CROS_ROOT, 'src/platform2')),
    (os.path.join(_CHROME_INTERNAL_URL, 'chromeos-hwid'),
     os.path.join(_CROS_ROOT, 'src/platform/chromeos-hwid')),
]

DEFAULT_HWIDSERVICE_PORT = 8181
DEFAULT_COMMAND_PORT = 6000


class ServiceManagerError(Exception):
  pass


class Repository(object):
  """A git respository wrapper."""

  def __init__(self, repo_url, directory):
    """Constructor for Repository.

    Args:
      repo_url: A string, the url to the repository
      directory: A string, the repostiory target path
    """

    self.repo_url = repo_url
    self.directory = directory

  def __str__(self):
    return self.repo_url + ': ' + self.directory

  def Clone(self):
    try:
      logging.info('Cloning repository %s to %s', self.repo_url,
                   self.directory)
      subprocess.check_call(['git', 'clone', self.repo_url, self.directory])
    except subprocess.CalledProcessError:
      logging.error(traceback.format_exc())
      raise ServiceManagerError('Error cloning repository %s' % self.repo_url)

  def Pull(self):
    try:
      logging.info('Pulling repository %s', self.directory)
      subprocess.check_call(['git', '-C', self.directory, 'pull'])
    except subprocess.CalledProcessError:
      logging.error(traceback.format_exc())
      raise ServiceManagerError('Error pulling repository %s' % self.repo_url)


class ServiceManager(object):
  """A service manager for managing the life-cycle of the HWIDService.

  ServiceManager creates the HWIDService by invoking a process and destroys it
  by sending Terminate request via synchronized _cmd_conn.
  """

  def __init__(self, port=DEFAULT_HWIDSERVICE_PORT, update_minutes=24*60):
    """Constructor.

    Args:
      port: An int, the port which HWID Service listens to.

    Attributes:
      _poll_seconds: An int, a time interval for polling repo for updating.
      _port: An int, the port which HWID Service listens to.
      _repos:
      _service:
      _service_path:

    """
    ToSeconds = lambda minutes: minutes * 60
    self._poll_seconds = ToSeconds(update_minutes)
    self._port = port
    self._repos = []
    for _repo, _target in _MANAGED_REPOS:
      self._repos.append(Repository(_repo, _target))
    self._service = None
    self._service_path = _RPC_SERVER

    # Synchronized command connection
    self._authkey = None
    self._cmd_conn = None
    self._cmd_listen_address = ('127.0.0.1', DEFAULT_COMMAND_PORT)
    self._cmd_listener = Listener(self._cmd_listen_address,
                                  authkey=self._authkey)

  def _StartService(self):
    """Start HWID Service."""
    if self._service is not None:
      logging.warning('HWID Service is already up')
      return

    cmd = [
        'python', '-u', self._service_path,
        '--port', str(self._port),
        '--sm-ip', self._cmd_listen_address[0],
        '--sm-port', str(self._cmd_listen_address[1])
    ]
    try:
      self._service = subprocess.Popen(
          cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      logging.info('HWID Service up, listing to port %d. '
                   'Will update in %d seconds.', self._port, self._poll_seconds)
    except OSError:
      raise ServiceManagerError('Error starting HWID Service: %s', cmd)

    try:
      logging.info('Waiting command connection...')
      self._cmd_conn = self._cmd_listener.accept()
      logging.info('Accept command connection from %s.',
                   self._cmd_listener.last_accepted)
    except Exception as e:
      raise ServiceManagerError('Error creating command connection: %s',
                                e.message)

  def _StopService(self):
    """Stop HWID Service."""
    terminate_request = CreateRequest(Command.TERMINATE)
    try:
      logging.info('request: %s', str(terminate_request))
      self._cmd_conn.send(terminate_request)
    except ValueError as e:
      raise ServiceManagerError('Error request object too large: %s', e.message)

    # Terminate request always close the HWIDServer process, either by
    # shutting down the rpc server properly or by killing the rpc server thread.
    try:
      response = self._cmd_conn.recv()
      logging.info('response: %s', str(response))

      if response['uuid'] != terminate_request['uuid']:
        logging.error('The uuid of request and response are different.')
    except EOFError as e:
      logging.error('The command connection is disconnected: %s', e.message)

    self._service = None
    self._cmd_conn.close()
    self._cmd_conn = None
    logging.info('HWID Service down')

  def _ParallelRepoOperation(self, op):
    """Parallel executing a Repository member function for all managed repos.

    Args:
      op: The name of Repository member function to execute.
    """
    threads = []
    for repo in self._repos:
      thr = threading.Thread(target=getattr(repo, op))
      thr.setDaemon(True)
      threads.append(thr)
      thr.start()

    for thr in threads:
      thr.join()

  def RunForever(self):
    """Run HWID Service forever."""
    self._ParallelRepoOperation('Clone')

    self._StartService()
    while True:
      time.sleep(self._poll_seconds)

      self._StopService()
      self._ParallelRepoOperation('Pull')
      self._StartService()


class TestServiceManager(ServiceManager):
  """A ServiceManager for off-line test."""
  def __init__(self, port=DEFAULT_HWIDSERVICE_PORT, update_minutes=1):
    super(TestServiceManager, self).__init__(port, update_minutes)
    self._repos = []  # Clean up the repos

  def _Setup(self):
    logging.info('Setting up HWID Service')


def _SetupLogger():
  """Logging to file and stdout."""
  logger = logging.getLogger()
  stream_handler = logging.StreamHandler(sys.stdout)
  formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
  stream_handler.setFormatter(formatter)
  logger.addHandler(stream_handler)
  logger.setLevel(logging.INFO)


def main():
  arg_parser = argparse.ArgumentParser(description='HWID Service Manager.')
  arg_parser.add_argument(
      '--local-test',
      action='store_true',
      default=False,
      dest='local_test',
      help='local testing')
  arg_parser.add_argument(
      '--update-minutes', type=int, dest='update_minutes', default=14400)
  arg_parser.add_argument(
      '-p', '--port', type=int, dest='port', default=DEFAULT_HWIDSERVICE_PORT)
  args = arg_parser.parse_args()

  _SetupLogger()

  sm = None
  if args.local_test:
    sm = TestServiceManager(port=args.port, update_minutes=args.update_minutes)
  else:
    sm = ServiceManager(port=args.port, update_minutes=args.update_minutes)
  sm.RunForever()


if __name__ == '__main__':
  main()
