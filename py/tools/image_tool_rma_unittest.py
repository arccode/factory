#!/usr/bin/env python
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


from __future__ import print_function

import argparse
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.tools import image_tool


DEBUG = False
"""Set DEBUG to True to debug this unit test itself.

The major difference is all output will be preserved in /tmp/t.
"""


class ImageToolRMATest(unittest.TestCase):
  """Unit tests for image_tool RMA related commands."""

  UPDATER_CONTENT = ('#!/bin/sh\n'
                     'echo \'{"project": {"host": {"versions": '
                     '{"ro": "RO", "rw": "RW"}}}}\'\n')
  LSB_CONTENT = 'CHROMEOS_RELEASE_VERSION=1.0\nCHROMEOS_RELEASE_BOARD=%s\n'

  PARTITION_COMMANDS = [
      '%(command)s create %(file)s',
      '%(command)s boot -p %(file)s',
      '%(command)s add -i 2 -s 1024 -b 34 -t kernel %(file)s',
      '%(command)s add -i 3 -s 2048 -b 1058 -t rootfs %(file)s',
      '%(command)s add -i 4 -s 1024 -b 3106 -t kernel %(file)s',
      '%(command)s add -i 5 -s 2048 -b 4130 -t rootfs %(file)s',
      '%(command)s add -i 6 -s 1 -b 6178 -t kernel %(file)s',
      '%(command)s add -i 7 -s 1 -b 6179 -t rootfs %(file)s',
      '%(command)s add -i 8 -s 1 -b 6180 -t data %(file)s',
      '%(command)s add -i 9 -s 1 -b 6181 -t reserved %(file)s',
      '%(command)s add -i 10 -s 1 -b 6182 -t reserved %(file)s',
      '%(command)s add -i 11 -s 1 -b 6183 -t firmware %(file)s',
      '%(command)s add -i 12 -s 1 -b 6184 -t efi %(file)s',
      '%(command)s add -i 1 -s 16384 -b 6185 -t data %(file)s',
  ]

  def CheckCall(self, command):
    return subprocess.check_call(command, shell=True, cwd=self.temp_dir)

  def ImageTool(self, *args):
    command = args[0]
    self.assertIn(command, self.cmd_map, 'Unknown command: %s' % command)
    cmd = self.cmd_map[command](*self.cmd_parsers)
    cmd.Init()
    cmd_args = self.cmd_parsers[0].parse_args(args)
    cmd_args.verbose = 0
    cmd_args.subcommand.args = cmd_args
    cmd_args.subcommand.Run()

  def CreateDiskImage(self, name, lsb_content):
    image_path = os.path.join(self.temp_dir, name)
    dir_path = os.path.dirname(image_path)
    if not os.path.exists(dir_path):
      os.makedirs(dir_path)
    self.CheckCall('truncate -s %s %s' % (16 * 1048576, name))
    for command in self.PARTITION_COMMANDS:
      self.CheckCall(command % dict(command='cgpt', file=name))
    with image_tool.GPT.Partition.MapAll(image_path) as f:
      self.CheckCall('sudo mkfs -F %sp3' % f)
      self.CheckCall('sudo mkfs -F %sp5' % f)
      self.CheckCall('sudo mkfs -F %sp1 2048' % f)
    with image_tool.Partition(image_path, 3).Mount(rw=True) as d:
      fw_path = os.path.join(d, 'usr', 'sbin', 'chromeos-firmwareupdate')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(fw_path))
      tmp_fw_path = os.path.join(self.temp_dir, 'chromeos-firmwareupdate')
      with open(tmp_fw_path, 'w') as f:
        f.write(self.UPDATER_CONTENT)
      self.CheckCall('sudo mv %s %s' % (tmp_fw_path, fw_path))
      self.CheckCall('sudo chmod a+rx %s' % fw_path)
      common_sh_path = os.path.join(
          d, 'usr', 'share', 'misc', 'chromeos-common.sh')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(common_sh_path))
      self.CheckCall('echo "%s" | sudo dd of=%s' %
                     ('#!/bin/sh', common_sh_path))
      lsb_path = os.path.join(d, 'etc', 'lsb-release')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(lsb_path))
      self.CheckCall('echo "%s" | sudo dd of=%s' %
                     (lsb_content.strip('\n'), lsb_path))
      write_gpt_path = os.path.join(d, 'usr', 'sbin', 'write_gpt.sh')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(write_gpt_path))
      tmp_write_gpt_path = os.path.join(self.temp_dir, 'write_gpt.sh')
      write_command = '\n'.join(
          cmd % dict(command='cgpt', file='$1')
          for cmd in self.PARTITION_COMMANDS)
      with open(tmp_write_gpt_path, 'w') as f:
        f.write('\n'.join([
            '#!/bin/sh',
            'GPT=""',
            'GPT="cgpt"',  # Override for unit test.
            'write_base_table() {',
            write_command,
            '}',
        ]))
      self.CheckCall('sudo mv %s %s' % (tmp_write_gpt_path, write_gpt_path))

    with image_tool.Partition(image_path, 1).Mount(rw=True) as d:
      lsb_path = os.path.join(d, 'dev_image', 'etc', 'lsb-factory')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(lsb_path))
      self.CheckCall('echo "%s" | sudo dd of=%s' %
                     (lsb_content.strip('\n'), lsb_path))
      self.CheckCall('sudo mkdir -p %s' % os.path.join(
          d, 'unencrypted', 'import_extensions'))

  def SetupBundleEnvironment(self, image_path):
    for dir_name in ['factory_shim', 'test_image', 'release_image',
                     'toolkit', 'hwid', 'complete', 'firmware']:
      dir_path = os.path.join(self.temp_dir, dir_name)
      if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    for name in ['release_image', 'test_image', 'factory_shim']:
      dest_path = os.path.join(self.temp_dir, name, 'image.bin')
      shutil.copy(image_path, dest_path)
      with image_tool.Partition(dest_path, 3).Mount(rw=True) as d:
        self.CheckCall('echo "%s" | sudo dd of="%s"' %
                       (name, os.path.join(d, 'tag')))
      with image_tool.Partition(dest_path, 1).Mount(rw=True) as d:
        self.CheckCall('echo "%s" | sudo dd of="%s"' %
                       (name, os.path.join(d, 'tag')))
    toolkit_path = os.path.join(self.temp_dir, 'toolkit', 'toolkit.run')
    with open(toolkit_path, 'w') as f:
      f.write('#!/bin/sh\necho Toolkit Version 1.0\n')
    os.chmod(toolkit_path, 0o755)

  def setUp(self):
    if DEBUG:
      self.temp_dir = '/tmp/t'
    else:
      self.temp_dir = tempfile.mkdtemp(prefix='image_tool_rma_ut_')
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers()
    self.cmd_parsers = (parser, subparser)
    self.cmd_map = dict(
        (v.name, v) for v in image_tool.__dict__.values()
        if inspect.isclass(v) and issubclass(v, image_tool.SubCommand))

  def tearDown(self):
    if not DEBUG:
      if os.path.exists(self.temp_dir):
        shutil.rmtree(self.temp_dir)

  def testRMACommands(self):
    """Test RMA related commands.

    To speed up execution time (CreateDiskImage takes ~2s while shutil.copy only
    takes 0.1s) we are testing all commands in one single test case.
    """
    self.CreateDiskImage('test1.bin', self.LSB_CONTENT % 'test1')
    self.CreateDiskImage('test2.bin', self.LSB_CONTENT % 'test2')
    self.CreateDiskImage('test3.bin', self.LSB_CONTENT % 'test3')
    image_path1 = os.path.join(self.temp_dir, 'test1.bin')
    image_path2 = os.path.join(self.temp_dir, 'test2.bin')
    image_path3 = os.path.join(self.temp_dir, 'test3.bin')
    os.chdir(self.temp_dir)

    # `rma-create` to create 3 RMA shims.
    self.SetupBundleEnvironment(image_path1)
    self.ImageTool('rma-create', '-o', 'rma1.bin')
    self.SetupBundleEnvironment(image_path2)
    self.ImageTool('rma-create', '-o', 'rma2.bin')
    self.SetupBundleEnvironment(image_path3)
    self.ImageTool('rma-create', '-o', 'rma3.bin')

    # Verify content of RMA shim.
    image_tool.Partition('rma1.bin', 1).CopyFile('tag', 'tag.1')
    image_tool.Partition('rma1.bin', 3).CopyFile('tag', 'tag.3')
    image_tool.Partition('rma1.bin', 1).CopyFile(
        'cros_payloads/test1.json', self.temp_dir)
    image_tool.Partition('rma1.bin', 1).CopyFile(
        image_tool.PATH_CROS_RMA_METADATA, self.temp_dir)
    self.assertEqual(open('tag.1').read().strip(), 'factory_shim')
    self.assertEqual(open('tag.3').read().strip(), 'factory_shim')
    with open('test1.json') as f:
      data = json.load(f)
    self.assertEqual(data['toolkit']['version'], u'Toolkit Version 1.0')
    with open(os.path.basename(image_tool.PATH_CROS_RMA_METADATA)) as f:
      data = json.load(f)
    self.assertEqual(data, [{'board': 'test1', 'kernel': 2, 'rootfs': 3}])

    # `rma-merge` to merge 2 different shims.
    self.ImageTool(
        'rma-merge', '-f', '-o', 'rma12.bin', '-i', 'rma1.bin', 'rma2.bin')
    image_tool.Partition('rma12.bin', 1).CopyFile(
        image_tool.PATH_CROS_RMA_METADATA, self.temp_dir)
    with open(os.path.basename(image_tool.PATH_CROS_RMA_METADATA)) as f:
      data = json.load(f)
    self.assertEqual(data, [{'board': 'test1', 'kernel': 2, 'rootfs': 3},
                            {'board': 'test2', 'kernel': 4, 'rootfs': 5}])

    # `rma-merge` to merge a universal shim and a normal shim.
    self.ImageTool(
        'rma-merge', '-f', '-o', 'rma123.bin', '-i', 'rma12.bin', 'rma3.bin')
    image_tool.Partition('rma123.bin', 1).CopyFile(
        image_tool.PATH_CROS_RMA_METADATA, self.temp_dir)
    with open(os.path.basename(image_tool.PATH_CROS_RMA_METADATA)) as f:
      data = json.load(f)
    self.assertEqual(data, [{'board': 'test1', 'kernel': 2, 'rootfs': 3},
                            {'board': 'test2', 'kernel': 4, 'rootfs': 5},
                            {'board': 'test3', 'kernel': 6, 'rootfs': 7}])


if __name__ == '__main__':
  # Support `cros_payload` in bin/ folder.
  new_path = os.path.realpath(os.path.join(
      os.path.dirname(os.path.realpath(__file__)), '..', '..', 'bin'))
  os.putenv('PATH', ':'.join(os.getenv('PATH', '').split(':') + [new_path]))

  sys.path.append(new_path)
  unittest.main()
