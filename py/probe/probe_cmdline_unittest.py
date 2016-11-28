#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import json
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import process_utils
from cros.factory.probe import function
from cros.factory.probe import probe_cmdline
from cros.factory.utils.arg_utils import Arg


CMD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'probe_cmdline.py')


class ProbeStatementTest(unittest.TestCase):
  class MockFunction(function.Function):
    ARGS = [Arg('data', list, 'help message')]
    def Apply(self, data):
      return self.args.data

  def setUp(self):
    function.RegisterFunction('mock', self.MockFunction, force=True)

  def testNormal(self):
    results = probe_cmdline.ProbeStatement(
        {'mock': {'data': [{'foo': 'FOO1', 'bar': 'BAR1'},
                           {'foo': 'FOO2', 'bar': 'BAR2'}]}},
        {'foo': 'FOO1'})
    self.assertEquals(results, [{'foo': 'FOO1', 'bar': 'BAR1'}])


class ProbeCmdTest(unittest.TestCase):
  def setUp(self):
    self.tmp_fd, self.tmp_file = tempfile.mkstemp()
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isfile(self.tmp_file):
      os.close(self.tmp_fd)
      os.remove(self.tmp_file)
    if os.path.isdir(self.tmp_dir):
      shutil.rmtree(self.tmp_dir)

  def testNormal(self):
    with open(self.tmp_file, 'w') as f:
      f.write('asdf\n')
    expected = {
        'audio': {
            'Lala': [
                {'file_raw': 'asdf'}]}}
    statement = {
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
        }
    }
    statement_path = os.path.join(self.tmp_dir, 'statement.json')
    with open(statement_path, 'w') as f:
      json.dump(statement, f)

    # Output to file.
    output_file = os.path.join(self.tmp_dir, 'output_file.json')
    cmd = [CMD_PATH, '--output-json-file', output_file, 'probe', statement_path]
    process_utils.CheckOutput(cmd)
    with open(output_file, 'r') as f:
      file_content = f.read()
      results = json.loads(file_content)
    self.assertEquals(results, expected)

    # Output to stdout.
    cmd = [CMD_PATH, 'probe', statement_path]
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertEquals(expected, results)

    cmd = [CMD_PATH, '--output-json-file', '-', 'probe', statement_path]
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertEquals(expected, results)


class EvalFunctionCmdTest(unittest.TestCase):
  def setUp(self):
    self.tmp_fd, self.tmp_file = tempfile.mkstemp()
    self.tmp_dir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.isfile(self.tmp_file):
      os.close(self.tmp_fd)
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
    cmd = [CMD_PATH, '--output-json-file', output_file,
           'eval-function', 'file', self.tmp_file,
           '--key', 'file_raw', '--split-line']
    process_utils.CheckOutput(cmd)
    with open(output_file, 'r') as f:
      file_content = f.read()
      results = json.loads(file_content)
    self.assertEquals(results, expected)

    # Output to stdout.
    cmd = [CMD_PATH, '--output-json-file', '-',
           'eval-function', 'file', self.tmp_file,
           '--key', 'file_raw', '--split-line']
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertEquals(expected, results)

    cmd = [CMD_PATH, 'eval-function', 'file', self.tmp_file,
           '--key', 'file_raw', '--split-line']
    results = json.loads(process_utils.CheckOutput(cmd))
    self.assertEquals(expected, results)


if __name__ == '__main__':
  unittest.main()
