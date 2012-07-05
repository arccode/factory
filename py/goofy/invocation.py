#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import fnmatch
import logging
import os
import cPickle as pickle
import pipes
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
import uuid
from optparse import OptionParser
from StringIO import StringIO

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.event import Event
from cros.factory import event_log
from cros.factory.test.factory import TestState
from cros.factory.test import utils
from cros.factory.test import pytests


# Number of bytes to include from the log of a failed test.
ERROR_LOG_TAIL_LENGTH = 8*1024


class PyTestInfo(object):
  def __init__(self, test_list, path, pytest_name, args, results_path):
    self.test_list = test_list
    self.path = path
    self.pytest_name = pytest_name
    self.args = args
    self.results_path = results_path


class TestInvocation(object):
  '''
  State for an active test.
  '''
  def __init__(self, goofy, test, on_completion=None):
    '''Constructor.

    @param goofy: The controlling Goofy object.
    @param test: The FactoryTest object to test.
    @param on_completion: Callback to invoke in the goofy event queue
      on completion.
    '''
    self.goofy = goofy
    self.test = test
    self.thread = threading.Thread(target=self._run,
                     name='TestInvocation-%s' % test.path)
    self.on_completion = on_completion
    self.uuid = event_log.TimedUuid()
    self.env_additions = {'CROS_FACTORY_TEST_PATH': self.test.path,
                'CROS_FACTORY_TEST_INVOCATION': self.uuid}
    self.debug_log_path = None
    self._lock = threading.Lock()
    # The following properties are guarded by the lock.
    self._aborted = False
    self._completed = False
    self._process = None

  def __repr__(self):
    return 'TestInvocation(_aborted=%s, _completed=%s)' % (
      self._aborted, self._completed)

  def start(self):
    '''Starts the test thread.'''
    self.thread.start()

  def abort_and_join(self):
    '''
    Aborts a test (must be called from the event controller thread).
    '''
    with self._lock:
      self._aborted = True
      if self._process:
        utils.kill_process_tree(self._process, 'autotest')
    if self.thread:
      self.thread.join()
    with self._lock:
      # Should be set by the thread itself, but just in case...
      self._completed = True

  def is_completed(self):
    '''
    Returns true if the test has finished.
    '''
    with self._lock:
      return self._completed

  def _invoke_autotest(self):
    '''
    Invokes an autotest test.

    This method encapsulates all the magic necessary to run a single
    autotest test using the 'autotest' command-line tool and get a
    sane pass/fail status and error message out.  It may be better
    to just write our own command-line wrapper for job.run_test
    instead.

    @param test: the autotest to run
    @param dargs: the argument map
    @return: tuple of status (TestState.PASSED or TestState.FAILED) and
      error message, if any
    '''
    assert self.test.autotest_name

    test_tag = '%s_%s' % (self.test.path, self.count)
    dargs = dict(self.test.dargs)
    dargs.update({'tag': test_tag,
            'test_list_path': self.goofy.options.test_list})

    status = TestState.FAILED
    error_msg = 'Unknown'

    try:
      output_dir = '%s/%s-%s' % (factory.get_test_data_root(),
                    self.test.path,
                    self.uuid)
      self.debug_log_path = os.path.join(
        output_dir,
        'results/default/debug/client.INFO')
      if not os.path.exists(output_dir):
        os.makedirs(output_dir)
      tmp_dir = tempfile.mkdtemp(prefix='tmp', dir=output_dir)

      control_file = os.path.join(tmp_dir, 'control')
      result_file = os.path.join(tmp_dir, 'result')
      args_file = os.path.join(tmp_dir, 'args')

      with open(args_file, 'w') as f:
        pickle.dump(dargs, f)

      # Create a new control file to use to run the test
      with open(control_file, 'w') as f:
        print >> f, 'import common, traceback, utils'
        print >> f, 'import cPickle as pickle'
        print >> f, ("success = job.run_test("
              "'%s', **pickle.load(open('%s')))" % (
          self.test.autotest_name, args_file))

        print >> f, (
          "pickle.dump((success, "
          "str(job.last_error) if job.last_error else None), "
          "open('%s', 'w'), protocol=2)"
          % result_file)

      args = [os.path.join(os.path.dirname(factory.FACTORY_PATH),
                 'autotest/bin/autotest'),
          '--output_dir', output_dir,
          control_file]

      logging.debug('Test command line: %s', ' '.join(
          [pipes.quote(arg) for arg in args]))

      with self._lock:
        with self.goofy.env.lock:
          self._process = self.goofy.env.spawn_autotest(
            self.test.autotest_name, args, self.env_additions,
            result_file)

      returncode = self._process.wait()
      with self._lock:
        if self._aborted:
          error_msg = 'Aborted by operator'
          return

      if returncode:
        # Only happens when there is an autotest-level problem (not when
        # the test actually failed).
        error_msg = 'autotest returned with code %d' % returncode
        return

      with open(result_file) as f:
        try:
          success, error_msg = pickle.load(f)
        except:  # pylint: disable=W0702
          logging.exception('Unable to retrieve autotest results')
          error_msg = 'Unable to retrieve autotest results'
          return

      if success:
        status = TestState.PASSED
        error_msg = ''
    except Exception:  # pylint: disable=W0703
      logging.exception('Exception in autotest driver')
      # Make sure Goofy reports the exception upon destruction
      # (e.g., for testing)
      self.goofy.record_exception(traceback.format_exception_only(
          *sys.exc_info()[:2]))
    finally:
      self.clean_autotest_logs(output_dir)
      return status, error_msg  # pylint: disable=W0150

  def _invoke_pytest(self):
    '''
    Invokes a pyunittest-based test.
    '''
    assert self.test.pytest_name

    files_to_delete = []
    try:
      def make_tmp(type):
        ret = tempfile.mktemp(
          prefix='%s-%s-' % (self.test.path, type))
        files_to_delete.append(ret)
        return ret

      info_path = make_tmp('info')
      results_path = make_tmp('results')

      log_dir = os.path.join(factory.get_log_root(),
                   'factory_test_logs')
      if not os.path.exists(log_dir):
        os.makedirs(log_dir)
      log_path = os.path.join(log_dir,
                  '%s.%03d' % (self.test.path,
                         self.count))

      with open(info_path, 'w') as info:
        pickle.dump(PyTestInfo(
            test_list=self.goofy.options.test_list,
            path=self.test.path,
            pytest_name=self.test.pytest_name,
            args=self.test.dargs,
            results_path = results_path),
              info)

      # Invoke the unittest driver in a separate process.
      with open(log_path, "w") as log:
        this_file = os.path.realpath(__file__)
        this_file = re.sub(r'\.pyc$', '.py', this_file)
        args = [this_file, '--pytest', info_path]
        logging.debug('Test command line: %s >& %s',
               ' '.join([pipes.quote(arg) for arg in args]),
               log_path)

        env = dict(os.environ)
        env.update(self.env_additions)
        with self._lock:
          if self._aborted:
            return TestState.FAILED, 'Aborted before starting'
          self._process = subprocess.Popen(
            args,
            env=env,
            stdin=open(os.devnull, "w"),
            stdout=log,
            stderr=subprocess.STDOUT)
        self._process.wait()
        with self._lock:
          if self._aborted:
            return TestState.FAILED, 'Aborted by operator'
        if self._process.returncode:
          return TestState.FAILED, (
            'Test returned code %d' % pytest.returncode)

      if not os.path.exists(results_path):
        return TestState.FAILED, 'pytest did not complete'

      with open(results_path) as f:
        return pickle.load(f)
    except:  # pylint: disable=W0702
      logging.exception('Unable to retrieve pytest results')
      return TestState.FAILED, 'Unable to retrieve pytest results'
    finally:
      for f in files_to_delete:
        try:
          if os.path.exists(f):
            os.unlink(f)
        except:
          logging.exception('Unable to delete temporary file %s',
                    f)

  def _invoke_target(self):
    '''
    Invokes a target directly within Goofy.
    '''
    try:
      self.test.invocation_target(self)
      return TestState.PASSED, ''
    except:
      logging.exception('Exception while invoking target')
      error_msg = traceback.format_exc()
      return TestState.FAILED, traceback.format_exc()

  def clean_autotest_logs(self, output_dir):
    globs = self.goofy.test_list.options.preserve_autotest_results
    if '*' in globs:
      # Keep everything
      return

    deleted_count = 0
    preserved_count = 0
    for root, dirs, files in os.walk(output_dir, topdown=False):
      for f in files:
        if any(fnmatch.fnmatch(f, g)
             for g in globs):
          # Keep it
          preserved_count = 1
        else:
          try:
            os.unlink(os.path.join(root, f))
            deleted_count += 1
          except:
            logging.exception('Unable to remove %s' %
                      os.path.join(root, f))
      try:
        # Try to remove the directory (in case it's empty now)
        os.rmdir(root)
      except:
        # Not empty; that's OK
        pass
    logging.info('Preserved %d files matching %s and removed %d',
           preserved_count, globs, deleted_count)

  def _run(self):
    with self._lock:
      if self._aborted:
        return

    self.count = self.test.update_state(
      status=TestState.ACTIVE, increment_count=1, error_msg='',
      invocation=self.uuid).count

    factory.console.info('Running test %s' % self.test.path)

    log_args = dict(
      path=self.test.path,
      # Use Python representation for dargs, since some elements
      # may not be representable in YAML.
      dargs=repr(self.test.dargs),
      invocation=self.uuid)
    if self.test.autotest_name:
      log_args['autotest_name'] = self.test.autotest_name
    if self.test.pytest_name:
      log_args['pytest_name'] = self.test.pytest_name

    self.goofy.event_log.Log('start_test', **log_args)
    start_time = time.time()
    try:
      if self.test.autotest_name:
        status, error_msg = self._invoke_autotest()
      elif self.test.pytest_name:
        status, error_msg = self._invoke_pytest()
      elif self.test.invocation_target:
        status, error_msg = self._invoke_target()
      else:
        status = TestState.FAILED
        error_msg = (
          'No autotest_name, pytest_name, or invocation_target')
    finally:
      try:
        self.goofy.event_client.post_event(
          Event(Event.Type.DESTROY_TEST,
              test=self.test.path,
              invocation=self.uuid))
      except:
        logging.exception('Unable to post END_TEST event')

      try:
        # Leave all items in log_args; this duplicates
        # things but will make it easier to grok the output.
        log_args.update(dict(status=status,
                   duration=time.time() - start_time))
        if error_msg:
          log_args['error_msg'] = error_msg
        if (status != TestState.PASSED and
          self.debug_log_path and
          os.path.exists(self.debug_log_path)):
          try:
            debug_log_size = os.path.getsize(self.debug_log_path)
            offset = max(0, debug_log_size - ERROR_LOG_TAIL_LENGTH)
            with open(self.debug_log_path) as f:
              f.seek(offset)
              log_args['log_tail'] = f.read()
          except:
            logging.exception('Unable to read log tail')
        self.goofy.event_log.Log('end_test', **log_args)
      except:
        logging.exception('Unable to log end_test event')

    factory.console.info('Test %s %s%s',
               self.test.path,
               status,
               ': %s' % error_msg if error_msg else '')

    self.test.update_state(status=status, error_msg=error_msg,
                 visible=False)
    with self._lock:
      self._completed = True

    self.goofy.run_queue.put(self.goofy.reap_completed_tests)
    if self.on_completion:
      self.goofy.run_queue.put(self.on_completion)


