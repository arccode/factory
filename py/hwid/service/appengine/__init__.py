# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handle site packages and package name conflicts inside docker."""

import os
import site
import sys


def _patch_imports():
  google = 'google'
  site_dir = os.environ.get('CUSTOMIZE_SITE_DIR')
  appengine_sdk_dir = os.environ.get('APPENGINE_SDK_DIR')
  if site_dir:
    site.addsitedir(site_dir)
    # Referenced from
    # https://github.com/GoogleCloudPlatform/python-repo-tools/blob/87422ba/gcp_devrel/testing/appengine.py#L39-L41
    if google in sys.modules and appengine_sdk_dir:
      sys.modules[google].__path__.append(
          os.path.join(appengine_sdk_dir, google))


_patch_imports()
