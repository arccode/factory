# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe.lib import combination_function


class Sequence(combination_function.CombinationFunction):
  """Sequential execute the functions.

  Description
  -----------
  The input of the next function is the output of the previous function.
  The concept is::

    data = Func1(data)
    data = Func2(data)
    ...

  This function is very useful when you want to union the outputs of a series
  of :ref:`probe functions <ProbeFunction>`.

  Examples
  --------
  Assume that we want to design a probe statement to probe general
  information from the device.  The expected probed data should contain two
  fields:

  - ``device_sku`` comes from the command ``cros_config /identity sku-id``
  - ``device_version`` from the command ``mosys platform version``.

  Instead of implementing a new probe function, we can reuse the existing
  :doc:`shell function <shell>`, which executes a single command, and writes
  a probe statement like::

    {
      "eval": {
        "sequence": {
          "functions": [
            {
              "shell": {
                "command": "cros_config /identity sku-id",
                "key": "device_sku"
              }
            },
            {
              "shell": {
                "command": "mosys platform version",
                "key": "device_version"
              }
            }
          ]
        }
      }
    }

  The expected probed results is::

    [
      {
        "device_sku": <output_of_the_cros_config_command>,
        "device_version": <output_of_the_mosys_command>
      }
    ]

  As this function is very common to use, the probe framework also supplies
  a syntax sugar for it.  Above probe statement can be simplified to::

    {
      "eval": [  # A list of functions means to apply the `sequence`
                 # function.
        {
          "shell": {
            "command": "cros_config /identity sku-id",
            "key": "device_sku"
          }
        },
        {
          "shell": {
            "command": "mosys platform version",
            "key": "device_version"
          }
        }
      ]
    }
  """

  def Combine(self, functions, data):
    for func in functions:
      data = func(data)
    return data
