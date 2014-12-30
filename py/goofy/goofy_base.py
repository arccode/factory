#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Components shared between host and device instances of goofy."""

import logging
import Queue
import os
import sys
import threading
import time
import traceback

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils

RUN_QUEUE_TIMEOUT_SECS = 10

class GoofyBase(object):
  """Base class from which Goofy[Host] and GoofyDevice derive.

  Implements the event loop.

  run_queue: A queue of callbacks to invoke from the main thread.
  exceptions: List of exceptions encountered in invocation threads.
  last_idle: The most recent time of invoking the idle queue handler, or none
  """
  def __init__(self):
    self.run_queue = Queue.Queue()
    self.exceptions = []
    self.last_idle = None

  def main(self):
    """Stub main function. This is meant to be overridden in subclasses."""
    pass

  def run_enqueue(self, val):
    """ Enqueues an object on the event loop

    Generally this is a function. It may also be None to indicate that the
    run queue should shut down.
    """
    self.run_queue.put(val)

  def run(self):
    """Runs Goofy."""
    # Process events forever.
    while self.run_once(True):
      pass

  def run_once(self, block=False):
    """Runs all items pending in the event loop.

    Args:
      block: If true, block until at least one event is processed.

    Returns:
      True to keep going or False to shut down.
    """
    events = utils.DrainQueue(self.run_queue)
    while not events:
      # Nothing on the run queue.
      self._run_queue_idle()
      if block:
        # Block for at least one event...
        try:
          events.append(self.run_queue.get(timeout=RUN_QUEUE_TIMEOUT_SECS))
        except Queue.Empty:
          # Keep going (calling _run_queue_idle() again at the top of
          # the loop)
          continue
        # ...and grab anything else that showed up at the same
        # time.
        events.extend(utils.DrainQueue(self.run_queue))
      else:
        break

    for event in events:
      if not event:
        # Shutdown request.
        self.run_queue.task_done()
        return False

      try:
        event()
      except:  # pylint: disable=W0702
        logging.exception('Error in event loop')
        self.record_exception(traceback.format_exception_only(
            *sys.exc_info()[:2]))
        # But keep going
      finally:
        self.run_queue.task_done()
    return True

  def _run_queue_idle(self):
    """Invoked when the run queue has no events.

    This method must not raise exception.
    """
    now = time.time()
    if (self.last_idle and
        now < (self.last_idle + RUN_QUEUE_TIMEOUT_SECS - 1)):
      # Don't run more often than once every (RUN_QUEUE_TIMEOUT_SECS -
      # 1) seconds.
      return

    self.last_idle = now
    self.perform_periodic_tasks()

  def perform_periodic_tasks(self):
    """ Perform any periodic work. Override point. """
    pass

  def destroy(self):
    """ Performs any shutdown tasks. Override point. """
    self.check_exceptions()

  def check_exceptions(self):
    """Raises an error if any exceptions have occurred in
    invocation threads.
    """
    if self.exceptions:
      raise RuntimeError('Exception in invocation thread: %r' %
                 self.exceptions)

  def record_exception(self, msg):
    """Records an exception in an invocation thread.

    An exception with the given message will be rethrown when
    Goofy is destroyed.
    """
    self.exceptions.append(msg)

  @staticmethod
  def drain_nondaemon_threads():
    """Wait for all non-current non-daemon threads to exit.

    This is performed by the Python runtime in an atexit handler,
    but this implementation allows us to do more detailed logging, and
    to support control-C for abrupt shutdown.
    """
    cur_thread = threading.current_thread()
    all_threads_joined = False
    while not all_threads_joined:
      for thread in threading.enumerate():
        if not thread.daemon and thread.is_alive() and thread is not cur_thread:
          logging.info("Waiting for thread '%s'...", thread.name)
          thread.join()
          # We break rather than continue on because the thread list
          # may have changed while we waited
          break
      else:
        # No threads remain
        all_threads_joined = True
    return all_threads_joined


  @classmethod
  def run_main_and_exit(cls):
    """Instantiate the receiver, run its main function, and exit when done.

    This class method is the "entry point" for goofy_base subclasses.
    It instantiates the receiver and invokes its main function, while
    handling exceptions. When main() finishes (normally or via an exception),
    it exits the process.

    Args:
      cls: 'self', a class object that derives from goofy_base
    """
    goofy = cls()
    try:
      goofy.main()
    except SystemExit:
      # Propagate SystemExit without logging.
      raise
    except KeyboardInterrupt:
      logging.info('Interrupted, shutting down...')
    except:
      # Log the error before trying to shut down
      logging.exception('Error in main loop')
      raise
    finally:
      try:
        # We drain threads manually, rather than letting Python do it,
        # so that we can report to the user which threads are stuck
        goofy.destroy()
        cls.drain_nondaemon_threads()
      except KeyboardInterrupt:
        # We got a keyboard interrupt while attempting to shut down.
        # The user is waiting impatiently! This can happen if threads get stuck.
        # We need to exit via os._exit, not sys.exit, because sys.exit() will
        # run the main thread's atexit handler, which waits for all threads to
        # exit, which is likely how we got stuck in the first place. However, we
        # do want to capture all logs, so we shut down logging gracefully.
        logging.info('Graceful shutdown interrupted, shutting down abruptly')
        logging.shutdown()
        os._exit(1) # pylint: disable=W0212
      # Normal exit path
      sys.exit(0)
