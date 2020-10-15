#!/usr/bin/env python3
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from cros.factory.tools import image_tool
from cros.factory.utils import process_utils


DEBUG = False
"""Set DEBUG to True to debug this unit test itself.

The major difference is all output will be preserved in /tmp/t.
"""


class ImageToolTest(unittest.TestCase):
  """Unit tests for image_tool."""

  UPDATER_CONTENT = '#!/bin/sh\necho FirmwareUpdate\n'
  LSB_CONTENT = 'CHROMEOS_RELEASE_VERSION=1.0\nCHROMEOS_RELEASE_BOARD=test\n'

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

  def CreateDiskImage(self, name):
    cgpt = image_tool.SysUtils.FindCGPT()
    image_path = os.path.join(self.temp_dir, name)
    dir_path = os.path.dirname(image_path)
    if not os.path.exists(dir_path):
      os.makedirs(dir_path)
    self.CheckCall('truncate -s %s %s' % (16 * 1048576, name))
    for command in self.PARTITION_COMMANDS:
      self.CheckCall(command % dict(command=cgpt, file=name))
    with image_tool.GPT.Partition.MapAll(image_path) as f:
      self.CheckCall('sudo mkfs -F %sp3' % f)
      self.CheckCall('sudo mkfs -F %sp5' % f)
      self.CheckCall('sudo mkfs -F %sp1 2048' % f)
    with image_tool.Partition(image_path, 3).Mount(rw=True) as d:
      fw_path = os.path.join(d, 'usr', 'sbin', 'chromeos-firmwareupdate')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(fw_path))
      self.CheckCall('echo "%s" | sudo dd of=%s' %
                     (self.UPDATER_CONTENT.strip('\n'), fw_path))
      self.CheckCall('sudo chmod a+rx %s' % fw_path)
      common_sh_path = os.path.join(
          d, 'usr', 'share', 'misc', 'chromeos-common.sh')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(common_sh_path))
      self.CheckCall('echo "%s" | sudo dd of=%s' %
                     ('#!/bin/sh', common_sh_path))
      lsb_path = os.path.join(d, 'etc', 'lsb-release')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(lsb_path))
      self.CheckCall('echo "%s" | sudo dd of=%s' %
                     (self.LSB_CONTENT.strip('\n'), lsb_path))
      write_gpt_path = os.path.join(d, 'usr', 'sbin', 'write_gpt.sh')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(write_gpt_path))
      tmp_write_gpt_path = os.path.join(self.temp_dir, 'write_gpt.sh')
      write_command = '\n'.join(
          cmd % dict(command=cgpt, file='$1')
          for cmd in self.PARTITION_COMMANDS)
      with open(tmp_write_gpt_path, 'w') as f:
        f.write('\n'.join([
            '#!/bin/sh',
            'GPT=""',
            'GPT="%s"' % cgpt,  # Override for unit test.
            'write_base_table() {',
            write_command,
            '}',
        ]))
      self.CheckCall('sudo mv %s %s' % (tmp_write_gpt_path, write_gpt_path))

    with image_tool.Partition(image_path, 1).Mount(rw=True) as d:
      lsb_path = os.path.join(d, 'dev_image', 'etc', 'lsb-factory')
      self.CheckCall('sudo mkdir -p %s' % os.path.dirname(lsb_path))
      self.CheckCall('echo "%s" | sudo dd of=%s' %
                     (self.LSB_CONTENT.strip('\n'), lsb_path))
      self.CheckCall('sudo mkdir -p %s' % os.path.join(
          d, 'unencrypted', 'import_extensions'))

  def SetupBundleEnvironment(self, image_path):
    for dir_name in ['factory_shim', 'test_image', 'release_image', 'toolkit',
                     'hwid', 'complete', 'firmware', 'project_config']:
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
      self.temp_dir = tempfile.mkdtemp(prefix='image_tool_ut_')
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

  def testImageCommands(self):
    """Test all commands that needs disk images.

    To speed up execution time (CreateDiskImage takes ~2s while shutil.copy only
    takes 0.1s) we are testing all commands that needs disk images in one single
    test case.
    """
    self.CreateDiskImage('test.bin')
    image_path = os.path.join(self.temp_dir, 'test.bin')
    mnt_dir = os.path.join(self.temp_dir, 'mnt', str(time.time()))
    os.makedirs(mnt_dir)

    try:
      self.ImageTool('mount', '-ro', image_path, '3', mnt_dir)
      self.assertTrue(os.path.exists(os.path.join(mnt_dir, 'usr', 'sbin')))
    finally:
      self.CheckCall('sudo umount %s' % mnt_dir)

    try:
      self.ImageTool('mount', '-rw', image_path, '3', mnt_dir)
      self.assertTrue(os.path.exists(os.path.join(mnt_dir, 'usr', 'sbin')))
      self.CheckCall('sudo touch %s' % os.path.join(mnt_dir, 'rw'))
    finally:
      self.CheckCall('sudo umount %s' % mnt_dir)

    self.ImageTool('get_firmware', '-i', image_path, '-o', self.temp_dir)
    updater = os.path.join(self.temp_dir, 'chromeos-firmwareupdate')
    with open(updater) as f:
      self.assertEqual(self.UPDATER_CONTENT, f.read())

    self.ImageTool('resize', '-i', image_path, '-p', '1', '-s', '2')
    part = image_tool.Partition(image_path, 1)
    self.assertEqual(part.size, 8388608)
    self.assertEqual(part.GetFileSystemSize(), 4194304)

    self.ImageTool('resize', '-i', image_path, '-p', '1', '-s', '7',
                   '--no-append')
    part = image_tool.Partition(image_path, 1)
    self.assertEqual(part.GetFileSystemSize(), 7340032)

    # Prepare the environment to run bundle commands, which need to run inside
    # the temp folder.
    self.SetupBundleEnvironment(image_path)
    os.chdir(self.temp_dir)

    self.ImageTool('preflash', '-o', 'disk.bin', '--stateful', '1')
    self.assertEqual(os.path.getsize('disk.bin'), 16013942784)
    image_tool.Partition('disk.bin', 1).CopyFile('tag', 'tag.1')
    image_tool.Partition('disk.bin', 3).CopyFile('tag', 'tag.3')
    image_tool.Partition('disk.bin', 5).CopyFile('tag', 'tag.5')
    self.assertEqual(open('tag.1').read().strip(), 'test_image')
    self.assertEqual(open('tag.3').read().strip(), 'test_image')
    self.assertEqual(open('tag.5').read().strip(), 'release_image')
    image_tool.Partition('disk.bin', 1).CopyFile(
        image_tool.PATH_PREFLASH_PAYLOADS_JSON, 'preflash.json')
    with open('preflash.json') as f:
      data = json.load(f)
    self.assertEqual(data['toolkit']['version'], u'Toolkit Version 1.0')

    self.ImageTool('bundle', '--no-firmware', '--timestamp', '20180101')
    bundle_name = 'factory_bundle_test_20180101_proto.tar.bz2'
    self.assertTrue(os.path.exists(bundle_name))
    contents = process_utils.CheckOutput('tar -xvf %s' % bundle_name,
                                         shell=True)
    contents = [line.split()[-1] for line in contents.splitlines()]
    self.assertCountEqual(
        contents,
        ['./', './README.md', './factory_shim/', './factory_shim/image.bin',
         './release_image/', './release_image/image.bin', './test_image/',
         './test_image/image.bin', './toolkit/', './toolkit/toolkit.run'])


