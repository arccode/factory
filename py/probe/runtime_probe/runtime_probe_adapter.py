# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

from cros.factory.probe.runtime_probe import probe_config_definition
from cros.factory.probe.runtime_probe import probe_config_types
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


RUNTIME_PROBE_BIN = os.path.join(
    os.path.dirname(__file__), '../../../bin/runtime_probe_invoker')
COMPONENT_NAME = 'adaptor_component'


def RunProbeFunction(category, probe_function_name, args):
  definition = probe_config_definition.GetProbeStatementDefinition(category)
  probe_statement = definition.GenerateProbeStatement(
      COMPONENT_NAME, probe_function_name, {}, args)
  payload = probe_config_types.ProbeConfigPayload()
  payload.AddComponentProbeStatement(probe_statement)

  with file_utils.UnopenedTemporaryFile() as config_file:
    with open(config_file, 'w') as f:
      f.write(payload.DumpToString())
    output = process_utils.CheckOutput(
        [RUNTIME_PROBE_BIN, f'--config_file_path={config_file}', '--to_stdout'])
  res = json_utils.LoadStr(output)
  return [x['values'] for x in res[category]]
