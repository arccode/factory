#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import os
import pipes
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sys_utils import MountPartition

BUNDLE_MOUNT_POINT = '/mnt/factory_bundle'

def MakeUpdateBundle(factory_image, output):
  """Prepares an updater bundle.

  Args:
    factory_image: Path to the image.
    output: Path to the factory.tar.bz2 bundle.

  Returns:
    The MD5SUM of the bundle.
  """
  for line in open('/etc/mtab').readlines():
    if line.split()[2] == BUNDLE_MOUNT_POINT:
      logging.error('%s is already mounted', BUNDLE_MOUNT_POINT)
      sys.exit(1)

  # Make BUNDLE_MOUNT_POINT as root.
  Spawn(['mkdir', '-p', BUNDLE_MOUNT_POINT], sudo=True, check_call=True)
  with MountPartition(factory_image, 1, BUNDLE_MOUNT_POINT,
                      rw=True):
    Spawn(['tar', 'cf', output, '-I', 'pbzip2',
           '-C', os.path.join(BUNDLE_MOUNT_POINT, 'dev_image'),
           '--exclude', 'factory/MD5SUM',
           'factory', 'autotest'],
           check_call=True, log=True)
    md5sum = (Spawn(['md5sum', output], check_output=True).
              stdout_data.split()[0])
    logging.info('MD5SUM is %s', md5sum)
    md5sum_file = os.path.join(BUNDLE_MOUNT_POINT,
                               'dev_image', 'factory', 'MD5SUM')
    # Use a shell, since we may need to be root to do this.
    Spawn('echo %s > %s' % (md5sum, pipes.quote(md5sum_file)),
          shell=True, sudo=True, log=True, check_call=True)

    return md5sum


def main():
  logging.basicConfig(level=logging.INFO)
  parser = argparse.ArgumentParser(
      description="Prepare an updater bundle.")
  parser.add_argument('-i', '--factory_image', metavar='FILE',
                      dest='factory_image',
                      required=True,
                      help='factory image from which to create the bundle')
  parser.add_argument('-o', '--output', metavar='BZFILE',
                      dest='output',
                      default='factory.tar.bz2',
                      help='output bundle')
  args = parser.parse_args()
  MakeUpdateBundle(args.factory_image, args.output)


if __name__ == '__main__':
  main()
