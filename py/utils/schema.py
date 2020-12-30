# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=protected-access,redefined-builtin

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

from .type_utils import MakeList

# To simplify portability issues, validating JSON schema is optional.
try:
  # pylint: disable=wrong-import-order
  import jsonschema
  _HAVE_JSONSCHEMA = True
except ImportError:
  _HAVE_JSONSCHEMA = False


class SchemaException(Exception):
  pass


class BaseType:
  """Base type class for schema classes.
  """

  def __init__(self, label):
    self.label = label

  def __repr__(self):
    return 'BaseType(%r)' % self.label

  def Validate(self, data):
    raise NotImplementedError


class Scalar(BaseType):
  """Scalar schema class.

  Attributes:
    label: A human-readable string to describe this Scalar.
    element_type: The Python type of this Scalar. Cannot be a iterable type.
    choices: A set of allowable choices for the scalar, or None to allow
        any values of the given type.

  Raises:
    SchemaException if argument format is incorrect.
  """

  def __init__(self, label, element_type, choices=None):
    super(Scalar, self).__init__(label)
    if getattr(element_type, '__iter__', None) and element_type not in (
        str, bytes):
      raise SchemaException(
          'element_type %r of Scalar %r is not a scalar type' % (element_type,
                                                                 label))
    self.element_type = element_type
    self.choices = set(choices) if choices else set()

  def __repr__(self):
    return 'Scalar(%r, %r%s)' % (
        self.label, self.element_type,
        ', choices=%r' % sorted(self.choices) if self.choices else '')

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
    if not isinstance(data, self.element_type):
      raise SchemaException('Type mismatch on %r: expected %r, got %r' %
                            (data, self.element_type, type(data)))
    if self.choices and data not in self.choices:
      raise SchemaException('Value mismatch on %r: expected one of %r' %
                            (data, sorted(self.choices)))


