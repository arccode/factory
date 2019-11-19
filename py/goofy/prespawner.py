# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A library to prespawn pytest processes to minimize startup overhead.

There are several possible ways to run pytest in a clean environment:

1. Spawn the pytest runner when the pytest is started.
   Even for simple pytests like message, the time it takes to start Python and
   import dependencies takes about 200ms on a ChromeOS laptop, and could take
   much longer for devices with lower computing power.

2. fork and import the pytest module directly.
   There are several global objects (logging, event_log) that we need to reset
   when in the child process, to ensure that the environment when running
   pytest is clean.
   Also, Goofy server itself is multithreaded, and it's generally not a good
   idea to fork from a multithreaded process.

3. Prespawn some process and use them when pytest is started.
   This is the current approach. We prespawn pytest runner in a background
   thread. When pytest is started, we get one prespawned process and feed the
   pytest info to it.
   This avoid the problem in 1. since most common import can be imported by
   pytest runner, and would be done in background before pytest is started.
   Also, it's much easier to ensure that the environment for running pytest is
   clean.

See https://crbug.com/733545, https://chromium-review.googlesource.com/c/603507
for discussions.
"""

import cPickle as pickle
import logging
import os
from Queue import Queue
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.utils import process_utils


NUM_PRESPAWNED_PROCESSES = 1
PYTEST_PRESPAWNER_PATH = os.path.join(paths.FACTORY_DIR,
                                      'py/test/pytest_runner.py')


class Prespawner(object):

  def __init__(self, prespawner_path, prespawner_args, pipe_stdout=False):
    self.prespawned = Queue(NUM_PRESPAWNED_PROCESSES)
    self.thread = None
    self.terminated = False
    self.prespawner_path = prespawner_path
    assert isinstance(prespawner_args, list)
    self.prespawner_args = prespawner_args
    self.pipe_stdout = pipe_stdout

  def spawn(self, args, env_additions=None):
    """Spawns a new process (reusing an prespawned process if available).

    @param args: A list of arguments (sys.argv)
    @param env_additions: Items to add to the current environment
    """
    new_env = dict(os.environ)
    if env_additions:
      new_env.update(env_additions)

    process = self.prespawned.get()
    # Write the environment and argv to the process's stdin; it will launch
    # test once these are received.
    pickle.dump((new_env, args), process.stdin, protocol=2)
    process.stdin.close()
    return process

  def start(self):
    """Starts a thread to pre-spawn pytests.
    """
    def run():
      while not self.terminated:
        if self.pipe_stdout:
          pipe_stdout_args = {'stdout': subprocess.PIPE,
                              'stderr': subprocess.STDOUT}
        else:
          pipe_stdout_args = {}

        process = process_utils.Spawn(
            ['python2', '-u', self.prespawner_path] + self.prespawner_args,
            cwd=os.path.dirname(self.prespawner_path),
            stdin=subprocess.PIPE,
            **pipe_stdout_args)
        logging.debug('Pre-spawned a test process %d', process.pid)
        self.prespawned.put(process)

      # Let stop() know that we are done
      self.prespawned.put(None)

    if not self.thread and os.path.exists(self.prespawner_path):
      self.thread = process_utils.StartDaemonThread(
          target=run, name='Prespawner')

  def stop(self):
    """Stops the pre-spawn thread gracefully.
    """
    self.terminated = True
    if self.thread:
      # Wait for any existing prespawned processes.
      while True:
        process = self.prespawned.get()
        if not process:
          break
        if process.poll() is None:
          # Send a 'None' environment and arg list to tell the prespawner
          # processes to exit.
          pickle.dump((None, None), process.stdin, protocol=2)
          process.stdin.close()
          process.wait()
      self.thread.join()
      self.thread = None


class PytestPrespawner(Prespawner):

  def __init__(self):
    super(PytestPrespawner, self).__init__(
        PYTEST_PRESPAWNER_PATH, [], pipe_stdout=True)
