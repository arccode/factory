# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sample parser module for the DRM Keys Provisioning Server."""

import json


def Parse(serialized_drm_key_list):
  # TODO(littlecvr): Add comment on how to write a Parse() function.
  return json.loads(serialized_drm_key_list)
