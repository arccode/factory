#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test program for tiny_par_unittest.py."""

import sys


def main():
  if len(sys.argv) > 2:
    print(' '.join(sys.argv[2:]))
  if len(sys.argv) > 1:
    sys.exit(int(sys.argv[1]))


if __name__ == '__main__':
  main()
