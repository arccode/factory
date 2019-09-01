#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import process_utils


CMD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'probe_cmdline.py')


class ProbeCmdTest(unittest.TestCase):
  def assertProbedResultEquals(self, result1, result2):
    self.assertEquals(len(result1), len(result2))
    for k, v1 in result1.iteritems():
      self.assertIn(k, result2)
      self.assertEquals(sorted(v1), sorted(result2[k]))

  def setUp(self):
    self.tmp_file = file_utils.CreateTemporaryFile()
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isfile(self.tmp_file):
      os.remove(self.tmp_file)
    if os.path.isdir(self.tmp_dir):
      shutil.rmtree(self.tmp_dir)

  def testNormal(self):
    with open(self.tmp_file, 'w') as f:
      f.write('asdf\n')
    expected = {
        'foo': [],
        'audio': [
            {'name': 'Lala', 'values': {'file_raw': 'asdf'}}],
        'bar': [
            {'name': 'bar_1', 'values': {'shell_raw': 'hello'}},
            {'name': 'bar_2', 'values': {'shell_raw': 'world'}}]}
    statement = {
        # There is no result in foo.
        'foo': {
            'foo_1': {
                'eval': 'shell:echo hello',
                'expect': 'asdf'
            }
        },
        # There is 1 result in audio.
        'audio': {
            'Lala': {
                'eval': {
                    'file': {
                        'file_path': self.tmp_file,
                        'key': 'file_raw'
                    },
                },
                'expect': 'asdf'
            }
        },
        # There are 2 results in bar.
        'bar': {
            'bar_1': {
                'eval': 'shell:echo hello',
            },
            'bar_2': {
                'eval': 'shell:echo world',
            }
        }
    }
    statement_path = os.path.join(self.tmp_dir, 'statement.json')
    with open(statement_path, 'w') as f:
      json.dump(statement, f)

    # Output to file.
    output_file = os.path.join(self.tmp_dir, 'output_file.json')
    cmd = [CMD_PATH, '--output-file', output_file,
           'probe', '--config-file', statement_path]
    process_utils.CheckOutput(cmd)
    results = json_utils.LoadFile(output_file)
    self.assertProbedResultEquals(results, expected)

    # Output to stdout.
    cmd = [CMD_PATH, 'probe', '--config-file', statement_path]
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertProbedResultEquals(expected, results)

    cmd = [CMD_PATH, '--output-file', '-',
           'probe', '--config-file', statement_path]
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertProbedResultEquals(expected, results)


class EvalFunctionCmdTest(unittest.TestCase):
  def setUp(self):
    self.tmp_file = file_utils.CreateTemporaryFile()
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isfile(self.tmp_file):
      os.remove(self.tmp_file)
    if os.path.isdir(self.tmp_dir):
      shutil.rmtree(self.tmp_dir)

  def testNormal(self):
    with open(self.tmp_file, 'w') as f:
      f.write('FOO\nBAR\n')
    expected = [
        {'file_raw': 'FOO'},
        {'file_raw': 'BAR'}]

    # Output to file.
    output_file = os.path.join(self.tmp_dir, 'output_file.json')
    cmd = [CMD_PATH, '--output-file', output_file,
           'eval-function', 'file', self.tmp_file,
           '--key', 'file_raw', '--split-line']
    process_utils.CheckOutput(cmd)
    with open(output_file, 'r') as f:
      file_content = f.read()
      results = json.loads(file_content)
    self.assertEquals(results, expected)

    # Output to stdout.
    cmd = [CMD_PATH, '--output-file', '-',
           'eval-function', 'file', self.tmp_file,
           '--key', 'file_raw', '--split-line']
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertEquals(expected, results)

    cmd = [CMD_PATH, 'eval-function', 'file', self.tmp_file,
           '--key', 'file_raw', '--split-line']
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertEquals(expected, results)

  def testShellCommand(self):
    expected = [
        {'shell_raw': 'hello'}]
    cmd = [CMD_PATH, 'eval-function', 'shell', 'echo hello']
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertEquals(expected, results)


if __name__ == '__main__':
  unittest.main()
