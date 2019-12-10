#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for memcache_adaptor."""

import pickle
import unittest

import mock
import redis

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
    self.assertEqual('aa', chunks['testnamespace:testkey.0'])
    self.assertEqual('bb', chunks['testnamespace:testkey.1'])

  def testBreakIntoChunksNone(self):
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 2
    serialized_data = ''
    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    chunks = adaptor.BreakIntoChunks('testkey', serialized_data)

    self.assertEqual(0, len(chunks))

  @mock.patch.object(redis.Redis, 'mset')
  @mock.patch.object(pickle, 'dumps', return_value='aabb')
  def testPut(self, mock_pickle, mock_redis_mset):
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 4
    data = ['aa', 'bb']

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    adaptor.Put('testkey', data)

    mock_redis_mset.assert_called_once_with({'testnamespace:testkey.0': 'aabb'})
    mock_pickle.assert_called_once_with(
        ['aa', 'bb'], memcache_adaptor.PICKLE_PROTOCOL_VERSION)

  def testPutTooBig(self):
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 4
    memcache_adaptor.MAX_NUMBER_CHUNKS = 2
    data = ['aa', 'bb']

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    self.assertRaises(memcache_adaptor.MemcacheAdaptorException,
                      adaptor.Put, 'testkey', data)

  @mock.patch.object(redis.Redis, 'mget',
                     return_value=['yy', 'zz'])
  @mock.patch.object(pickle, 'loads', return_value='pickle_return')
  def testGet(self, mock_pickle, mock_redis_mget):
    memcache_adaptor.MAX_NUMBER_CHUNKS = 2

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    value = adaptor.Get('testkey')

    mock_redis_mget.assert_called_once_with(['testnamespace:testkey.0',
                                             'testnamespace:testkey.1'])
    mock_pickle.assert_called_once_with('yyzz')
    self.assertEqual('pickle_return', value)

  @mock.patch.object(redis.Redis, 'mset')
  @mock.patch.object(redis.Redis, 'mget')
  def testEnd2End(self, mock_redis_mget, mock_redis_mset):
    object_to_save = ['one', 'two', 'three']
    memcache_adaptor.MEMCACHE_CHUNKSIZE = 8

    adaptor = memcache_adaptor.MemcacheAdaptor('testnamespace')
    adaptor.Put('testkey', object_to_save)
    arg = mock_redis_mset.call_args[0][0]

    # Return values sorted by key
    mock_redis_mget.return_value = list(map(arg.get, sorted(arg)))
    retrieved_object = adaptor.Get('testkey')

    self.assertListEqual(object_to_save, retrieved_object)


if __name__ == '__main__':
  unittest.main()
