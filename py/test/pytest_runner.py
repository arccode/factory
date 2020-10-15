#!/usr/bin/env python3
#
# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import inspect
import logging
import os
import pickle
import signal
import sys

from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test.state import TestState
from cros.factory.test.utils import pytest_utils
from cros.factory.test.utils.pytest_utils import PytestExecutionResult
from cros.factory.testlog import testlog
from cros.factory.utils.arg_utils import Args
from cros.factory.utils import file_utils
from cros.factory.utils import log_utils
from cros.factory.utils import type_utils

# pylint: disable=no-name-in-module
from cros.factory.external.setproctitle import setproctitle


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

    test = pytest_utils.LoadPytest(test_info.pytest_name)()
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

    test_case_result = pytest_utils.RunTestCase(test)

    if test_case_result.failure_details:
      logging.info('pytest failure:\n%s', test_case_result.DumpStr())
      result = PytestExecutionResult.GenerateFromTestResultFailureDetails(
          TestState.FAILED, test_case_result.failure_details)
    else:
      result = PytestExecutionResult(TestState.PASSED)
  except Exception:
    logging.exception('Unable to run pytest')
    result = PytestExecutionResult.GenerateFromException(TestState.FAILED)

  file_utils.WriteFile(test_info.results_path, pickle.dumps(result),
                       encoding=None)


def main():
  # Load pickle object from the binary data directly to prevent potential
  # decoding errors.
  env, info = pickle.load(sys.stdin.buffer)
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
  if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
    testlog.GetGlobalTestlog().Close()


if __name__ == '__main__':
  main()
