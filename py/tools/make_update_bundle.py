#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import getpass
import logging
import os
import subprocess
import sys

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn

BUNDLE_MOUNT_POINT = '/mnt/factory_bundle'

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

  for line in open('/etc/mtab').readlines():
    if line.split()[2] == BUNDLE_MOUNT_POINT:
      logging.error('%s is already mounted', BUNDLE_MOUNT_POINT)
      sys.exit(1)

  if getpass.getuser() != 'root':
    logging.info("You're not root: running with sudo")
    os.execvp('sudo', ['sudo'] + sys.argv)
    logging.error("Unable to run sudo")
    sys.exit(1)

  mount_script = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src',
                              'platform', 'factory-utils', 'factory_setup',
                              'mount_partition.sh')

  utils.TryMakeDirs(BUNDLE_MOUNT_POINT)
  Spawn([mount_script, args.factory_image, '1', BUNDLE_MOUNT_POINT],
        check_call=True, log=True)
  try:
    Spawn(['tar', 'cf', args.output, '-I', 'pbzip2',
           '-C', os.path.join(BUNDLE_MOUNT_POINT, 'dev_image'),
           '--exclude', 'factory/MD5SUM',
           'factory', 'autotest'],
          check_call=True, log=True)
    md5sum = (Spawn(['md5sum', args.output], check_output=True).
              stdout_data.split()[0])
    logging.info('MD5SUM is %s', md5sum)
    md5sum_file = os.path.join(BUNDLE_MOUNT_POINT,
                               'dev_image', 'factory', 'MD5SUM')
    logging.info('Saving MD5SUM to %s', md5sum_file)
    with open(md5sum_file, 'w') as f:
      f.write(md5sum)
  finally:
    for _ in xrange(5):
      try:
        Spawn(['umount', BUNDLE_MOUNT_POINT], call=True, log=True)
        break
      except subprocess.CalledProcessError:
        pass
    else:
      logging.error('Unable to unmount %s', BUNDLE_MOUNT_POINT)


if __name__ == '__main__':
  main()
