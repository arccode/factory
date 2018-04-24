# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.functions import shell
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import sys_utils
from cros.factory.utils import type_utils


class VPDFunction(shell.ShellFunction):
  """Reads the information from VPD.

  Description
  -----------
  This function probes the VPD data in the firmware by calling the command
  ``vpd``.

  This function supplies 3 modes:
    1. If the user doesn't specify any field name of VPD data to probe
       (i.e. both the arguments ``field`` and ``key`` are `None`), the probed
       result will be a dict contains all fields in the VPD data.
    2. If the user specifies a list of fields (ex: ``fields=['a', 'b', ...]``),
       the probed result will contain only specified fields.  The user also can
       specify the argument ``key='another_key_name'`` to customize the key name
       in the result dict if the specified fields contains only element.

  Examples
  --------
  Let's assume that the read-only VPD partition contains these fields::

    serial=12345
    region=us

  And read-write VPD partition contains::

    k1=v1
    k2=v2
    k3=v3

  And we have the probe config file::

    {
      "all_ro_vpd_data": {  # Simplest example, just dump all fields in RO VPD.
        "from_firmware": {
          "eval": "vpd"
        }
      },

      "region": {
        "from_firmware": {
          "eval": {
            "vpd": {
              "fields": [
                "region"
              ],
              "key": "region_code"  # In this case we rename the key from
                                    # "region" to "region_code".
            }
          }
        }
      },

      "k1k2_rw_vpd_data": {  # In this case we only output k1, k2 from the RW
                             # VPD.
        "from_firmware": {
          "eval": {
            "vpd": {
              "partition": "rw",
              "fields": [
                "k1",
                "k2"
              ]
            }
          }
        }
      }
    }

  Then the corresponding output will be::

    {
      "all_ro_vpd_data": [
        {
          "name": "from_firmware",
          "values": {
            "serial": "12345",
            "region": "us"
          }
        }
      ],

      "region": [
        {
          "name": "from_firmware",
          "values": {
            "region_code": "us"
          }
        }
      ],

      "k1k2_rw_vpd_data": [
        {
          "name": "from_firmware",
          "values": {
            "k1": "v1",
            "k2": "v2"
          }
        }
      ]
    }
  """

  ARGS = [
      Arg('fields', list, 'A list of fields of VPD data to probe.',
          default=None),
      Arg('key', str,
          'The key of the result.  Can be specified only if the `fields` '
          'argument contains exact one element', default=None),
      Arg('partition', type_utils.Enum(['ro', 'rw']),
          'The partition name to read, can be either "ro" or "rw"',
          default='ro')
  ]

  def __init__(self, **kwargs):
    super(VPDFunction, self).__init__(**kwargs)

    if self.args.key and len(self.args.fields) != 1:
      raise ValueError('Key remap is only available in single field mode.')

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
