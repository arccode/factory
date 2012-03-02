# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import inspect
import logging
import os
import yaml


class InvalidDataError(ValueError):
  """Error in (en/de)coding or validating data."""
  pass


class _DatastoreClass(object):

  def __init__(self, **field_dict):
    """Creates object using the field data specified in field_dict."""
    self.__dict__.update(field_dict)

  def Yrepr(self, yaml_representer):
    """The object YAML representation is just its field_dict data."""
    return yaml_representer.represent_data(self.__dict__)

  def Encode(self):
    """Return the YAML string for this object and check its schema.

    After generating the output data, run decode on that to validate.
    """
    yaml_data = yaml.dump(self, default_flow_style=False)
    self.Decode(yaml_data)
    return yaml_data

  @classmethod
  def Decode(c, data):
    """Given YAML string, creates corresponding object and check its schema."""
    def NestedDecode(elt_type, elt_data):
      """Apply appropriate constructors to nested object data."""
      if isinstance(elt_type, tuple):
        collection_type, field_type = elt_type
        if collection_type is dict:
          return dict((field_key, NestedDecode(field_type, field))
                      for field_key, field in elt_data.items())
        if collection_type is list:
          return [NestedDecode(field_type, field) for field in elt_data]
      elif issubclass(elt_type, _DatastoreClass):
        return elt_type(**elt_data)
      return elt_data
    try:
      field_dict = yaml.safe_load(data)
    except yaml.YAMLError, e:
      raise InvalidDataError("YAML deserialization error: %s" % e)
    c.ValidateSchema(field_dict)
    cooked_field_dict = dict(
        (elt_key, NestedDecode(elt_type, field_dict[elt_key]))
        for elt_key, elt_type in c._schema.items())
    return c(**cooked_field_dict)

  @classmethod
  def ValidateSchema(c, field_dict):
    """Ensures the layout of field_dict matches the class schema specification.

    This should be run before data is coerced into objects.  When the
    schema indicates an object class type, the corresponding schema
    for that class is applied to the corresponding subset of field
    data.  Long story short, field_dict should not contain any
    objects.

    Args:
      field_dict: Data which must have layout and type matching schema.
    """
    def ValidateCollection(top_level_tag, collection_type_data,
                           collection_data):
      if len(collection_type_data) != 2:
        raise InvalidDataError(
            '%r schema contains bad type definiton for element %r, ' %
            (c.__name__, top_level_tag) +
            'expected (collection type, field type) tuple, '
            'found %s' % repr(collection_type_data))
      collection_type, field_type = collection_type_data
      if collection_type not in [dict, list]:
        raise InvalidDataError(
            '%r schema element %r has illegal collection type %r ' %
            (c.__name__, top_level_tag, collection_type.__name__) +
            '(only "dict" and "list" are supported)')
      if not isinstance(collection_data, collection_type):
        raise InvalidDataError(
            '%r schema validation failed for element %r, ' %
            (c.__name__, top_level_tag) +
            'expected type %r, found %r' %
            (collection_type.__name__, type(collection_data).__name__))
      if collection_type is dict:
        for field_key, field_data in collection_data.items():
          if not (isinstance(field_key, str) or isinstance(field_key, int)):
            raise InvalidDataError(
                '%r schema validation failed for element %r, ' %
                (c.__name__, top_level_tag) +
                'dict key must be "str" or "int", found %r' %
                (type(field_key).__name__))
          ValidateField(top_level_tag, field_type, field_data)
      elif collection_type is list:
        for field_data in collection_data:
          ValidateField(top_level_tag, field_type, field_data)
    def ValidateField(top_level_tag, field_type, field_data):
      if isinstance(field_type, tuple):
        ValidateCollection(top_level_tag, field_type, field_data)
      elif issubclass(field_type, _DatastoreClass):
        field_type.ValidateSchema(field_data)
      else:
        if not isinstance(field_data, field_type):
          raise InvalidDataError(
              '%r schema validation failed for element %r, ' %
              (c.__name__, top_level_tag) +
              'expected type %r, found %r' %
              (field_type.__name__, type(field_data).__name__))
    if (set(c._schema) ^ set(field_dict)):
      raise InvalidDataError(
          '%r schema and data dict keys do not match, ' % c.__name__ +
          'data is missing keys: %r, ' %
          sorted(set(c._schema) - set(field_dict)) +
          'data has extra keys: %r' % sorted(set(field_dict) - set(c._schema)))
    for top_level_tag, field_type in c._schema.items():
      ValidateField(top_level_tag, field_type, field_dict[top_level_tag])


def MakeDatastoreSubclass(subclass_name, subclass_schema):
  """Define storable object type with a schema and yaml representer.

  The new object is defined in the module scope of the calling
  function.  The yaml representer is added so that yaml calls the
  appropriate Yrepr function for the object, instead of the generic
  tagged python object format.

  Args:
    subclass_name: Name of the class to be defined.
    subclass_schema: A dict describing the subclass schema, which will
      be enforced whenever the subclass data is written to the backing
      store.  The dict must contain a key for each data field, and the
      corresponding value is the type of that field ; value types can
      be singleton python types, or they can be 2-tuples.  For tuples,
      the lhs must be either dict or list, and the rhs can be either a
      singleton or recursively another tuple.  The keys for dicts are
      implicitly enforced to always be of type str.  There must be a
      field called 'name', which is used as an index by the backing
      store.
  Returns:
    Nothing.
  """
  subclass = type(subclass_name, (_DatastoreClass,), {})
  caller_module = inspect.getmodule((inspect.stack()[1])[0])
  setattr(caller_module, subclass_name, subclass)
  subclass._schema = subclass_schema
  yaml.add_representer(subclass, lambda yaml_repr, obj: obj.Yrepr(yaml_repr))
