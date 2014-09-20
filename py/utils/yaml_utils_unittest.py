#!/bin/env python
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
import yaml

import factory_common # pylint: disable=W0611
from cros.factory.utils import yaml_utils


class BaseYAMLTagMetaclassUnittest(unittest.TestCase):
  def runTest(self):
    class FooTagMetaclass(yaml_utils.BaseYAMLTagMetaclass):
      YAML_TAG = '!foo'

      @classmethod
      def YAMLConstructor(mcs, loader, node):
        value = loader.construct_scalar(node)
        return FooTag(value)

      @classmethod
      def YAMLRepresenter(mcs, dumper, data):
        return dumper.represent_scalar(mcs.YAML_TAG, data.content)

    class FooTag(object):
      __metaclass__ = FooTagMetaclass

      def __init__(self, content):
        self.content = content

    # Test load YAML tag.
    value = yaml.load('!foo foo_bar')
    self.assertIsInstance(value, FooTag)
    self.assertEquals('foo_bar', value.content)

    # Test dump YAML tag.
    result = yaml.dump(value)
    self.assertEquals("!foo 'foo_bar'\n", result)


if __name__ == '__main__':
  unittest.main()