class RegexpStr(Scalar):
  """Schema class for a string which matches the specific regular expression.

  Attributes:
    label: A human-readable string to describe this Scalar.
    regexp: A regular expression object to match.

  Raises:
    SchemaException if argument format is incorrect.
  """

  def __init__(self, label, regexp):
    super(RegexpStr, self).__init__(label, str)
    self.regexp = regexp

  def __repr__(self):
    return 'RegexpStr(%r, %s)' % (self.label, self.regexp.pattern)

  def __deepcopy__(self, memo):
    return RegexpStr(self.label, self.regexp)

  def Validate(self, data):
    """Validates the given data against the RegexpStr schema.

    It first checks if the data's type is `str`.  Then, it checks if the
    value matches the regular expression.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    super(RegexpStr, self).Validate(data)
    if not self.regexp.match(data):
      raise SchemaException("Value %r doesn't match regeular expression %s" %
                            (data, self.regexp.pattern))


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
    min_size: The minimum size of the elements, default to 0.
    max_size: None or the maximum size of the elements.

  Raises:
    SchemaException if argument format is incorrect.
  """

  def __init__(self, label, key_type, value_type, min_size=0, max_size=None):
    super(Dict, self).__init__(label)
    if not (isinstance(key_type, Scalar) or
            (isinstance(key_type, AnyOf) and
             key_type.CheckTypeOfPossibleValues(Scalar))):
      raise SchemaException('key_type %r of Dict %r is not Scalar' %
                            (key_type, self.label))
    self.key_type = key_type
    if not isinstance(value_type, BaseType):
      raise SchemaException('value_type %r of Dict %r is not Schema object' %
                            (value_type, self.label))
    self.value_type = value_type
    self.min_size = min_size
    self.max_size = max_size

  def __repr__(self):
    size_expr = '[%d, %s]' % (self.min_size, ('inf' if self.max_size is None
                                              else '%d' % self.max_size))
    return 'Dict(%r, key_type=%r, value_type=%r, size=%s)' % (
        self.label, self.key_type, self.value_type, size_expr)

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
                            (self.label, type(data)))

    if len(data) < self.min_size:
      raise SchemaException('Size mismatch on %r: expected size >= %r' %
                            (self.label, self.min_size))

    if self.max_size is not None and self.max_size < len(data):
      raise SchemaException('Size mismatch on %r: expected size <= %r' %
                            (self.label, self.max_size))

    for k, v in data.items():
      self.key_type.Validate(k)
      self.value_type.Validate(v)


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
    allow_undefined_keys: A boolean that indicates whether additional items
        that is not recorded in both `items` and `optional_items` are allowed
        or not.

  Raises:
    SchemaException if argument format is incorrect.
  """

  def __init__(self, label, items=None, optional_items=None,
               allow_undefined_keys=False):
    super(FixedDict, self).__init__(label)
    if items and not isinstance(items, dict):
      raise SchemaException('items of FixedDict %r should be a dict' %
                            self.label)
    self.items = copy.deepcopy(items) if items is not None else {}
    if optional_items and not isinstance(optional_items, dict):
      raise SchemaException('optional_items of FixedDict %r should be a dict' %
                            self.label)
    self.optional_items = (
        copy.deepcopy(optional_items) if optional_items is not None else {})
    self.allow_undefined_keys = allow_undefined_keys

  def __repr__(self):
    return 'FixedDict(%r, items=%r, optional_items=%r)' % (self.label,
                                                           self.items,
                                                           self.optional_items)

  def Validate(self, data):
    """Validates the given data and all its key-value pairs against the Dict
    schema.

    If a key of Dict's type is required, then it must exist in the data's keys.
    If `self.allow_undefined_keys` is `False` and some items in the given data
    are not in either `self.items` or `self.optional_items`, the method will
    raise `SchemaException`.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, dict):
      raise SchemaException('Type mismatch on %r: expected dict, got %r' %
                            (self.label, type(data)))
    data_key_list = list(data)
    # Check that every key-value pair in items exists in data
    for key, value_schema in self.items.items():
      if key not in data:
        raise SchemaException(
            'Required item %r does not exist in FixedDict %r' %
            (key, data))
      value_schema.Validate(data[key])
      data_key_list.remove(key)
    # Check that all the remaining unmatched key-value pairs matches any
    # definition in items or optional_items.
    for key, value_schema in self.optional_items.items():
      if key not in data:
        continue
      value_schema.Validate(data[key])
      data_key_list.remove(key)
    if not self.allow_undefined_keys and data_key_list:
      raise SchemaException('Keys %r are undefined in FixedDict %r' %
                            (data_key_list, self.label))


class JSONSchemaDict(BaseType):
  """JSON schema class.

  This schema class allows mixing JSON schema with other schema types.

  Attributes:
    label: A human-readable string to describe this JSON schema.
    schema: a JSON schema object.

  Raises:
    SchemaException if given schema is invalid (SchemaError) or fail
    to validate data using the schema (ValidationError).
  """
  def __init__(self, label, schema):
    super(JSONSchemaDict, self).__init__(label)
    self.label = label
    if _HAVE_JSONSCHEMA:
      try:
        jsonschema.Draft4Validator.check_schema(schema)
      except Exception as e:
        raise SchemaException('Schema %r is invalid: %r' % (schema, e))
    self.schema = schema

  def __repr__(self):
    return 'JSONSchemaDict(%r, %r)' % (self.label, self.schema)

  def Validate(self, data):
    if _HAVE_JSONSCHEMA:
      try:
        jsonschema.validate(data, self.schema)
      except Exception as e:
        raise SchemaException('Fail to validate %r with JSON schema %r: %r' %
                              (data, self.schema, e))

  def CreateOptional(self):
    """Creates a new schema that accepts null and itself."""
    return JSONSchemaDict(f'{self.label} or null',
                          {'anyOf': [
                              {
                                  'type': 'null'
                              },
                              self.schema,
                          ]})


