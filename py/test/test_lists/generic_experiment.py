# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0613,W0622

"""Place holder for experiment test list.

Users can add tests for their need.
The tests here are only examples to create a experiment test list.
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.test import i18n
from cros.factory.test.i18n import _
from cros.factory.test.test_lists.test_lists import RebootStep
from cros.factory.test.test_lists.test_lists import TestGroup


def Experiment(args):
  """Creates Experiment test list.

  Args:
    args: A TestListArgs object.
  """
  with TestGroup(id='Reboot', label=_('Reboot')):
    RebootStep(
        id='Reboot',
        label=i18n.StringFormat(_('Reboot ({count} times)'),
                                count=args.experiment_reboot_iterations),
        iterations=args.experiment_reboot_iterations,
        dargs={'check_tag_file': True})