def run_pytest(test_info):
  '''Runs a pytest, saving a pickled (status, error_msg) tuple to the
  appropriate results file.

  Args:
    test_info: A PyTestInfo object containing information about what to
      run.
  '''
  try:
    __import__('cros.factory.test.pytests.%s' % test_info.pytest_name)
    module = getattr(pytests, test_info.pytest_name)
    suite = unittest.TestLoader().loadTestsFromModule(module)

    # Recursively set
    def set_test_info(test):
      if isinstance(test, unittest.TestCase):
        test.test_info = test_info
      elif isinstance(test, unittest.TestSuite):
        for x in test:
          set_test_info(x)
    set_test_info(suite)

    runner = unittest.TextTestRunner()
    result = runner.run(suite)

    def format_error_msg(test_name, trace):
      '''Formats a trace so that the actual error message is in the last
      line.
      '''
      # The actual error is in the last line.
      trace, _, error_msg = trace.strip().rpartition('\n')
      error_msg = error_msg.replace('FactoryTestFailure: ', '')
      return error_msg + '\n' + trace

    all_failures = result.failures + result.errors
    if all_failures:
      status = TestState.FAILED
      error_msg = '; '.join(format_error_msg(test_name, trace)
                  for test_name, trace in all_failures)
      logging.info('pytest failure: %s', error_msg)
    else:
      status = TestState.PASSED
      error_msg = ''
  except:
    logging.exception('Unable to run pytest')
    status = TestState.FAILED
    error_msg = traceback.format_exc()

  with open(test_info.results_path, 'w') as results:
    pickle.dump((status, error_msg), results)

def main():
  parser = OptionParser()
  parser.add_option('--pytest', dest='pytest_info',
            help='Info for pytest to run')
  (options, args) = parser.parse_args()

  assert options.pytest_info

  info = pickle.load(open(options.pytest_info))
  factory.init_logging(info.path)
  run_pytest(info)

if __name__ == '__main__':
  main()
