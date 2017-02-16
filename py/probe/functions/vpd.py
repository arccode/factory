# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import shell
from cros.factory.utils.arg_utils import Arg


class VPDFunction(shell.ShellFunction):
  """Reads the information from VPD."""

  ARGS = [
      Arg('field', str, 'The field of VPD.'),
      Arg('key', str, 'The key of the result.', default=None),
      Arg('from_rw', bool,
          'True to read from RW_VPD, and False to read from RO_VPD. '
          'Default is to read from RO_VPD.', default=False),
  ]

  def __init__(self, **kwargs):
    super(VPDFunction, self).__init__(**kwargs)

    partition = 'RW_VPD' if self.args.from_rw else 'RO_VPD'
    self.args.command = 'vpd -i %s -g %s' % (partition, self.args.field)
    self.args.split_line = False
    if self.args.key is None:
      self.args.key = self.args.field
