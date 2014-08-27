#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Tools to mount partition in an image or a block device."""


import argparse
import logging

import factory_common  # pylint: disable=W0611
from cros.factory.utils.sys_utils import MountPartition


def main():
  logging.basicConfig(level=logging.INFO)
  parser = argparse.ArgumentParser(
      description="Mount a partition in an image file.")
  parser.add_argument('-rw', '--rw', action='store_true',
                      help='mount partition read/write')
  parser.add_argument('source_path', help='an image file or a block device')
  parser.add_argument('index', type=int, help='partition index')
  parser.add_argument('mount_point', help='mount point')
  args = parser.parse_args()

  MountPartition(args.source_path, args.index, args.mount_point, args.rw)

if __name__ == '__main__':
  main()
