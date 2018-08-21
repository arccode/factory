# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


def CreateFixture(class_name, params):
  """Initializes a fixture instance.

  Imports a fixture module based on class_name and initializes the
  instance using params.

  Args:
    class_name: fixture's import path under cros.factory.test.fixture +
        module name.  For example,

        "dummy_bft_fixture.DummyBFTFixture".

        Then cros.factory.test.fixture.dummy_bft_fixture.DummyBFTFixture will be
        used.
    params: a dict of params for the contructor.

  Returns:
    An instance of the specified fixture implementation.
  """
  module, cls = class_name.rsplit('.', 1)
  module = 'cros.factory.test.fixture.%s' % module
  fixture = getattr(__import__(module, fromlist=[cls]), cls)(**params)
  return fixture
