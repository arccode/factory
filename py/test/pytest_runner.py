#!/usr/bin/env python
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function

import cPickle as pickle
import inspect
import logging
import os
import signal
import sys
import traceback
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test.state import TestState
from cros.factory.test.utils import pytest_utils
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Args
from cros.factory.utils import log_utils
from cros.factory.utils import type_utils

# pylint: disable=no-name-in-module
from cros.factory.external.setproctitle import setproctitle


def RunTestCase(test_case):
  """Runs the given test case.

  This is the actual test case runner.  It runs the test case and returns the
  test results.

  Args:
    test_case: The test case to run.

  Returns:
    The test result of the test case.
  """
  logging.debug('[%s] Really run test case: %s', os.getpid(), test_case.id())
  result = unittest.TestResult()
  test_case.run(result)
  return result


def RunPytest(test_info):
  """Runs a pytest, saving a pickled (status, error_msg) tuple to the
  appropriate results file.

  Args:
    test_info: A PytestInfo object containing information about what to run.
  """
  try:
    os.setpgrp()
    # Register a handler for SIGTERM, so that Python interpreter has
    # a chance to do clean up procedures when SIGTERM is received.
    def _SIGTERMHandler(signum, frame):  # pylint: disable=unused-argument
      logging.error('SIGTERM received')
      raise type_utils.TestFailure('SIGTERM received')

    signal.signal(signal.SIGTERM, _SIGTERMHandler)

    test = pytest_utils.LoadPytest(test_info.pytest_name)
    os.environ.update({
        session.ENV_TEST_FILE_PATH:
            os.path.realpath(inspect.getfile(test.__class__))
    })

    logging.debug('[%s] Start test case: %s', os.getpid(), test.id())

    test.test_info = test_info
    if test_info.dut_options:
      os.environ.update({
          device_utils.ENV_DUT_OPTIONS: str(test_info.dut_options)})
    arg_spec = getattr(test, 'ARGS', None)
    if arg_spec:
      test.args = Args(*arg_spec).Parse(test_info.args)

    result = RunTestCase(test)

    def FormatErrorMessage(trace):
      """Formats a trace so that the actual error message is in the last line.
      """
      # The actual error is in the last line.
      trace, unused_sep, error_msg = trace.strip().rpartition('\n')
      error_msg = error_msg.replace('TestFailure: ', '')
      return error_msg + '\n' + trace

    all_failures = result.failures + result.errors
    if all_failures:
      status = TestState.FAILED
      error_msg = '\n'.join(FormatErrorMessage(trace)
                            for test_name, trace in all_failures)
      logging.info('pytest failure: %s', error_msg)
    else:
      status = TestState.PASSED
      error_msg = ''
  except Exception:
    logging.exception('Unable to run pytest')
    status = TestState.FAILED
    error_msg = traceback.format_exc()

  with open(test_info.results_path, 'w') as results:
    pickle.dump((status, error_msg), results)


def main():
  env, info = pickle.load(sys.stdin)
  if not env:
    sys.exit(0)
  os.environ.update(env)

  log_utils.InitLogging(info.path)
  if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
    testlog.Testlog(
        stationDeviceId=session.GetDeviceID(),
        stationInstallationId=session.GetInstallationID())
  else:
    # If the testlog.TESTLOG_ENV_VARIABLE_NAME environment variable doesn't
    # exist, assume invocation is being called by run_test.py.  In this case,
    # this is expected behaviour, since run_test.py doesn't save logs.
    logging.info('Logging for Testlog is not able to start')

  proc_title = os.environ.get('CROS_PROC_TITLE')
  if proc_title:
    setproctitle(proc_title)
  RunPytest(info)


if __name__ == '__main__':
  main()
