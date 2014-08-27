#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import os
import re
import subprocess
import sys
from contextlib import contextmanager

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn
from cros.factory.utils.sys_utils import MountPartition


STATEFUL_PARTITION_INDEX = 1

BLACKLIST = map(re.compile, [
    'autotest/deps/',
    'autotest/site_tests/.+/src/',
    'autotest/site_tests/audiovideo_V4L2/media_v4l2_.*test$',
    ])


def DiffImages(mount_point_1, mount_point_2, out=sys.stdout):
  '''Compares two images.

  Args:
    mount_point_1, mount_point_2: Mount points of stateful partitions of images
      to compare.
    out: Output to which differences should be printed.
  '''
  mount_points = [mount_point_1, mount_point_2]

  # Hold in a variable since we want to change in an inner function.
  differences = [0]

  for d in ['autotest', 'factory']:
    process = Spawn(
        ['diff', '-qr'] +
        # Skip client directory in autotest, since it causes a recursive
        # directory loop in diff.  This isn't perfect since it skips
        # *everything* called client, but it'll do.
        (['-x', 'client'] if d == 'autotest' else []) +
        [os.path.join(x, 'dev_image', d) for x in mount_points],
        read_stdout=True, log=True,
        check_call=lambda returncode: returncode in [0,1])

    for line in process.stdout_lines():
      match = re.match('^Files (.+) and (.+) differ$|'
                       '^Only in (.+): (.+)$',
                       line)
      assert match, 'Weird line in diff output: %r' % line

      if match.group(1):
        # Files exist in both trees, but differ
        paths = [match.group(1), match.group(2)]
      else:
        assert match.group(3)
        path = os.path.join(match.group(3), match.group(4))
        if path.startswith(mount_points[0]):
          paths = [path, None]
        elif path.startswith(mount_points[1]):
          paths = [None, path]
        else:
          assert False, (
              "path doesn't start with either of %s" % mount_points)

      stripped_paths = []
      for i in (0, 1):
        if paths[i]:
          prefix = os.path.join(mount_points[i], 'dev_image', '')
          assert paths[i].startswith(prefix)
          # Strip the prefix
          stripped_paths.append(paths[i][len(prefix):])

      assert all(x == stripped_paths[0] for x in stripped_paths), (
          stripped_paths)

      stripped_path = stripped_paths[0]

      blacklist_matches = [x for x in BLACKLIST
                           if x.match(stripped_path)]
      if blacklist_matches:
        logging.debug('Skipping %s since it matches %r',
                      stripped_path,
                      [x.pattern for x in blacklist_matches])
        continue

      def PrintHeader(message):
        print >> out
        print >> out, '*** %s' % stripped_path
        print >> out, '*** %s' % message
        differences[0] += 1

      if any(x is None for x in paths):
        # We only have one or the other
        PrintHeader('Only in image%d' % (1 if paths[0] else 2))
        continue

      # It's a real difference.  Are either or both symlinks?
      is_symlink = map(os.path.islink, paths)

      if is_symlink[0] != is_symlink[1]:

        def _IsSymlinkStr(value):
          return 'is' if value else 'is not'

        # That's a difference.
        PrintHeader('%s symlink in image1 but %s in image2' %
                    (_IsSymlinkStr(is_symlink[0]),
                     _IsSymlinkStr(is_symlink[1])))

      elif is_symlink[0]:
        link_paths = map(os.readlink, paths)
        if link_paths[0] != link_paths[1]:
          PrintHeader('symlink to %r in image1 but %r in image2' %
                      tuple(link_paths))
      else:
        # They're both regular files; print a unified diff of the
        # contents.
        process = Spawn(
            ['diff', '-u'] + paths,
            check_call=lambda returncode: returncode in [0,1,2],
            read_stdout=True)
        if process.returncode == 2:
          if re.match('Binary files .+ differ\n$', process.stdout_data):
            PrintHeader('Binary files differ')
          else:
            raise subprocess.CalledProcessError(process.returncode,
              process.args)
        else:
          PrintHeader('Files differ; unified diff follows')
          out.write(process.stdout_data)

  return differences[0]


def main(argv=None, out=sys.stdout):
  parser = argparse.ArgumentParser(
      description=("Compares the autotest and factory directories in "
                   "two partitions."))
  parser.add_argument('--verbose', '-v', action='count')
  parser.add_argument('images', metavar='IMAGE', nargs=2)
  args = parser.parse_args(argv or sys.argv)
  logging.basicConfig(level=logging.WARNING - 10 * (args.verbose or 0))

  mount_points = ['/tmp/diff_image_1', '/tmp/diff_image_2']
  for f in mount_points:
    utils.TryMakeDirs(f)

  def MountOrReuse(index):
    if os.path.isdir(args.images[index]):
      @contextmanager
      def Image():
        yield args.images[index]
      return Image()
    else:
      return MountPartition(args.images[index], STATEFUL_PARTITION_INDEX,
                            mount_points[index])

  differences = 0
  with MountOrReuse(0) as mount_point_0:
    with MountOrReuse(1) as mount_point_1:
      differences += DiffImages(mount_point_0, mount_point_1, out)

  print >> out
  print >> out, 'Found %d differences' % differences
  sys.exit(0 if differences == 0 else 1)

if __name__ == '__main__':
  main()
