# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Cloud stoarge buckets and service environment configuration."""

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import filesystem_adapter
from cros.factory.hwid.service.appengine import hwid_manager


_CONFIGURATIONS = {
    's~google.com:chromeoshwid': {
        'env': 'prod',
        'bucket': 'chromeoshwid',
        'ge_bucket': 'chromeos-build-release-console',
    },
    's~google.com:chromeoshwid-staging': {
        'env': 'staging',
        'bucket': 'chromeoshwid-staging',
        'ge_bucket': 'chromeos-build-release-console-staging',
    },
    'default': {
        'env': 'dev',
        'bucket': 'chromeoshwid-dev',
        # Allow unauthenticated access when running a local dev server and
        # during tests.
        'skip_auth_check': True,
        'ge_bucket': 'chromeos-build-release-console-staging',
    }
}


def GetConfig():
  try:
    app_id = os.environ['APPLICATION_ID']
    return _CONFIGURATIONS.get(app_id, _CONFIGURATIONS['default'])
  except KeyError:
    return _CONFIGURATIONS['default']


# TODO(yllin): Refactor config for naming convention.
config = GetConfig()
ge_filesystem = filesystem_adapter.CloudStorageAdapter(config['ge_bucket'])
hwid_filesystem = filesystem_adapter.CloudStorageAdapter(config['bucket'])
hwid_manager = hwid_manager.HwidManager(hwid_filesystem)
