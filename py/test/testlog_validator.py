# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Various validate function for FIELDS in testlog's Event-like object."""

import datetime
import pprint
import logging

import factory_common  # pylint: disable=W0611
from cros.factory.test import testlog_utils


class Validator(object):
  """Wrapper for functions that assign and validate values to Event object."""
  @staticmethod
  def Object(inst, key, value):
    # pylint: disable=W0212
    inst._data[key] = value

  @staticmethod
  def Long(inst, key, value):
    if not isinstance(value, (int, long)):
      raise ValueError(
          'key[%s] accepts type of int or long. Not %r '
          'Please convert before assign' % (key, type(value)))
    Validator.Object(inst, key, value)

  @staticmethod
  def Float(inst, key, value):
    if not isinstance(value, float):
      raise ValueError(
          'key[%s] accepts type of float. Not %r '
          'Please convert before assign' % (key, type(value)))
    Validator.Object(inst, key, value)

  @staticmethod
  def String(inst, key, value):
    if not isinstance(value, basestring):
      raise ValueError(
          'key[%s] accepts type of basestring. Not %r '
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
  def Dict(inst, key, value):
    """Inserts an item into the inst._data[key].

    Assuming inst._data[key] is a dictionary, the inserted element will be
    inst_data[key][value['key']] = value['value'].
    """
    logging.debug('Validator.Dict called with (%s, %s)', key, value)
    if not 'key' in value or not 'value' in value or len(value.items()) != 2:
      raise ValueError(
          'Validator.Dict accepts value in form of {%r:..., %r:...}, not %s' % (
              'key', 'value', pprint.pformat(value)))

    # pylint: disable=W0212
    updated_dict = inst._data[key] if key in inst._data else dict()
    sub_key = value['key']
    if sub_key in updated_dict:
      raise ValueError(
          '%s in duplicated for field %s' % (sub_key, key))
    updated_dict[sub_key] = value['value']
    # TODO(itspeter): Check if anything left in value.
    # pylint: disable=W0212
    inst._data[key] = updated_dict

  @staticmethod
  def List(inst, key, value):
    logging.debug('Validator.List called with (%s, %s)', key, value)
    # pylint: disable=W0212
    updated_list = inst._data[key] if key in inst._data else list()
    updated_list.append(value)
    # pylint: disable=W0212
    inst._data[key] = updated_list

  @staticmethod
  def Time(inst, key, value):
    """Converts value into datetime object.

    The datetime object is expected to converts to ISO8601 format at the
    time that it convert to JSON string.
    """
    logging.debug('Validator.Time called with (%s, %s)', key, value)
    if isinstance(value, basestring):
      d = testlog_utils.FromJSONDateTime(value)
    elif isinstance(value, datetime.datetime):
      d = value
    else:
      raise ValueError('Invalid `time` (%r) for Validator.Time' % value)
    # Round precision of microseconds to ensure equivalence after converting
    # to JSON and back again.
    d = d.replace(microsecond=(d.microsecond / 1000 * 1000))
    Validator.Object(inst, key, d)

  @staticmethod
  def Attachment(inst, key, value):
    del inst, key, value
    logging.debug('AttachmentValidator called: %s, %s', key, value)
    # TODO(itspeter): Implement it.
    raise NotImplementedError

  @staticmethod
  def Status(inst, key, value):
    if value not in inst.STATUS:
      raise ValueError('Invalid status : %r' % value)
    Validator.Object(inst, key, value)
