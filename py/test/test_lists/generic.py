# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Placeholder for a new-style generic test list, once we have one."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import TestList


def CreateTestLists():
  with TestList('placeholder', 'Placeholder new-style test list'):
    pass

