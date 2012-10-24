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
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import unittest
import yaml
from optparse import OptionParser
from setproctitle import setproctitle

import factory_common  # pylint: disable=W0611
from cros.factory import event_log
from cros.factory.goofy.service_manager import ServiceManager
from cros.factory.test import factory
from cros.factory.test import pytests
from cros.factory.test import shopfloor
from cros.factory.test import test_ui
from cros.factory.test import utils
from cros.factory.test.args import Args
from cros.factory.test.event import Event
from cros.factory.test.factory import TestState
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.string_utils import DecodeUTF8


# Number of bytes to include from the log of a failed test.
ERROR_LOG_TAIL_LENGTH = 8*1024

# pylint: disable=W0702


def ResolveTestArgs(dargs):
  '''Resolves an argument dictionary by evaluating any functions.

  For instance, in a test list:

    OperatorTest(
      ...
      dargs={
          'method': 'Foo',
          'args': lambda env: [
              env.state.get_shared_data('mlb_serial_number'),
              env.shopfloor.get_serial_number(),
              env.GetMACAddress('wlan0'),
          ]
      })

  This will be resolved to something like this before the test is run:

    OperatorTest(
      ...
      dargs={
          'method': 'Foo',
          'args': ['MLB12345', 'X67890', '00:11:22:33:44:55']
      })

  Args:
    dargs: An test argument dictionary from the test list.

  Returns:
    dargs, except that any values that are lambdas are replaced with the
      results of evaluating them with a single argument, 'env',
      which is an instance of the Env class.
  '''
  class Env(object):
    '''Environment for resolving test arguments.'''
    def __init__(self):
      self.state = factory.get_state_instance()
      self.shopfloor = shopfloor

    def GetMACAddress(self, interface):
      return open('/sys/class/net/%s/address' % interface).read().strip()

  def ResolveArg(k, v):
    '''Resolves a single argument.'''
    if not isinstance(v, types.FunctionType):
      return v

    v = v(Env())
    logging.info('Resolved argument %s to %r', k, v)
    return v

  return dict((k, ResolveArg(k, v)) for k, v in dargs.iteritems())


class PyTestInfo(object):
  def __init__(self, test_list, path, pytest_name, args, results_path):
    self.test_list = test_list
    self.path = path
    self.pytest_name = pytest_name
    self.args = args
    self.results_path = results_path

  def ReadTestList(self):
    '''Reads and returns the test list.'''
    return factory.read_test_list(self.test_list)


