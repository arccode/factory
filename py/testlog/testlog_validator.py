# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Various validation functions for FIELDS in testlog's Event-like object."""

import logging
import os
import pprint
import re
import shutil

from .utils import time_utils


class Validator:
  """Wrapper for functions that assign and validate values to Event object."""
  @staticmethod
  def Object(inst, key, value):
    # pylint: disable=protected-access
    inst._data[key] = value

  @staticmethod
  def Long(inst, key, value):
    if not isinstance(value, int):
      raise ValueError(
          'key[%s] accepts type of int or long. Not %r '
          'Please convert before assign' % (key, type(value)))
    Validator.Object(inst, key, value)

  @staticmethod
  def Number(inst, key, value):
    if isinstance(value, int):
      value = float(value)
    if not isinstance(value, float):
      raise ValueError(
          'key[%s] accepts type of float. Not %r '
          'Please convert before assign' % (key, type(value)))
    Validator.Object(inst, key, value)

  @staticmethod
  def String(inst, key, value):
    if not isinstance(value, str):
      raise ValueError(
          'key[%s] accepts type of str. Not %r '
          'Please convert before assign' % (key, type(value)))
    Validator.Object(inst, key, value)

  @staticmethod
  def Boolean(inst, key, value):
    if not isinstance(value, bool):
      raise ValueError(
          'key[%s] accepts type of bool. Not %r '
          'Please convert before assign' % (key, type(value)))
    Validator.Object(inst, key, value)

  @staticmethod
  def Dict(inst, key, value, schema=None):
    """Inserts an item into the inst._data[key].

    Assuming inst._data[key] is a dictionary, the inserted element will be
    inst_data[key][value['key']] = value['value'].
    """
    logging.debug('Validator.Dict called with (%s, %s)', key, value)
    if not 'key' in value or not 'value' in value or len(value.items()) != 2:
      raise ValueError(
          'Validator.Dict accepts value in form of {%r:..., %r:...}, not %s' % (
              'key', 'value', pprint.pformat(value)))

    if not isinstance(value['key'], str):
      raise ValueError(
          'The key of %s accepts type of str. Not %r '
          'Please convert before assign' % (key, type(value['key'])))

    if schema:
      schema.Validate(value['value'])

    # pylint: disable=protected-access
    updated_dict = inst._data[key] if key in inst._data else {}
    sub_key = value['key']
    if sub_key in updated_dict:
      raise ValueError(
          '%r is duplicated for field %s' % (sub_key, key))
    updated_dict[sub_key] = value['value']
    # TODO(itspeter): Check if anything left in value.
    # pylint: disable=protected-access
    inst._data[key] = updated_dict

  @staticmethod
  def List(inst, key, value, schema=None):
    logging.debug('Validator.List called with (%s, %s)', key, value)

    if schema:
      schema.Validate(value)

    # pylint: disable=protected-access
    updated_list = inst._data[key] if key in inst._data else []
    updated_list.append(value)
    # pylint: disable=protected-access
    inst._data[key] = updated_list

  @staticmethod
  def Attachment(inst, key, value, delete, testlog_getter_fn):
    del inst  # Unused.
    logging.debug('Validator.Attachment is called: (key=%s, value=%s, '
                  'delete=%s)', key, value, delete)
    # TODO(itspeter): Move constants to a better place.
    PATH = 'path'
    MIME_TYPE = 'mimeType'

    # Verify required fields
    # TODO(itspeter): Figure out a long-term approach to avoid attchments
    #                 are processed twice (one on API call, one on
    #                 testlog.Collect.

    source_path = value[PATH]
    if not source_path:
      raise ValueError('path field cannot be found')
    # Check if source_path exists
    # TODO(itspeter): Consider doing a lsof sanity check.
    if not os.path.exists(source_path):
      raise ValueError('not able to find file %s' % source_path)
    mime_type = value[MIME_TYPE]
    if not isinstance(mime_type, str) or (
        not re.match(r'^[-\+\w]+/[-\+\w]+$', mime_type)):
      raise ValueError('mimeType(%r) is incorrect for file %s' % (
          mime_type, source_path))

    # Move the attachment file.
    folder = testlog_getter_fn().attachments_folder

    # First try with the attachment name.
    ideal_target_name = key
    target_path = os.path.join(folder, ideal_target_name)
    if os.path.exists(target_path):
      target_path = None
      for unused_i in range(5):  # Try at most 5 times of adding a random UUID.
        uuid_target_path = os.path.join(folder, '%s_%s' % (
            time_utils.TimedUUID()[-12:], ideal_target_name))
        if not os.path.exists(uuid_target_path):
          target_path = uuid_target_path
          break
      if target_path is None:
        raise ValueError(
            'Try to get a lottery for yourself, with about a probability '
            'of %s, %s failed to find its way home' % (
                (1.0 / 16) ** 12, source_path))
    if delete:
      shutil.move(source_path, target_path)
    else:
      shutil.copy(source_path, target_path)
    value[PATH] = target_path
    # TODO(itspeter): Check if anything left in value.

  @staticmethod
  def Status(inst, key, value):
    if value not in inst.STATUS:
      raise ValueError('Invalid status : %r' % value)
    Validator.Object(inst, key, value)
