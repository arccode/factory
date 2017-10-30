# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import shell
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils


class VPDFunction(shell.ShellFunction):
  """Reads the information from VPD.

  This function supplies 3 modes:
    1. If the user doesn't specify any field name of VPD data to probe
       (both the arguments `field` and `field` are `None`), the probe result
       will be a dict contains all fields in the VPD data.
    2. If the user specifies a list of fields (ex: `fields=['a', 'b', ...]`),
       the probe result will contain only specified fields.  The user also can
       specify the argument `key='another_key_name'` to customize the key name
       in the result dict if the specified fields contains only element.
  """

  ARGS = [
      Arg('fields', list, 'A list of fields of VPD data to probe.',
          default=None),
      Arg('key', str,
          'The key of the result.  Can be specified only if the `fields` '
          'argument contains exact one element', default=None),
      Arg('partition', str,
          'The partition name to read, can be either "ro" or "rw"',
          default='ro')
  ]

  def __init__(self, **kwargs):
    super(VPDFunction, self).__init__(**kwargs)

    if self.args.key and len(self.args.fields) != 1:
      raise ValueError('Key remap is only available in single field mode.')

    if self.args.partition.lower() not in ['ro', 'rw']:
      raise ValueError('Invalid partition name: %r' % self.args.partition)

  def Probe(self):
    vpd_tool = sys_utils.VPDTool()
    vpd_data = vpd_tool.GetAllData(
        partition=getattr(vpd_tool, self.args.partition.upper() + '_PARTITION'))

    if not self.args.fields:
      return [vpd_data]

    # success only if all fields are found in the vpd data
    if set(self.args.fields) - set(vpd_data.keys()):
      return []

    if self.args.key:
      return [{self.args.key: vpd_data[self.args.fields[0]]}]

    return [{field: vpd_data[field] for field in self.args.fields}]
