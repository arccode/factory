# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=unused-import
from cros.factory.probe import function
from cros.factory.utils import process_utils


class GenericTPMFunction(function.ProbeFunction):
  """Probe the generic TPM information.

  The function is ported from `py/gooftool/probe.py` module.
  """

  def Probe(self):
    tpm_data = [line.partition(':') for line in
                process_utils.CheckOutput('tpm_version').splitlines()]
    tpm_dict = dict((key.strip(), value.strip()) for
                    key, _, value in tpm_data)
    mfg = tpm_dict.get('Manufacturer Info', None)
    version = tpm_dict.get('Chip Version', None)
    if mfg is not None and version is not None:
      return {'manufacturer_info': mfg,
              'version': version}
    return None