class List(BaseType):
  """List schema class.

  Attributes:
    label: A string to describe this list.
    element_type: Optional schema object to validate the elements of the list.
        Default None means no validation of elements' type.
    min_length: The expected minimum length of the list.  Default to 0.
    max_length: None or the limit of the length.

  Raises:
    SchemaException if argument format is incorrect.
  """

  def __init__(self, label, element_type=None, min_length=0, max_length=None):
    super(List, self).__init__(label)
    if element_type and not isinstance(element_type, BaseType):
      raise SchemaException(
          'element_type %r of List %r is not a Schema object' %
          (element_type, self.label))
    self.element_type = copy.deepcopy(element_type)
    self.min_length = min_length
    self.max_length = max_length

  def __repr__(self):
    max_bound_repr = ('inf' if self.max_length is None
                      else '%d' % self.max_length)
    return 'List(%r, %r, [%r, %s])' % (
        self.label, self.element_type, self.min_length, max_bound_repr)

  def Validate(self, data):
    """Validates the given data and all its elements against the List schema.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, list):
      raise SchemaException('Type mismatch on %r: expected list, got %r' %
                            (self.label, type(data)))

    if len(data) < self.min_length:
      raise SchemaException('Length mismatch on %r: expected length >= %d' %
                            (self.label, self.min_length))

    if self.max_length is not None and self.max_length < len(data):
      raise SchemaException('Length mismatch on %r: expected length <= %d' %
                            (self.label, self.max_length))

    if self.element_type:
      for data_value in data:
        self.element_type.Validate(data_value)


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
          (element_types, self.label))
    self.element_types = copy.deepcopy(element_types)

  def __repr__(self):
    return 'Tuple(%r, %r)' % (self.label, self.element_types)

  def Validate(self, data):
    """Validates the given data and all its elements against the Tuple schema.

    Args:
      data: A Python data structure to be validated.

    Raises:
      SchemaException if validation fails.
    """
    if not isinstance(data, tuple):
      raise SchemaException('Type mismatch on %r: expected tuple, got %r' %
                            (self.label, type(data)))
    if self.element_types and len(self.element_types) != len(data):
      raise SchemaException(
          'Number of elements in tuple %r does not match that defined '
          'in Tuple schema %r' % (str(data), self.label))
    for content, element_type in zip(data, self.element_types):
      element_type.Validate(content)


class AnyOf(BaseType):
  """A Schema class which accepts any one of the given Schemas.

  Attributes:
    types: A list of Schema objects to be matched.
    label: An optional string to describe this AnyOf type.
  """

  def __init__(self, types, label=None):
    super(AnyOf, self).__init__(label)
    if (not isinstance(types, list) or
        not all([isinstance(x, BaseType) for x in types])):
      raise SchemaException(
          'types in AnyOf(types=%r%s) should be a list of Schemas' %
          (types, '' if label is None else ', label=%r' % label))
    self.types = list(types)

  def __repr__(self):
    label = '' if self.label is None else ', label=%r' % self.label
    return 'AnyOf(%r%s)' % (self.types, label)

  def CheckTypeOfPossibleValues(self, schema_type):
    """Checks if the acceptable types are of the same type as schema_type.

    Args:
      schema_type: The schema type to check against with.
    """
    return all([isinstance(k, schema_type) for k in self.types])

  def Validate(self, data):
    """Validates if the given data matches any schema in types

    Args:
      data: A Python data structue to be validated.

    Raises:
      SchemaException if no schemas in types validates the input data.
    """
    match = False
    for schema_type in self.types:
      try:
        schema_type.Validate(data)
      except SchemaException:
        continue
      match = True
      break
    if not match:
      raise SchemaException('%r does not match any type in %r' % (data,
                                                                  self.types))


class Optional(AnyOf):
  """A Schema class which accepts either None or given Schemas.

  It is a special case of AnyOf class: in addition of given schema(s), it also
  accepts None.

  Attributes:
    types: A (or a list of) Schema object(s) to be matched.
    label: An optional string to describe this Optional type.
  """

  def __init__(self, types, label=None):
    try:
      super(Optional, self).__init__(MakeList(types), label=label)
    except SchemaException:
      raise SchemaException(
          'types in Optional(types=%r%s) should be a Schema or a list of '
          'Schemas' % (types, '' if label is None else ', label=%r' % label))

  def __repr__(self):
    label = '' if self.label is None else ', label=%r' % self.label
    return 'Optional(%r%s)' % (self.types, label)

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
      raise SchemaException(
          '%r is not None and does not match any type in %r' % (data,
                                                                self.types))
