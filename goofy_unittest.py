#!/usr/bin/python -u
#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common

import logging
import mox
import pickle
import subprocess
import tempfile
import unittest

from mox import IgnoreArg

from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import goofy
from autotest_lib.client.cros.factory import state
from autotest_lib.client.cros.factory import TestState
from autotest_lib.client.cros.factory.goofy import Environment
from autotest_lib.client.cros.factory.goofy import Goofy


def init_goofy(env=None, test_list=None, restart=True):
    '''Initializes and returns a Goofy.'''
    goofy = Goofy()
    # Make a copy (since we'll be modifying it.
    args = ['--noui']
    if restart:
        args.append('--restart')
    if test_list:
        out = tempfile.NamedTemporaryFile(prefix='test_list', delete=False)
        out.write('TEST_LIST = [' + test_list + ']')
        out.close()
        args.extend(['--test_list', out.name])
    logging.info('Running goofy with args %r', args)
    goofy.init(args, env or Environment())
    return goofy


def mock_autotest(env, name, passed, error_msg):
    '''Adds a side effect that a mock autotest will be executed.

    Args:
        name: The name of the autotest to be mocked.
        passed: Whether the test should pass.
        error_msg: The error message.
    '''
    def side_effect(name, args, env_additions, result_file):
        with open(result_file, 'w') as out:
            pickle.dump((passed, error_msg), out)
            return subprocess.Popen(['true'])

    env.spawn_autotest(
        name, IgnoreArg(), IgnoreArg(), IgnoreArg()).WithSideEffects(
        side_effect)


class GoofyTestCase(unittest.TestCase):
    '''Base class for Goofy test cases.'''
    def setUp(self):
        self.mocker = mox.Mox()
        self.env = self.mocker.CreateMock(Environment)
        self.goofy = init_goofy(self.env, self.TEST_LIST)
        self.state = state.get_instance()

    def tearDown(self):
        self.goofy.destroy()

    def _wait(self):
        '''Waits for any pending invocations in Goofy to complete,
        and verifies and resets all mocks.'''
        self.goofy.wait()
        self.mocker.VerifyAll()
        self.mocker.ResetAll()


class BasicTestCase(GoofyTestCase):
    '''A simple test case that checks that tests are run in the correct
    order.'''

    TEST_LIST = '''
        OperatorTest(id='a', autotest_name='a_A'),
        OperatorTest(id='b', autotest_name='b_B'),
        OperatorTest(id='c', autotest_name='c_C'),
    '''
    def test_basic_behavior(self):
        def run_one_test(id, name, passed, error_msg):
            mock_autotest(self.env, name, passed, error_msg)
            self.mocker.ReplayAll()
            self.assertTrue(self.goofy.run_once())
            self.assertEqual([id],
                             [test.path for test in self.goofy.invocations])
            self._wait()
            state = self.state.get_test_state(id)
            self.assertEqual(TestState.PASSED if passed else TestState.FAILED,
                             state['status'])
            self.assertEqual(1, state['count'])
            self.assertEqual(error_msg, state['error_msg'])

        run_one_test('a', 'a_A', True, '')
        run_one_test('b', 'b_B', False, 'Uh-oh')
        run_one_test('c', 'c_C', False, 'Uh-oh')


if __name__ == "__main__":
    factory.init_logging('goofy_unittest')
    goofy._inited_logging = True
    goofy.suppress_chroot_warning = True

    unittest.main()
