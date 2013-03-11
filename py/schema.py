#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=W0212, W0622

"""A function to create a schema tree from the given schema expression.

For example:

  1. This is the schema of the encoded_fields in component database.

    Dict('encoded_fields', Scalar('encoded_field', str),
      Dict('encoded_indices', Scalar('encoded_index', int),
        Dict('component_classes', Scalar('component_class', str),
          AnyOf('component_names', [
            Scalar('component_name', str),
            List('list_of_component_names', Scalar('component_name', str)),
            Scalar('none', type(None))
          ])
        )
      )
    )

  2. This is the schema of the pattern in component database.

    List('pattern',
        Dict('pattern_field', key_type=Scalar('encoded_index', str),
             value_type=Scalar('bit_offset', int))
    )

  3. This is the schema of the components in component database.

    Dict('components', Scalar('component_class', str),
      Dict('component_names', Scalar('component_name', str),
        FixedDict('component_attributes',
          items={
            'value': AnyOf('probed_value', [
              Scalar('probed_value', str),
              List('list_of_probed_values', Scalar('probed_value', str))
            ])
          },
          optional_items={
            'labels': List('list_of_labels', Scalar('label', str))
          }
        )
      )
    )
"""

import copy
import factory_common # pylint: disable=W0611

from cros.factory.common import MakeList


class SchemaException(Exception):
  pass


class BaseType(object):
  """Base type class for schema classes.
  """
  def __init__(self, label):
    self._label = label

  def Validate(self, data):
    raise NotImplementedError


class Scalar(BaseType):
  """Scalar schema class.

  Attributes:
    label: A human-readable string to describe this Scalar.
    element_type: The Python type of this Scalar. Cannot be a iterable type.

  Raises:
    SchemaException if argument format is incorrect.
  """
  def __init__(self, label, element_type):
    super(Scalar, self).__init__(label)
    if getattr(element_type, '__iter__', None):
      raise SchemaException('Scalar element type %r is iterable')
    self._element_type = element_type

  def Validate(self, data):
    """Validates the given data against the Scalar schema.

    It checks if the data's type matches the Scalar's element type. Also, it
    checks if the data's value matches the Scalar's value if the required value
    is specified.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, self._element_type):
      raise SchemaException('Type mismatch on %r: expected %r, got %r' %
                            (data, self._element_type, type(data)))


class Dict(BaseType):
  """Dict schema class.

  This schema class is used to verify simple dict. Only the key type and value
  type are validated.

  Attributes:
    label: A human-readable string to describe this Scalar.
    key_type: A schema object indicating the schema of the keys of this Dict. It
        can be a Scalar or an AnyOf with possible values being all Scalars.
    value_type: A schema object indicating the schema of the values of this
        Dict.

  Raises:
    SchemaException if argument format is incorrect.
  """
  def __init__(self, label, key_type, value_type):
    super(Dict, self).__init__(label)
    if not (isinstance(key_type, Scalar) or
           (isinstance(key_type, AnyOf) and
            key_type.CheckTypeOfPossibleValues(Scalar))):
      raise SchemaException('key_type %r of Dict %r is not Scalar' %
                            (key_type, self._label))
    self._key_type = key_type
    if not isinstance(value_type, BaseType):
      raise SchemaException('value_type %r of Dict %r is not Schema object' %
                            (value_type, self._label))
    self._value_type = value_type

  def Validate(self, data):
    """Validates the given data against the Dict schema.

    It checks that all the keys in data matches the schema defined by key_type,
    and all the values in data matches the schema defined by value_type.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, dict):
      raise SchemaException('Type mismatch on %r: expected dict, got %r' %
                            (self._label, type(data)))
    for k, v in data.iteritems():
      self._key_type.Validate(k)
      self._value_type.Validate(v)


