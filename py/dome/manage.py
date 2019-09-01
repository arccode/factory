#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import signal
import sys

from django.core.management import execute_from_command_line


def handler(signum, frame):
  del signum, frame  # Unused.
  sys.exit(1)


def main():
  signal.signal(signal.SIGTERM, handler)
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
  execute_from_command_line(sys.argv)


if __name__ == '__main__':
  main()
