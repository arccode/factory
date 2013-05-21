# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import logging
import pprint
import re
import struct
import uuid
import yaml


# The following YAML strings needs further handler. So far we just simply
# remove them. It works well now, while tuples are treated as lists, unicodes
# are treated as strings, objects are dropped.
# TODO(waihong): Use yaml.add_multi_constructor to handle them.
YAML_STR_BLACKLIST = (
    r'( !!python/tuple| !!python/unicode| !!python/object[A-Za-z_.:/]+)')


class EventBlob(object):
  """A structure to wrap the information returned from event log watcher.

  Properties:
    metadata: A dict to keep the metadata.
    chunk: A byte-list to store the orignal event data.
  """
  def __init__(self, metadata, chunk):
    self.metadata = metadata
    self.chunk = chunk


class EventStream(list):
  """Event Stream Structure.

  An EventStream is a list to store multiple non-preamble events, which share
  the same preamble event.

  Properties:
    metadata: A dict to keep the metadata.
    preamble: The dict of the preamble event.
  """
  def __init__(self, metadata):
    """Initializer.

    Args:
      yaml_str: The string contains multiple yaml-formatted events.
    """
    super(EventStream, self).__init__()
    self.metadata = metadata
    self.preamble = None


def GenerateEventStreamsFromYaml(metadata, yaml_str):
  """Generates EventStreams from multiple yaml-formatted events with delimiters.

  Args:
    metadata: A dict to keep the metadata.
    yaml_str: The string contains multiple yaml-formatted events.

  Yields:
    EventStream objects.
  """
  first = True
  stream = EventStream(metadata)
  # Some un-expected patterns appear in the log. Remove them.
  yaml_str = re.sub(YAML_STR_BLACKLIST, '', yaml_str)
  try:
    for event in yaml.safe_load_all(yaml_str):
      if not event:
        continue
      if 'EVENT' not in event:
        logging.warn('The event dict is invalid, no EVENT tag:\n%s.',
                     pprint.pformat(event))
        continue
      if event['EVENT'] == 'preamble':
        # Yeild the stream it just created when it meets a new preamble,
        # except the case of the first one.
        if not first:
          yield stream
          stream = EventStream(metadata)
        stream.preamble = event
      else:
        stream.append(event)
      first = False
  except yaml.YAMLError, e:
    logging.exception('Error on parsing the yaml string "%s": %s',
                      yaml_str, e)
  yield stream


class EventPacket(object):
  """Event Packet Structure.

  An EventPacket is a non-preamble event combined with its preamble. It is
  used as an argument to pass to the exporters.

  Properties:
    metadata: A dict to keep the metadata.
    preamble: The dict of the preamble event.
    event: The dict of the non-preamble event.
    _event_id: The event_id string.
  """
  def __init__(self, metadata, preamble, event):
    self.metadata = metadata
    self.preamble = preamble
    self.event = event
    self._event_id = None

  @staticmethod
  def FlattenAttr(attr):
    """Generator of flattened attributes.

    Args:
      attr: The attr dict/list which may contains multi-level dicts/lists.

    Yields:
      A tuple (path_str, leaf_value).
    """
    def _FlattenAttr(attr):
      if isinstance(attr, dict):
        for key, val in attr.iteritems():
          for path, leaf in _FlattenAttr(val):
            yield [key] + path, leaf
      elif isinstance(attr, list):
        for index, val in enumerate(attr):
          for path, leaf in _FlattenAttr(val):
            yield [str(index)] + path, leaf
      else:
        # The leaf node.
        yield [], attr

    # Join the path list using '.'.
    return (('.'.join(k), v) for k, v in _FlattenAttr(attr))

  def GetEventId(self):
    """Generates the unique ID for an event, the base64 of {reimage_id}{SEQ}."""
    if not self._event_id:
      reimage_id = (self.preamble.get('reimage_id') or
                    self.preamble.get('image_id'))
      reimage_id_bytes = uuid.UUID(reimage_id).bytes
      seq_bytes = struct.pack('>L', int(self.event.get('SEQ')))
      self._event_id = ''.join([base64.urlsafe_b64encode(s).rstrip('=')
          for s in [reimage_id_bytes, seq_bytes]])
    return self._event_id

  def FindAttrContainingKey(self, key):
    """Finds the attr in the event that contains the given key.

    Args:
      key: A string of key.

    Returns:
      The dict inside the event that contains the given key.
    """
    def _FindContainingDictForKey(deep_dict, key):
      if isinstance(deep_dict, dict):
        if key in deep_dict.iterkeys():
          # Found, return its parent.
          return deep_dict
        else:
          # Try its children.
          for val in deep_dict.itervalues():
            result = _FindContainingDictForKey(val, key)
            if result:
              return result
      elif isinstance(deep_dict, list):
        # Try its children.
        for val in deep_dict:
          result = _FindContainingDictForKey(val, key)
          if result:
            return result
      # Not found.
      return None

    return _FindContainingDictForKey(self.event, key)
