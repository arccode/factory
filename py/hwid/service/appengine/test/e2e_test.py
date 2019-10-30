#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for e2e test.

Before deploying HWID Service to prod environment, one should run this test
on the staging environment. The test loads a test config files in the
factory-private repository, and executes the speicified tests.
"""

import json
import logging
import os
import unittest

import requests

# pylint: disable=import-error
import factory_common  # pylint: disable=unused-import
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


TEST_DIR = os.path.dirname(os.path.abspath(__file__))
APPENGINE_DIR = os.path.dirname(TEST_DIR)
FACTORY_DIR = os.path.abspath(
    os.path.join(APPENGINE_DIR, '../../../..'))
FACTORY_PRIVATE_DIR = os.path.abspath(
    os.path.join(FACTORY_DIR, '../factory-private'))
DEFAULT_CONFIG_PATH = os.path.join(
    FACTORY_PRIVATE_DIR, 'config/hwid/service/appengine/test/e2e_test')


class E2ETest(unittest.TestCase):
  """e2e tests on staging environment."""
  def setUp(self):
    self.config = config_utils.LoadConfig(DEFAULT_CONFIG_PATH, 'e2e_test')
    self.default_http_method = self.config['default_http_method']
    self.apikey = self.config['apikey']

  def _GenerateURL(self, path):
    return '%s/%s' % (self.config['url_prefix'], path)

  def _GenerateParams(self, params=None):
    """Genearate params for requeust."""
    params = params or {}
    params['key'] = self.apikey
    return params

  def testAll(self):
    failed_tests = []
    for test in self.config['tests']:
      url = self._GenerateURL(test['path'])
      params = self._GenerateParams(test.get('params', None))

      http_method = test.get('http_method', self.default_http_method)
      if http_method == 'GET':
        response = requests.get(url, params=params)
      elif http_method == 'POST':
        data = test.get('data', None)
        headers = test.get('headers', None)
        response = requests.post(url, data=data, headers=headers, params=params)
      else:
        raise ValueError('Does not support http_method %s.' % http_method)

      try:
        r = type_utils.UnicodeToString(response.json())
        # Pops non-related keys.
        for k in ['kind', 'etag']:
          r.pop(k, None)
        expecting_output = test['expecting_output']
        if expecting_output != r:
          with open(file_utils.CreateTemporaryFile(), 'w') as f:
            # Dumps failure logs in json format.
            f.write(json.dumps({'expect': expecting_output, 'got': r}))
            failed_tests.append((test['name'], f.name))
      except Exception as e:
        logging.exception('Unknown failure at %s: %s', test['name'], str(e))
        failed_tests.append(test['name'])

    logging.info('[%d/%d] Passed',
                 len(self.config['tests']) - len(failed_tests),
                 len(self.config['tests']))

    for t in failed_tests:
      logging.error('FAILED: %r', t)

    assert not failed_tests


if __name__ == '__main__':
  logging.getLogger().setLevel(int(os.environ.get('LOG_LEVEL') or logging.INFO))
  unittest.main()
