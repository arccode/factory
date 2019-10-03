# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A helper module provides constants and common classes."""

import os


INSTALOG_DIR = os.path.dirname(
    os.path.realpath(__file__.replace('.pyc', '.py')))
INSTALOG_PARENT_DIR = os.path.realpath(os.path.join(INSTALOG_DIR, '..'))
INSTALOG_VIRTUAL_ENV_DIR = (
    os.environ.get('VIRTUAL_ENV') or
    os.path.realpath(os.path.join(INSTALOG_DIR, 'virtual_env')))
