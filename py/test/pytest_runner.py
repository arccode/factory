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

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.test import session
from cros.factory.test.state import TestState
from cros.factory.test.utils import pytest_utils
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

    result = pytest_utils.RunTestCase(test)

    if result.failure_details:
      logging.info('pytest failure:\n%s', result.DumpStr())
      status = TestState.FAILED
      failures = result.failure_details
    else:
      status = TestState.PASSED
      failures = []
  except Exception as e:
    logging.exception('Unable to run pytest')
    status = TestState.FAILED
    failures = [(e, traceback.extract_tb(sys.exc_info()[2]))]

  try:
    pickled_result = pickle.dumps((status, failures))
  except Exception:
    logging.warning('Some exception objects are not pickle-able.  Convert them '
                    'to generic exceptions first.')
    pickled_result = pickle.dumps(
        (status, [(type_utils.Error(str(e)), tb) for e, tb in failures]))

  file_utils.WriteFile(test_info.results_path, pickled_result)


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
  if testlog.TESTLOG_ENV_VARIABLE_NAME in os.environ:
    testlog.GetGlobalTestlog().Close()


if __name__ == '__main__':
  main()
