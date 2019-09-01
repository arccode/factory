#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re
import tempfile
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.probe.lib import cached_probe_function
from cros.factory.utils import file_utils


class CachedProbeFunctionTest(unittest.TestCase):
  def setUp(self):
    self.probed_results = {
        'i1': {'k1': 'v1'}, 'i2': [{'k2': 'v21'}, {'k2': 'v22'}]}

    # pylint: disable=abstract-method
    class _SimpleCachedProbeFunction(cached_probe_function.CachedProbeFunction):
      called = False

      def __init__(self):
        super(_SimpleCachedProbeFunction, self).__init__()
        self.GetCategoryFromArgs = mock.MagicMock()

      @classmethod
      def ProbeAllDevices(cls):
        self.assertFalse(cls.called)
        cls.called = True
        return self.probed_results

    self.func = _SimpleCachedProbeFunction()

  def testNoCategory(self):
    self.func.GetCategoryFromArgs.return_value = None

    result = self.func()
    self.assertEquals(
        sorted(result), sorted([{'k1': 'v1'}, {'k2': 'v21'}, {'k2': 'v22'}]))
    self.assertEquals(result, self.func())

  def testWithCategory(self):
    self.func.GetCategoryFromArgs.return_value = 'i1'

    result = self.func()
    self.assertEquals(result, [{'k1': 'v1'}])
    self.assertEquals(result, self.func())

  def testInvalidCategory(self):
    self.func.GetCategoryFromArgs.side_effect = (
        cached_probe_function.InvalidCategoryError())

    self.assertEquals(self.func(), [])

  def testProbedResultsNoCategory(self):
    self.probed_results = [{'aa': 'bb'}, {'cc': 'dd'}]
    self.func.GetCategoryFromArgs.return_value = None

    self.assertEquals(sorted(self.func()), sorted([{'aa': 'bb'}, {'cc': 'dd'}]))


class LazyCachedProbeFunctionTest(unittest.TestCase):
  def setUp(self):
    self.probed_results = {
        'i1': {'k1': 'v1'}, 'i2': [{'k2': 'v21'}, {'k2': 'v22'}]}

    # pylint: disable=abstract-method
    class _Function(cached_probe_function.LazyCachedProbeFunction):
      called = set()

      def __init__(self):
        super(_Function, self).__init__()
        self.GetCategoryFromArgs = mock.MagicMock()

      @classmethod
      def ProbeDevices(cls, category):
        self.assertNotIn(category, cls.called)
        cls.called.add(category)
        return self.probed_results[category]

    self.func = _Function()

  def testNormal(self):
    self.func.GetCategoryFromArgs.return_value = 'i1'
    result = self.func()
    self.assertEquals(result, [{'k1': 'v1'}])
    self.assertEquals(result, self.func())
    self.assertEquals(self.func.called, {'i1'})

    self.func.GetCategoryFromArgs.return_value = 'i2'
    result = self.func()
    self.assertEquals(result, [{'k2': 'v21'}, {'k2': 'v22'}])
    self.assertEquals(result, self.func())
    self.assertEquals(self.func.called, {'i1', 'i2'})

  def testInvalidCategory(self):
    self.func.GetCategoryFromArgs.side_effect = (
        cached_probe_function.InvalidCategoryError())

    self.assertEquals(self.func(), [])

  def testProbeFailed(self):
    self.func.GetCategoryFromArgs.return_value = 'i999'

    self.assertEquals(self.func(), [])


class GlobPathCachedProbeFunctionTest(unittest.TestCase):
  def setUp(self):
    self.root_dir = tempfile.mkdtemp()
    file_utils.TryMakeDirs(os.path.join(self.root_dir, 'dev1'))
    file_utils.TryMakeDirs(os.path.join(self.root_dir, 'dev2'))
    file_utils.TryMakeDirs(os.path.join(self.root_dir, 'devX'))
    file_utils.TryMakeDirs(os.path.join(self.root_dir, 'real_dev_6'))
    file_utils.ForceSymlink(os.path.join(self.root_dir, 'real_dev_6'),
                            os.path.join(self.root_dir, 'dev6'))
    file_utils.TryMakeDirs(os.path.join(self.root_dir, 'dev_raise_exception'))

    class Function(cached_probe_function.GlobPathCachedProbeFunction):
      GLOB_PATH = os.path.join(self.root_dir, 'dev*')

      @classmethod
      def ProbeDevice(cls, dir_path):
        name = os.path.basename(dir_path)
        if name == 'dev_raise_exception':
          raise Exception()
        if re.match(r'^dev[0-9]+$', name):
          return {'name': os.path.basename(os.path.realpath(dir_path))}

    self.Function = Function

  def testNoDirPath(self):
    func = self.Function()

    result = func()
    self.assertItemsEqual(
        result, self._GenerateExpectedProbedResults(['dev1', 'dev2', 'dev6']))

  def testInvalidDirPath(self):
    func = self.Function(dir_path='aabbcc')

    self.assertEquals(func(), [])

  def testWithDirPath(self):
    func = self.Function(dir_path=os.path.join(self.root_dir, 'dev1'))
    result = func()
    self.assertEquals(result, self._GenerateExpectedProbedResults(['dev1']))

    # Symlink should be resolved.
    func = self.Function(dir_path=os.path.join(self.root_dir, 'dev6'))
    result = func()
    self.assertEquals(result, self._GenerateExpectedProbedResults(['dev6']))

    func = self.Function(dir_path=os.path.join(self.root_dir, 'real_dev_6'))
    result = func()
    self.assertEquals(result, self._GenerateExpectedProbedResults(['dev6']))

  def _GenerateExpectedProbedResults(self, names):
    ret = []
    for name in names:
      path = os.path.join(self.root_dir, name)
      ret.append({'name': os.path.basename(os.path.realpath(path)),
                  'device_path': path})
    return ret


if __name__ == '__main__':
  unittest.main()
