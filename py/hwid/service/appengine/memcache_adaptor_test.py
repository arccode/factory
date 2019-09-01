#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for memcache_adaptor."""

import cPickle
import unittest

# pylint: disable=import-error, no-name-in-module
from google.appengine.api import memcache
import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import memcache_adaptor


class MemcacheAdaptorTest(unittest.TestCase):

  def setUp(self):
    super(MemcacheAdaptorTest, self).setUp()
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 950000
    memcache_adaptor.MAX_NUMBER_CHUNKS = 10

  def testBreakIntoChunks(self):
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 2
    serialized_data = 'aabb'
    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    chunks = adaptor.BreakIntoChunks('testkey', serialized_data)

    self.assertEqual(2, len(chunks))
    self.assertEqual('aa', chunks['testkey.0'])
    self.assertEqual('bb', chunks['testkey.1'])

  def testBreakIntoChunksNone(self):
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 2
    serialized_data = ''
    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    chunks = adaptor.BreakIntoChunks('testkey', serialized_data)

    self.assertEqual(0, len(chunks))

  @mock.patch.object(memcache, 'set_multi')
  @mock.patch.object(cPickle, 'dumps', return_value='aabb')
  def testPut(self, mock_pickle, mock_memcache_set):
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 4
    data = ['aa', 'bb']

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    adaptor.Put('testkey', data)

    mock_memcache_set.assert_called_once_with({'testkey.0': 'aabb'},
                                              namespace='testnamespace')
    mock_pickle.assert_called_once_with(
        ['aa', 'bb'], memcache_adaptor.PICKLE_PROTOCOL_VERSION)

  def testPutTooBig(self):
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 4
    memcache_adaptor.MAX_NUMBER_CHUNKS = 2
    data = ['aa', 'bb']

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    self.assertRaises(memcache_adaptor.MemcacheAdaptorException,
                      adaptor.Put, 'testkey', data)

  def testAssembleFromChunks(self):
    chunks = {
        'testkey.0': 'aa', 'testkey.1': 'bb', 'testkey.2': 'cc',
        'testkey.3': 'dd', 'testkey.4': 'ee', 'testkey.5': 'ff',
        'testkey.6': 'gg', 'testkey.7': 'hh', 'testkey.8': 'ii',
        'testkey.9': 'jj', 'testkey.10': 'kk', 'testkey.11': 'll',
        'testkey.12': None
    }

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    serialized_data = adaptor.AssembleFromChunks(chunks)

    self.assertEqual('aabbccddeeffgghhiijjkkll', serialized_data)

  @mock.patch.object(memcache, 'get_multi',
                     return_value={'testkey.1': 'zz', 'testkey.0': 'yy'})
  @mock.patch.object(cPickle, 'loads', return_value='pickle_return')
  def testGet(self, mock_pickle, mock_memcache_get):
    memcache_adaptor.MAX_NUMBER_CHUNKS = 2

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    value = adaptor.Get('testkey')

    mock_memcache_get.assert_called_once_with(['testkey.0', 'testkey.1'],
                                              namespace='testnamespace')
    mock_pickle.assert_called_once_with('yyzz')
    self.assertEqual('pickle_return', value)

  @mock.patch.object(memcache, 'set_multi')
  @mock.patch.object(memcache, 'get_multi')
  def testEnd2End(self, mock_memcache_get, mock_memcache_set):
    object_to_save = ['one', 'two', 'three']
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 8

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    adaptor.Put('testkey', object_to_save)
    mock_memcache_get.return_value = mock_memcache_set.call_args[0][0]
    retrieved_object = adaptor.Get('testkey')

    self.assertListEqual(object_to_save, retrieved_object)


if __name__ == '__main__':
  unittest.main()
