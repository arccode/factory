# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Base class for AppEngine integration tests.

The class makes sure that the testbed has been initialized and sets an
environment variable that is require to make cloudstorage work.
"""

import unittest

# pylint: disable=import-error, no-name-in-module
from google.appengine.ext import testbed


class AppEngineTestBase(unittest.TestCase):
  """ AppEngineTestBase class for testing in a local stubs out environment."""

  def setUp(self):
    super(AppEngineTestBase, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    # Stubs out appengine APIs
    self.testbed.init_app_identity_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_urlfetch_stub()
    self.testbed.init_blobstore_stub()
    self.testbed.init_datastore_v3_stub()

  def tearDown(self):
    super(AppEngineTestBase, self).tearDown()
    self.testbed.deactivate()
