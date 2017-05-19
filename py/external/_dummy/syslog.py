# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dummy implementation for syslog."""

import logging

def openlog(unused_name):
  pass

def syslog(message):
  logging.info('Dummy syslog: %s', message)
