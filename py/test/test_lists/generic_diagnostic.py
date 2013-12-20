# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0613,W0622


"""The creation of generic diagnostic test list.

This file implements Diagnostic method to create generic
diagnostic test list.
"""


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import TestGroup

def Diagnostic(args):
  """Creates Diagnostic test list.

  Args:
    args: A TestListArgs object.
  """
  group_id = 'Diagnostic'
  with TestGroup(id=group_id):
    OperatorTest(
        id='AudioDiagnostic',
        label_zh=u'音效诊断',
        pytest_name='audio_diagnostic',
        run_if=lambda env:env.InEngineeringMode(),
        )
