#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Tools to mount rootfs partition from mini-Omaha kernel+rootfs image file."""


import argparse
import logging

import factory_common  # pylint: disable=W0611
from cros.factory.utils.sys_utils import MountPartition


def main():
  logging.basicConfig(level=logging.INFO)
  parser = argparse.ArgumentParser(
      description=('Mount a rootfs partition from a mini-Omaha channel file, '
                   'which is kernel+rootfs.'))
  parser.add_argument('source_path',
                      help='a mini-Omaha channel file')
  parser.add_argument('mount_point', help='mount point')
  args = parser.parse_args()

  MountPartition(args.source_path, mount_point=args.mount_point,
                 is_omaha_channel=True)

if __name__ == '__main__':
  main()
