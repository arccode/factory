# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import inspect
import logging
import os
import yaml


class _DatastoreClass(object):

  def __init__(self, **field_dict):
    """Creates object using the field data specified in field_dict."""
    self.__dict__.update(field_dict)

  def Yrepr(self, yaml_representer):
    """The object YAML representation is just its field_dict data."""
    return yaml_representer.represent_data(self.__dict__)

  def Encode(self):
    """Return the YAML string for this object and check its schema."""
    self.ValidateSchema(self.__dict__)
    return yaml.dump(self, default_flow_style=False)

  @classmethod
  def Decode(c, data):
    """Given YAML string, creates corresponding object and check its schema."""
    try:
      field_dict = c.ValidateSchema(yaml.safe_load(data), decode=True)
    except yaml.YAMLError, e:
      logging.error("YAML deserialization error: %s" % e)
      return None
    return c(**field_dict)

  @classmethod
  def ValidateSchema(c, field_dict, decode=False):
    """Ensures the layout of field_dict matches the class schema specification.

    Args:
      field_dict: Data which must have layout and type matching schema.
      decode: When set, if the schema contains references to other
        DatastoreClass subclasses, apply the appropriate constructor
        and schema validation.
    Returns:
      Schema-compliant field_dict ; or throws an assertion error is
      the schema is not met.
    """
    #TODO(tammo): Provide meaningful error output.
    #TODO(tammo): Separate validation from the returns-a-field_dict decode bits.
    assert(not (set(c._schema) ^ set(field_dict)))
    def validate_complex(t, field):
      assert(len(t) == 2)
      (ft, sft) = t
      assert(ft in [dict, list])
      assert(ft == type(field))
      if ft is dict:
        if not field:
          return {}
        for k in field:
          assert(isinstance(k, str) or isinstance(k, int))
          return dict((k, validate_field(sft, sf)) for k, sf in field.items())
      if ft is list:
        return sorted(map(lambda sf: validate_field(sft, sf), field))
    def validate_field(t, field):
      if isinstance(t, tuple):
        return validate_complex(t, field)
      elif issubclass(t, _DatastoreClass):
        if decode:
          return t(**t.ValidateSchema(field, decode))
        else:
          assert(isinstance(field, t))
          t.ValidateSchema(field.__dict__)
          return field
      else:
        assert(isinstance(field, t))
        return field
    return dict((k, validate_field(t, field_dict[k]))
                for k, t in c._schema.items())


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
