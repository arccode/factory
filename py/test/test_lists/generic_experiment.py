# -*- mode: python; coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0613,W0622

"""Place holder for experiment test list.

Users can add tests for their need.
The tests here are only examples to create a experiment test list.
"""


import factory_common  # pylint: disable=W0611
from cros.factory.test.test_lists.test_lists import RebootStep
from cros.factory.test.test_lists.test_lists import TestGroup


def Experiment(args):
  """Creates Experiment test list.

  Args:
    args: A TestListArgs object.
  """
  with TestGroup(id='Reboot',
                 label_zh=u'重新开机'):
    RebootStep(
        id='Reboot',
        label_en='Reboot %r times' % args.experiment_reboot_iterations,
        label_zh=u'重新开机 (%r 次)' % args.experiment_reboot_iterations,
        iterations=args.experiment_reboot_iterations)