class UserInputTest(unittest.TestCase):
  """Unit tests for image_tool.UserInput."""

  @mock.patch('builtins.input')
  def testSelect(self, input_mock):
    title = 'test_select'
    options_list = ['a', 'b']
    options_dict = {'a': 1, 'b': 2}

    # '1' is valid, and converted into 0-based index, which is 0.
    input_mock.side_effect = ['0', '3', 'a', '', '1']
    answer = image_tool.UserInput.Select(title, options_list)
    self.assertEqual(answer, 0)

    # Empty string is accepted.
    input_mock.side_effect = ['0', '3', 'a', '', '1']
    answer = image_tool.UserInput.Select(title, options_list, optional=True)
    self.assertEqual(answer, None)

    # 'a' is valid.
    input_mock.side_effect = ['1', 'c', 'a']
    answer = image_tool.UserInput.Select(title, options_dict=options_dict)
    self.assertEqual(answer, 'a')

    # List and dict combined.
    input_mock.side_effect = ['2']
    answer = image_tool.UserInput.Select(title, options_list, options_dict)
    self.assertEqual(answer, 1)
    input_mock.side_effect = ['b']
    answer = image_tool.UserInput.Select(title, options_list, options_dict)
    self.assertEqual(answer, 'b')

  @mock.patch('builtins.input')
  def testYesNo(self, input_mock):
    title = 'test_yes_no'

    input_mock.side_effect = ['', 'y']
    answer = image_tool.UserInput.YesNo(title)
    self.assertEqual(answer, True)
    input_mock.side_effect = ['a', 'n']
    answer = image_tool.UserInput.YesNo(title)
    self.assertEqual(answer, False)

  @mock.patch('builtins.input')
  def testGetNumber(self, input_mock):
    title = 'test_get_number'

    # No range.
    input_mock.side_effect = ['', '10']
    answer = image_tool.UserInput.GetNumber(title)
    self.assertEqual(answer, 10)

    input_mock.side_effect = ['', '10']
    answer = image_tool.UserInput.GetNumber(title, optional=True)
    self.assertEqual(answer, None)

    # With range.
    input_mock.side_effect = ['10', '1']
    answer = image_tool.UserInput.GetNumber(title, max_value=5)
    self.assertEqual(answer, 1)

    input_mock.side_effect = ['10', '1', '3']
    answer = image_tool.UserInput.GetNumber(title, min_value=2, max_value=5)
    self.assertEqual(answer, 3)

  @mock.patch('builtins.input')
  def testGetString(self, input_mock):
    title = 'test_get_string'

    input_mock.side_effect = ['', 'test']
    answer = image_tool.UserInput.GetString(title)
    self.assertEqual(answer, 'test')
    input_mock.side_effect = ['', 'test']
    answer = image_tool.UserInput.GetString(title, optional=True)
    self.assertEqual(answer, None)


if __name__ == '__main__':
  # Support `cros_payload` in bin/ folder.
  new_path = os.path.realpath(os.path.join(
      os.path.dirname(os.path.realpath(__file__)), '..', '..', 'bin'))
  os.putenv('PATH', ':'.join(os.getenv('PATH', '').split(':') + [new_path]))

  sys.path.append(new_path)
  unittest.main()
