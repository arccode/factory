# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A connector to memcache that deals with the 1M data size limitiation."""

import logging
import os
import pickle

import redis


PICKLE_PROTOCOL_VERSION = 2
MAX_NUMBER_CHUNKS = 10
# Chunksize has to be less than 1000000 bytes which is the max size for a
# memcache data entry.  Tweaking this number may improve/reduce performance.
MEMCACHE_CHUNKSIZE = 950000


class MemcacheAdapterException(Exception):
  pass


class MemcacheAdapter:
  """Memcache connector that can store objects larger than 1M.

  This connector will save items to the memcache by first serializing the object
  then breaking that serialized data up into chunks that are small enough to
  fit into memcache.

  You should not use this connector unless you are sure your data may be
  greater than 1M, breaking up the data adds a performance overhead.
  """

  def __init__(self, namespace=None):
    self.namespace = namespace
    redis_host = os.environ.get('REDIS_HOST', 'localhost')
    redis_port = int(os.environ.get('REDIS_PORT', 6379))
    self.client = redis.Redis(host=redis_host, port=redis_port,
                              health_check_interval=30)

  def ClearAll(self):
    """Clear all items in cache.

    This method is for testing purpose since each integration test should have
    empty cache in the beginning.
    """
    self.client.flushall()

  def BreakIntoChunks(self, key, serialized_data):
    chunks = {}
    # Split serialized object into chunks no bigger than chunksize. The unique
    # key for the split chunks is <key>.<number> so the first chunk for key SNOW
    # will be SNOW.0 the second chunk will be in SNOW.1
    for i in range(0, len(serialized_data), MEMCACHE_CHUNKSIZE):
      chunk_key = '%s.py3:%s.%s' % (self.namespace, key,
                                    i // MEMCACHE_CHUNKSIZE)
      chunks[chunk_key] = serialized_data[i : i+MEMCACHE_CHUNKSIZE]
    return chunks

  def Put(self, key, value):
    """Store an object too large to fit directly into memcache."""
    serialized_value = pickle.dumps(value, PICKLE_PROTOCOL_VERSION)

    chunks = self.BreakIntoChunks(key, serialized_value)
    if len(chunks) > MAX_NUMBER_CHUNKS:
      raise MemcacheAdapterException('Object too large to store in memcache.')

    logging.debug('Memcache writing %s', key)
    self.client.mset(chunks)

  def Get(self, key):
    """Retrieve and re-assemble a large object from memcache."""
    keys = ['%s.py3:%s.%s' % (self.namespace, key, i)
            for i in range(MAX_NUMBER_CHUNKS)]
    chunks = self.client.mget(keys)
    serialized_data = b''.join(filter(None, chunks))
    if not serialized_data:
      logging.debug('Memcache no data found %s', key)
      return None
    return pickle.loads(serialized_data)
