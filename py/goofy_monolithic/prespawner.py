# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
A library to prespawn autotest processes to minimize startup overhead.
'''

import cPickle as pickle
import logging
import os
import subprocess
import threading
from Queue import Queue


import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn


NUM_PRESPAWNED_PROCESSES = 1
PRESPAWNER_PATH = '/usr/local/autotest/bin/prespawner.py'


class Prespawner():
  def __init__(self):
    self.prespawned = Queue(NUM_PRESPAWNED_PROCESSES)
    self.thread = None
    self.terminated = False

  def spawn(self, args, env_additions=None):
    '''
    Spawns a new autotest (reusing an prespawned process if available).

    @param args: A list of arguments (sys.argv)
    @param env_additions: Items to add to the current environment
    '''
    new_env = dict(os.environ)
    if env_additions:
      new_env.update(env_additions)

    process = self.prespawned.get()
    # Write the environment and argv to the process's stdin; it will launch
    # autotest once these are received.
    pickle.dump((new_env, args), process.stdin, protocol=2)
    process.stdin.close()
    return process

  def start(self):
    '''
    Starts a thread to pre-spawn autotests.
    '''
    def run():
      while not self.terminated:
        process = Spawn(
          ['python', '-u', PRESPAWNER_PATH,
           '--prespawn_autotest'],
          cwd=os.path.dirname(PRESPAWNER_PATH),
          stdin=subprocess.PIPE)
        logging.debug('Pre-spawned an autotest process %d', process.pid)
        self.prespawned.put(process)

      # Let stop() know that we are done
      self.prespawned.put(None)

    if not self.thread and os.path.exists(PRESPAWNER_PATH):
      self.thread = threading.Thread(target=run, name='Prespawner')
      self.thread.start()

  def stop(self):
    '''
    Stops the pre-spawn thread gracefully.
    '''
    if not self.thread:
      # Never started
      return

    self.terminated = True
    # Wait for any existing prespawned processes.
    while True:
      process = self.prespawned.get()
      if not process:
        break
      # Send a 'None' environment and arg list to tell the prespawner
      # processes to exit.
      pickle.dump((None, None), process.stdin, protocol=2)
      process.stdin.close()
      process.wait()
    self.thread = None
