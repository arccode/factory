# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

import factory_common  # pylint: disable=unused-import
from cros.factory.test.test_lists import manager


PORT = 4013

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
STATIC_DIR = os.path.realpath(
    os.path.join(SCRIPT_DIR, '..', 'frontend', 'dist'))
PUBLIC_TEST_LISTS_DIR = os.path.realpath(
    os.path.join(SCRIPT_DIR, '..', '..', '..', manager.TEST_LISTS_RELPATH))
PRIVATE_TEST_LISTS_RELPATH = os.path.join(
    'chromeos-base', 'factory-board', 'files', manager.TEST_LISTS_RELPATH)