class TestInvocation(object):
  '''
  State for an active test.

  Properties:
    update_state_on_completion: State for Goofy to update on
      completion; Goofy will call test.update_state(
      **update_state_on_completion).  So update_state_on_completion
      will have at least status and error_msg properties to update
      the test state.
  '''
  def __init__(self, goofy, test, on_completion=None):
    '''Constructor.

    Args:
      goofy: The controlling Goofy object.
      test: The FactoryTest object to test.
      on_completion: Callback to invoke in the goofy event queue
        on completion.
    '''
    self.goofy = goofy
    self.test = test
    self.thread = threading.Thread(target=self._run,
                     name='TestInvocation-%s' % test.path)
    self.on_completion = on_completion
    self.uuid = event_log.TimedUuid()
    self.output_dir = os.path.join(factory.get_test_data_root(),
                                   '%s-%s' % (self.test.path,
                                              self.uuid))
    utils.TryMakeDirs(self.output_dir)

    # Create a symlink for the latest test run, so if we're looking at the
    # logs we don't need to enter the whole UUID.
    latest_symlink = os.path.join(factory.get_test_data_root(),
                                  self.test.path)
    try:
      os.remove(latest_symlink)
    except OSError:
      pass
    try:
      os.symlink(os.path.basename(self.output_dir), latest_symlink)
    except OSError:
      logging.exception('Unable to create symlink %s', latest_symlink)

    self.metadata_file = os.path.join(self.output_dir, 'metadata')
    self.env_additions = {'CROS_FACTORY_TEST_PATH': self.test.path,
                          'CROS_FACTORY_TEST_INVOCATION': self.uuid,
                          'CROS_FACTORY_TEST_METADATA': self.metadata_file}
    self.metadata = {}
    self.update_metadata(path=test.path,
                         init_time=time.time(),
                         invocation=str(self.uuid),
                         label_en=test.label_en,
                         label_zh=test.label_zh)
    self.count = None
    self.log_path = os.path.join(self.output_dir, 'log')
    self.update_state_on_completion = {}

    self._lock = threading.Lock()
    # The following properties are guarded by the lock.
    self._aborted = False
    self._completed = False
    self._process = None

  def __repr__(self):
    return 'TestInvocation(_aborted=%s, _completed=%s)' % (
      self._aborted, self._completed)

  def update_metadata(self, **kwargs):
    self.metadata.update(kwargs)
    tmp = self.metadata_file + '.tmp'
    with open(tmp, 'w') as f:
      yaml.dump(self.metadata, f, default_flow_style=False)
    os.rename(tmp, self.metadata_file)

  def start(self):
    '''Starts the test thread.'''
    self.thread.start()

  def abort_and_join(self):
    '''
    Aborts a test (must be called from the event controller thread).
    '''
    with self._lock:
      self._aborted = True
      process = self._process
    if process:
      utils.kill_process_tree(process, 'autotest')
    if self.thread:
      self.thread.join()
    with self._lock:
      # Should be set by the thread itself, but just in case...
      self._completed = True

  def is_completed(self):
    '''
    Returns true if the test has finished.
    '''
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
      # Symlink client.INFO to the log path.
      os.symlink('results/default/debug/client.INFO',
                 self.log_path)
      tmp_dir = tempfile.mkdtemp(prefix='tmp', dir=self.output_dir)

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
          '--output_dir', self.output_dir,
          control_file]

      logging.debug('Test command line: %s', ' '.join(
          [pipes.quote(arg) for arg in args]))

      self.env_additions['CROS_PROC_TITLE'] = (
          '%s.py (factory autotest %s)' % (
              self.test.autotest_name, self.output_dir))

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
        except:
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
      self.clean_autotest_logs()
      return status, error_msg  # pylint: disable=W0150

  def _invoke_pytest(self):
    '''
    Invokes a pyunittest-based test.
    '''
    assert self.test.pytest_name

    files_to_delete = []
    try:
      def make_tmp(prefix):
        ret = tempfile.mktemp(
          prefix='%s-%s-' % (self.test.path, prefix))
        files_to_delete.append(ret)
        return ret

      info_path = make_tmp('info')
      results_path = make_tmp('results')

      log_dir = os.path.join(factory.get_test_data_root())
      if not os.path.exists(log_dir):
        os.makedirs(log_dir)

      try:
        args = ResolveTestArgs(self.test.dargs)
      except Exception, e:
        logging.exception('Unable to resolve test arguments')
        return TestState.FAILED, 'Unable to resolve test arguments: %s' % e

      with open(info_path, 'w') as info:
        pickle.dump(PyTestInfo(
            test_list=self.goofy.options.test_list,
            path=self.test.path,
            pytest_name=self.test.pytest_name,
            args=args,
            results_path=results_path),
              info)

      # Invoke the unittest driver in a separate process.
      with open(self.log_path, 'wb', 0) as log:
        this_file = os.path.realpath(__file__)
        this_file = re.sub(r'\.pyc$', '.py', this_file)
        args = [this_file, '--pytest', info_path]

        cmd_line = ' '.join([pipes.quote(arg) for arg in args])
        print >> log, 'Running test: %s' % cmd_line

        logging.debug('Test command line: %s >& %s',
                      cmd_line, self.log_path)

        self.env_additions['CROS_PROC_TITLE'] = (
            '%s.py (factory pytest %s)' % (
                self.test.pytest_name, self.output_dir))

        env = dict(os.environ)
        env.update(self.env_additions)
        with self._lock:
          if self._aborted:
            return TestState.FAILED, 'Aborted before starting'

          self._process = Spawn(
            args,
            env=env,
            stdin=open(os.devnull, "w"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)

        # Tee process's stderr to both the log and our stderr; this
        # will end when the process dies.
        while True:
          line = self._process.stdout.readline()
          if not line:
            break
          log.write(line)
          sys.stderr.write('%s> %s' % (self.test.path, line))

        self._process.wait()
        with self._lock:
          if self._aborted:
            return TestState.FAILED, 'Aborted by operator'
        if self._process.returncode:
          return TestState.FAILED, (
            'Test returned code %d' % self._process.returncode)

      if not os.path.exists(results_path):
        return TestState.FAILED, 'pytest did not complete'

      with open(results_path) as f:
        return pickle.load(f)
    except:
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

      if sys.exc_info()[0] == factory.FactoryTestFailure:
        # Use the status from the exception.
        status = sys.exc_info()[1].status
      else:
        status = TestState.FAILED

      return status, traceback.format_exc()

  def clean_autotest_logs(self):
    globs = self.goofy.test_list.options.preserve_autotest_results
    if '*' in globs:
      # Keep everything
      return

    deleted_count = 0
    preserved_count = 0
    for root, dummy_dirs, files in os.walk(self.output_dir, topdown=False):
      for f in files:
        if f in ['log', 'metadata'] or any(fnmatch.fnmatch(f, g)
                                           for g in globs):
          # Keep it
          preserved_count = 1
        else:
          try:
            os.unlink(os.path.join(root, f))
            deleted_count += 1
          except:
            logging.exception('Unable to remove %s',
                              os.path.join(root, f))
      try:
        # Try to remove the directory (in case it's empty now)
        os.rmdir(root)
      except OSError:
        # Not empty; that's OK
        pass
    logging.info('Preserved %d files matching %s and removed %d',
           preserved_count, globs, deleted_count)

  def _run(self):
    with self._lock:
      if self._aborted:
        return

    if self.test.iterations > 1:
      iteration_string = ' [%s/%s]' % (
        self.test.iterations -
        self.test.get_state().iterations_left + 1,
        self.test.iterations)
    else:
      iteration_string = ''
    factory.console.info('Running test %s%s',
                         self.test.path, iteration_string)

    service_manager = ServiceManager()
    service_manager.SetupServices(enable_services=self.test.enable_services,
                                  disable_services=self.test.disable_services)

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

    self.update_metadata(start_time=time.time(), **log_args)
    start_time = time.time()
    try:
      status, error_msg = None, None
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
      if error_msg:
        error_msg = DecodeUTF8(error_msg)

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
        end_time = time.time()
        log_args.update(dict(status=status,
                             duration=(end_time - start_time)))
        if error_msg:
          log_args['error_msg'] = error_msg
        if (status != TestState.PASSED and
            self.log_path and
            os.path.exists(self.log_path)):
          try:
            log_size = os.path.getsize(self.log_path)
            offset = max(0, log_size - ERROR_LOG_TAIL_LENGTH)
            with open(self.log_path) as f:
              f.seek(offset)
              log_args['log_tail'] = DecodeUTF8(f.read())
          except:
            logging.exception('Unable to read log tail')
        self.goofy.event_log.Log('end_test', **log_args)
        self.update_metadata(end_time=end_time, **log_args)
      except:
        logging.exception('Unable to log end_test event')

    service_manager.RestoreServices()

    factory.console.info(u'Test %s%s %s%s',
                         self.test.path,
                         iteration_string,
                         status,
                         u': %s' % error_msg if error_msg else '')

    with self._lock:
      self.update_state_on_completion = dict(
        status=status, error_msg=error_msg,
        visible=False, decrement_iterations_left=1)
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
        arg_spec = getattr(test, 'ARGS', None)
        if arg_spec:
          setattr(test, 'args', Args(*arg_spec).Parse(test_info.args))
      elif isinstance(test, unittest.TestSuite):
        for x in test:
          set_test_info(x)
    set_test_info(suite)

    runner = unittest.TextTestRunner()
    result = runner.run(suite)

    def format_error_msg(trace):
      '''Formats a trace so that the actual error message is in the last
      line.
      '''
      # The actual error is in the last line.
      trace, _, error_msg = trace.strip().rpartition('\n')
      error_msg = error_msg.replace('FactoryTestFailure: ', '')
      return error_msg + '\n' + trace

    all_failures = result.failures + result.errors + test_ui.exception_list
    if all_failures:
      status = TestState.FAILED
      error_msg = '; '.join(format_error_msg(trace)
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
  (options, dummy_args) = parser.parse_args()

  assert options.pytest_info

  test_ui.exception_list = []

  info = pickle.load(open(options.pytest_info))
  factory.init_logging(info.path)
  proc_title = os.environ.get('CROS_PROC_TITLE')
  if proc_title:
    setproctitle(proc_title)
  run_pytest(info)

if __name__ == '__main__':
  main()
