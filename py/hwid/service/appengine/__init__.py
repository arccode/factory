# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handle site packages and package name conflicts inside docker."""

import functools
import os
import os.path
import site
import sys


_APPENGINE_SRC_ROOT = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    '..', '..', '..', '..', '..')


def _PatchImports():
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


@functools.lru_cache(maxsize=1)
def _SetRegionPathEnv():
  if os.environ.get('IS_APPENGINE') == 'true':
    resource_dir = os.path.join(_APPENGINE_SRC_ROOT, 'resource')
    os.environ.setdefault('CROS_REGIONS_DATABASE',
                          os.path.join(resource_dir, 'cros-regions.json'))


@functools.lru_cache(maxsize=1)
def _AddProtoDir():
  sys.path.append(os.path.join(_APPENGINE_SRC_ROOT, 'protobuf_out'))


_PatchImports()
_SetRegionPathEnv()
_AddProtoDir()