class FixedDict(BaseType):
  """FixedDict schema class.

  FixedDict is a Dict with predefined allowed keys. And each key corresponds to
  a value type. The analogy of Dict vs. FixedDict can be Elements vs. Attribues
  in XML.

  An example FixedDict schema:
    FixedDict('foo',
              items={
                'a': Scalar('bar', str),
                'b': Scalar('buz', int)
              }, optional_items={
                'c': Scalar('boo', int)
              })

  Attributes:
    label: A human-readable string to describe this dict.
    items: A dict of required items that must be specified.
    optional_items: A dict of optional items.

  Raises:
    SchemaException if argument format is incorrect.
  """
  def __init__(self, label, items=None, optional_items=None):
    super(FixedDict, self).__init__(label)
    if items and not isinstance(items, dict):
      raise SchemaException('items of FixedDict %r should be a dict' %
                            self._label)
    self._items = copy.deepcopy(items) if items is not None else {}
    if optional_items and not isinstance(optional_items, dict):
      raise SchemaException('optional_items of FixedDict %r should be a dict' %
                            self._label)
    self._optional_items = (
        copy.deepcopy(optional_items) if optional_items is not None else {})

  def Validate(self, data):
    """Validates the given data and all its key-value pairs against the Dict
    schema.

    If a key of Dict's type is required, then it must exist in the data's keys.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, dict):
      raise SchemaException('Type mismatch on %r: expected dict, got %r' %
                            (self._label, type(data)))
    data_key_list = data.keys()
    # Check that every key-value pair in items exists in data
    for key, value_schema in self._items.iteritems():
      if key not in data:
        raise SchemaException(
            'Required item %r does not exist in FixedDict %r' %
            (key, data))
      value_schema.Validate(data[key])
      data_key_list.remove(key)
    # Check that all the remaining unmatched key-value pairs matches any
    # definition in items or optional_items.
    for key, value_schema in self._optional_items.iteritems():
      if key not in data:
        continue
      value_schema.Validate(data[key])
      data_key_list.remove(key)
    if data_key_list:
      raise SchemaException('Keys %r are undefined in FixedDict %r' %
                            (data_key_list, self._label))


class List(BaseType):
  """List schema class.

  Attributes:
    label: A string to describe this list.
    element_type: Optional schema object to describe the type of the List.

  Raises:
    SchemaException if argument format is incorrect.
  """
  def __init__(self, label, element_type=None):
    super(List, self).__init__(label)
    if element_type and not isinstance(element_type, BaseType):
      raise SchemaException(
          'element_type %r of List %r is not a Schema object' %
          (element_type, self._label))
    self._element_type = copy.deepcopy(element_type)

  def Validate(self, data):
    """Validates the given data and all its elements against the List schema.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, list):
      raise SchemaException('Type mismatch on %r: expected list, got %r' %
                             (self._label, type(data)))
    if self._element_type:
      for data_value in data:
        self._element_type.Validate(data_value)


class Tuple(BaseType):
  """Tuple schema class.

  Comparing to List, the Tuple schema makes sure that every element exactly
  matches the defined position and schema.

  Attributes:
    label: A string to describe this tuple.
    element_types: Optional list or tuple schema object to describe the
        types of the Tuple.

  Raises:
    SchemaException if argument format is incorrect.
  """
  def __init__(self, label, element_types=None):
    super(Tuple, self).__init__(label)
    if (element_types and
        (not isinstance(element_types, (tuple, list))) or
        (not all([isinstance(x, BaseType)] for x in element_types))):
      raise SchemaException(
          'element_types %r of Tuple %r is not a tuple or list' %
          (element_types, self._label))
    self._element_types = copy.deepcopy(element_types)

  def Validate(self, data):
    """Validates the given data and all its elements against the Tuple schema.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, tuple):
      raise SchemaException('Type mismatch on %r: expected tuple, got %r' %
                            (self._label, type(data)))
    if self._element_types and len(self._element_types) != len(data):
      raise SchemaException(
          'Number of elements in tuple %r does not match that defined '
          'in Tuple schema %r' % (str(data), self._label))
    for data, element_type in zip(data, self._element_types):
      element_type.Validate(data)


class AnyOf(BaseType):
  """A Schema class which accepts any one of the given Schemas.

  Attributes:
    label: A human-readable string to describe this object.
    type_list: A list of Schema objects to be matched.
  """
  def __init__(self, label, type_list):
    super(AnyOf, self).__init__(label)
    if (not isinstance(type_list, list) or
        not all([isinstance(x, BaseType) for x in type_list])):
      raise SchemaException(
          'type_list of AnyOf %r should be a list of Schema types' %
          self._label)
    self._type_list = type_list

  def CheckTypeOfPossibleValues(self, schema_type):
    """Checks if the acceptable types are of the same type as schema_type.

    Args:
      schema_type: The schema type to check against with.
    """
    return all([isinstance(k, schema_type) for k in self._type_list])

  def Validate(self, data):
    """Validates if the given data matches any schema in type_list

    Args:
      data: A Python data structue to be validated.

    Raises:
      SchemaException if no schemas in type_list validates the input data.
    """
    match = False
    for schema_type in self._type_list:
      try:
        schema_type.Validate(data)
      except SchemaException:
        continue
      match = True
      break
    if not match:
      raise SchemaException('%r does not match any type in %r' %
                            (data, self._label))


class Optional(AnyOf):
  """A Schema class which accepts either None or given Schemas.

  It is a special case of AnyOf class: in addition of given schema(s), it also
  accepts None.

  Attributes:
    label: A human-readable string to describe this object.
    types: A (a list of) Schema object(s) to be matched.
  """
  def __init__(self, label, types):
    super(Optional, self).__init__(label, MakeList(types))

  def Validate(self, data):
    """Validates if the given data is None or matches any schema in types.

    Args:
      data: A Python data structue to be validated.

    Raises:
      SchemaException if data is not None and no schemas in types validates the
      input data.
    """
    if data is None:
      return
    try:
      super(Optional, self).Validate(data)
    except SchemaException:
      raise SchemaException('%r is not None and does not match any type in %r' %
                            (data, self._label))
