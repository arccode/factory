#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Format a JSON test list."""

import argparse
import collections
import json
import sys


def ReorderDictKey(obj, key_order=None):
  if key_order is None:
    key_order = lambda x: x

  if callable(key_order):
    key_order = list(sorted(obj.iterkeys(), key=key_order))
  elif not all(k in key_order for k in obj):
    raise ValueError('Some keys of %r is not inside order %r.' % (obj,
                                                                  key_order))

  return collections.OrderedDict((k, obj[k]) for k in key_order if k in obj)


def ReorderDictKeyInObject(obj, path, key_order=None):
  paths = path.split('.')
  last = paths.pop()

  for p in paths:
    if p not in obj:
      return
    obj = obj[p]

  if last in obj:
    obj[last] = ReorderDictKey(obj[last], key_order)


_COMMENT_PREFIX = '__comment_'


def ConstantOrder(constant):
  if constant.startswith(_COMMENT_PREFIX):
    return (constant[len(_COMMENT_PREFIX):], 1)
  return (constant, 0)


_TEST_OBJECT_KEY_ORDER = [
    '__replace__', '__delete__', 'inherit', 'pytest_name', 'id', 'label',
    'teardown', 'run_if', 'exclusive_resources', 'disable_services',
    'enable_services', 'allow_reboot', 'parallel', 'layout', 'iterations',
    'retries', 'action_on_failure', 'child_action_on_failure', 'disable_abort',
    'require_run', '__comment', 'locals', 'subtests', 'args'
]


def RecursiveFormatTestObject(test_obj):
  if isinstance(test_obj, basestring):
    return test_obj

  test_obj = ReorderDictKey(test_obj, _TEST_OBJECT_KEY_ORDER)
  if 'subtests' in test_obj:
    test_obj['subtests'] = [
        RecursiveFormatTestObject(v) for v in test_obj['subtests']
    ]
  return test_obj


def Format(test_list):
  test_list = ReorderDictKey(
      test_list,
      key_order=[
          '__comment', 'inherit', 'label', 'constants', 'options',
          'definitions', 'tests', 'override_args'
      ])
  ReorderDictKeyInObject(test_list, 'options')
  ReorderDictKeyInObject(test_list, 'constants', key_order=ConstantOrder)
  ReorderDictKeyInObject(test_list, 'definitions')
  if 'definitions' in test_list:
    test_list['definitions'] = collections.OrderedDict(
        (k, RecursiveFormatTestObject(v))
        for k, v in test_list['definitions'].iteritems())
  if 'tests' in test_list:
    test_list['tests'] = [
        RecursiveFormatTestObject(test_obj) for test_obj in test_list['tests']
    ]
  ReorderDictKeyInObject(test_list, 'override_args')
  return test_list


def main():
  parser = argparse.ArgumentParser(description='Format a JSON test list.')
  parser.add_argument(
      '-i', '--inplace', dest='inplace', action='store_true',
      help='Update the JSON test list inplace.')
  parser.add_argument('test_list', help='The test list to be formatted.')
  options = parser.parse_args()

  with open(options.test_list, 'r') as fp:
    input_test_list = json.load(fp, object_pairs_hook=collections.OrderedDict)

  output_test_list = Format(input_test_list)

  def _WriteTestList(fp, test_list):
    json.dump(
        test_list, fp, indent=2, separators=(',', ': '), ensure_ascii=True)
    fp.write('\n')

  if options.inplace:
    with open(options.test_list, 'w') as fp:
      _WriteTestList(fp, output_test_list)
  else:
    _WriteTestList(sys.stdout, output_test_list)


if __name__ == '__main__':
  main()
