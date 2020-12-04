#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for e2e test.

Before deploying HWID Service to prod environment, one should run this test
on the staging environment. The test loads a test config files in the
factory-private repository, and executes the speicified tests.
"""

import importlib
import json
import logging
import os
import unittest

from google.protobuf import json_format
from google.protobuf import text_format

from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


TEST_DIR = os.path.dirname(os.path.abspath(__file__))
APPENGINE_DIR = os.path.dirname(TEST_DIR)
PROTO_DIR = os.path.join(APPENGINE_DIR, 'proto')
FACTORY_DIR = os.path.abspath(
    os.path.join(APPENGINE_DIR, '../../../..'))
FACTORY_PRIVATE_DIR = os.path.abspath(
    os.path.join(FACTORY_DIR, '../factory-private'))
TEST_DIR = os.path.join(FACTORY_PRIVATE_DIR,
                        'config/hwid/service/appengine/test/')
DEFAULT_CONFIG_PATH = os.path.join(TEST_DIR, 'e2e_test')
PROTO_PKG = 'cros.factory.hwid.service.appengine.proto'


class E2ETest(unittest.TestCase):
  """e2e tests on staging environment."""
  def setUp(self):
    self.config = config_utils.LoadConfig(DEFAULT_CONFIG_PATH, 'e2e_test')
    self.test_cmd = self.config['test_cmd']
    self._SetupEnv(self.config['check_env_cmd'], self.config['setup_env_cmd'])

  def _SetupEnv(self, check_env_cmd, setup_env_cmd):
    check_ret = process_utils.Spawn(check_env_cmd, call=True).returncode
    if check_ret:
      logging.info("Setting up environment with command: %s", setup_env_cmd)
      setup_ret = process_utils.Spawn(setup_env_cmd, call=True).returncode
      if setup_ret:
        self.fail('Environment is not ready')

  def _GenerateCommand(self, test):
    return [
        os.path.join(TEST_DIR, self.test_cmd), test['proto_filename'],
        test['api']
    ]

  def testAll(self):
    logging.info('Test endpoint: %s', self.config['host_name'])
    for test in self.config['tests']:
      with self.subTest(name=test['name']):
        logging.info('Running test: %s', test['name'])
        try:
          pkg = importlib.import_module('.' + test['proto_filename'] + '_pb2',
                                        PROTO_PKG)
          response_class = getattr(pkg, test['response_class'])
          request_class = getattr(pkg, test['request_class'])
          expected_output = json.dumps(test['expected_output'])
          request = json_format.Parse(
              json.dumps(test['request']), request_class())
          cmd = self._GenerateCommand(test)
          p = process_utils.Spawn(cmd, stdin=process_utils.PIPE,
                                  stdout=process_utils.PIPE,
                                  stderr=process_utils.PIPE)
          stdin = text_format.MessageToString(request)
          stdout = p.communicate(stdin)[0]
          out_msg = text_format.Parse(stdout, response_class())
          expected_msg = json_format.Parse(expected_output, response_class())
        except Exception as ex:
          self.fail(str(ex))

        if out_msg != expected_msg:
          out_json = json_format.MessageToDict(out_msg)
          err_msg = json.dumps({
              'expect': test['expected_output'],
              'got': out_json
          })

          with open(file_utils.CreateTemporaryFile(), 'w') as f:
            f.write(err_msg)
          self.fail('%s failed, see report at %s' % (test['name'], f.name))


if __name__ == '__main__':
  logging.getLogger().setLevel(int(os.environ.get('LOG_LEVEL') or logging.INFO))
  unittest.main()
