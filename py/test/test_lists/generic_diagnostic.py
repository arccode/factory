# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""The creation of generic diagnostic test list.

This file implements Diagnostic method to create generic
diagnostic test list.
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.test.i18n import _
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import TestGroup


def Diagnostic(args):
  """Creates Diagnostic test list.

  Args:
    args: A TestListArgs object.
  """
  del args  # Unused.
  group_id = 'Diagnostic'
  with TestGroup(id=group_id, run_if=lambda env: env.InEngineeringMode()):
    OperatorTest(
        id='AudioDiagnostic',
        label=_('Audio Diagnostic'),
        pytest_name='audio_diagnostic',
    )
