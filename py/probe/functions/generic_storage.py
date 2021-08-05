# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.probe.lib import runtime_probe_function


class GenericStorageFunction(runtime_probe_function.RuntimeProbeFunction):
  """Probe the generic storage information."""
  CATEGORY_NAME = 'storage'
  FUNCTION_NAME = 'generic_storage'
