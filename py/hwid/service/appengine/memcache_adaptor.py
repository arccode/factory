# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A connector to memcache that deals with the 1M data size limitiation."""

import cPickle
import logging

from six.moves import xrange

# pylint: disable=import-error, no-name-in-module
from google.appengine.api import memcache

PICKLE_PROTOCOL_VERSION = 2
MAX_NUMBER_CHUNKS = 10
# Chunksize has to be less than 1000000 bytes which is the max size for a
# memcache data entry.  Tweaking this number may improve/reduce performance.
MEMCACHE_CHUNKSIZE = 950000


class MemcacheAdaptorException(Exception):
  pass


class MemcacheAdaptor(object):
  """Memcache connector that can store objects larger than 1M.

  This connector will save items to the memcache by first serializing the object
  then breaking that serialized data up into chunks that are small enough to
  fit into memcache.

  You should not use this connector unless you are sure your data may be
  greater than 1M, breaking up the data adds a performance overhead.
  """

  def __init__(self, namespace=None):
    self.namespace = namespace

  def BreakIntoChunks(self, key, serialized_data):
    chunks = {}
    # Split serialized object into chunks no bigger than chunksize. The unique
    # key for the split chunks is <key>.<number> so the first chunk for key SNOW
    # will be SNOW.0 the second chunk will be in SNOW.1
    for i in xrange(0, len(serialized_data), MEMCACHE_CHUNKSIZE):
      chunk_key = '%s.%s' % (key, i // MEMCACHE_CHUNKSIZE)
      chunks[chunk_key] = serialized_data[i : i+MEMCACHE_CHUNKSIZE]
    return chunks

  def Put(self, key, value):
    """Store an object too large to fit directly into memcache."""
    serialized_value = cPickle.dumps(value, PICKLE_PROTOCOL_VERSION)

    chunks = self.BreakIntoChunks(key, serialized_value)
    if len(chunks) > MAX_NUMBER_CHUNKS:
      raise MemcacheAdaptorException('Object too large to store in memcache.')

    logging.debug('Memcache writing %s', key)
    memcache.set_multi(chunks, namespace=self.namespace)

  def AssembleFromChunks(self, chunks):
    chunks_in_order = []

    def _SortKeyByIndex(chunk_key):
      # The chunk_key format is 'PROJECT.INDEX', we should extract the index out
      # to do integer comparison.
      return int(chunk_key[chunk_key.find('.') + 1:])

    # They memcache keys returned are in no particular order so sort them.
    for key in sorted(chunks, key=_SortKeyByIndex):
      # We ask for more memcache keys than there are chunks so ignore any
      # empty memcache returns.
      if chunks[key]:
        chunks_in_order.append(chunks[key])
    return ''.join(chunks_in_order)

  def Get(self, key):
    """Retrieve and re-assemble a large object from memcache."""
    keys = ['%s.%s' % (key, i) for i in xrange(MAX_NUMBER_CHUNKS)]
    chunks = memcache.get_multi(keys, namespace=self.namespace)
    serialized_data = self.AssembleFromChunks(chunks)
    if not serialized_data:
      logging.debug('Memcache no data found %s', key)
      return None
    return cPickle.loads(serialized_data)
