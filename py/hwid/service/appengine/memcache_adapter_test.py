#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for memcache_adapter."""

import pickle
import unittest
from unittest import mock

import redis

from cros.factory.hwid.service.appengine import memcache_adapter


class MemcacheAdapterTest(unittest.TestCase):

  def setUp(self):
    super(MemcacheAdapterTest, self).setUp()
    memcache_adapter.MEMCACHE_CHUNKSIZE = 950000
    memcache_adapter.MAX_NUMBER_CHUNKS = 10

  def testBreakIntoChunks(self):
    memcache_adapter.MEMCACHE_CHUNKSIZE = 2
    serialized_data = b'aabb'
    adapter = memcache_adapter.MemcacheAdapter('testnamespace')
    chunks = adapter.BreakIntoChunks('testkey', serialized_data)

    self.assertEqual(2, len(chunks))
    self.assertEqual(b'aa', chunks['testnamespace.py3:testkey.0'])
    self.assertEqual(b'bb', chunks['testnamespace.py3:testkey.1'])

  def testBreakIntoChunksNone(self):
    memcache_adapter.MEMCACHE_CHUNKSIZE = 2
    serialized_data = ''
    adapter = memcache_adapter.MemcacheAdapter('testnamespace')
    chunks = adapter.BreakIntoChunks('testkey', serialized_data)

    self.assertEqual(0, len(chunks))

  @mock.patch.object(redis.Redis, 'mset')
  @mock.patch.object(pickle, 'dumps', return_value=b'aabb')
  def testPut(self, mock_pickle, mock_redis_mset):
    memcache_adapter.MEMCACHE_CHUNKSIZE = 4
    data = ['aa', 'bb']

    adapter = memcache_adapter.MemcacheAdapter('testnamespace')
    adapter.Put('testkey', data)

    mock_redis_mset.assert_called_once_with({
        'testnamespace.py3:testkey.0': b'aabb'})
    mock_pickle.assert_called_once_with(
        ['aa', 'bb'], memcache_adapter.PICKLE_PROTOCOL_VERSION)

  def testPutTooBig(self):
    memcache_adapter.MEMCACHE_CHUNKSIZE = 4
    memcache_adapter.MAX_NUMBER_CHUNKS = 2
    data = ['aa', 'bb']

    adapter = memcache_adapter.MemcacheAdapter('testnamespace')
    self.assertRaises(memcache_adapter.MemcacheAdapterException,
                      adapter.Put, 'testkey', data)

  @mock.patch.object(redis.Redis, 'mget',
                     return_value=[b'yy', b'zz'])
  @mock.patch.object(pickle, 'loads', return_value='pickle_return')
  def testGet(self, mock_pickle, mock_redis_mget):
    memcache_adapter.MAX_NUMBER_CHUNKS = 2

    adapter = memcache_adapter.MemcacheAdapter('testnamespace')
    value = adapter.Get('testkey')

    mock_redis_mget.assert_called_once_with(['testnamespace.py3:testkey.0',
                                             'testnamespace.py3:testkey.1'])
    mock_pickle.assert_called_once_with(b'yyzz')
    self.assertEqual('pickle_return', value)

  @mock.patch.object(redis.Redis, 'mset')
  @mock.patch.object(redis.Redis, 'mget')
  def testEnd2End(self, mock_redis_mget, mock_redis_mset):
    object_to_save = ['one', 'two', 'three']
    memcache_adapter.MEMCACHE_CHUNKSIZE = 8

    adapter = memcache_adapter.MemcacheAdapter('testnamespace')
    adapter.Put('testkey', object_to_save)
    arg = mock_redis_mset.call_args[0][0]

    # Return values sorted by key
    mock_redis_mget.return_value = list(map(arg.get, sorted(arg)))
    retrieved_object = adapter.Get('testkey')

    self.assertListEqual(object_to_save, retrieved_object)


if __name__ == '__main__':
  unittest.main()
