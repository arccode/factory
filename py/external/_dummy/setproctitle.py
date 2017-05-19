# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dummy implementation for setproctitle."""

import logging

def setproctitle(message):
  logging.info('Dummy setproctitle: %s', message)
