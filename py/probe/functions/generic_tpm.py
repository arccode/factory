# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import process_utils


class GenericTPMFunction(cached_probe_function.CachedProbeFunction):
  """Probe the generic TPM information."""

  def GetCategoryFromArgs(self):
    return None

  @classmethod
  def ProbeAllDevices(cls):
    tpm_data = [line.split(':') for line in
                process_utils.CheckOutput('tpm_version').splitlines()]
    tpm_dict = {key.strip(): value.strip() for key, value in tpm_data}
    mfg = tpm_dict.get('Manufacturer Info', None)
    version = tpm_dict.get('Chip Version', None)
    if mfg is not None and version is not None:
      return [{'manufacturer_info': mfg, 'version': version}]
    return None
