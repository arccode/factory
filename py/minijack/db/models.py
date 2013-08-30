# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import inspect


class Field(object):
  """The base class of fields.

  All the database fields are abstracted in fields, like integer fields
  (IntegerField), text fields (TextField), etc. This is the base class of
  all fields.

  Properties:
    _primary_key: True if this field is a primary key; otherwise, False.
    _db_index: True if this field is indexed; otherwise, False.
  """
  def __init__(self, primary_key=False, db_index=False):
    self._primary_key = primary_key
    self._db_index = db_index

  def IsPrimaryKey(self):
    """Is this field a primary key?"""
    return self._primary_key

  def IsDbIndex(self):
    """Is this field indexed?"""
    return self._db_index

  def IsValid(self, value):
    """Is the given value a valid field?"""
    raise NotImplementedError()

  def ToPython(self, value):
    """Converts the value to a Python type."""
    raise NotImplementedError()

  def GetDefault(self):
    """Gets the default value of this field."""
    raise NotImplementedError()

  def GetDbType(self, database_type):
    """Gets the database type of this field in a string."""
    raise NotImplementedError()


class IntegerField(Field):
  def IsValid(self, value):
    if isinstance(value, int):
      return True
    try:
      int(value)
    except ValueError:
      return False
    else:
      return True

  def ToPython(self, value):
    return int(value)

  def GetDefault(self):
    return 0

  def GetDbType(self, database_type):
    return 'INTEGER'


class FloatField(Field):
  def IsValid(self, value):
    # Both float and int are acceptable.
    if isinstance(value, float) or isinstance(value, int):
      return True
    try:
      float(value)
    except ValueError:
      return False
    else:
      return True

  def ToPython(self, value):
    return float(value)

  def GetDefault(self):
    return 0.0

  def GetDbType(self, database_type):
    from db import bigquery
    if database_type == bigquery.Database:
      return 'FLOAT'
    else:
      return 'REAL'


class TextField(Field):
  def IsValid(self, value):
    return isinstance(value, str) or isinstance(value, unicode)

  def ToPython(self, value):
    return str(value)

  def GetDefault(self):
    return ''

  def GetDbType(self, database_type):
    from db import bigquery, cloud_sql
    if database_type == bigquery.Database:
      return 'STRING'
    elif (database_type == cloud_sql.Database and
        (self._primary_key or self._db_index)):
      # MySQL can't do index on TEXT, only on VARCHAR, which has maximum length
      # limit of 255. We just use the maximum length limit here.
      return 'VARCHAR(255)'
    else:
      return 'TEXT'


class ModelType(type):
  """The metaclass of Model.

  It initializes the following class attributes on the creation of Model:
    _model: The model dict, which contains the mapping of field names to
            field objects. It is used as the schema of the data model.
    _primary_key: The primary key list, which contains a list of the primary
                  key field names.
    _db_indexes: The indexed field list, which contains a list of the indexed
                 field names.
  """
  def __new__(mcs, name, bases, attrs):
    model = {}
    primary_key = []
    db_indexes = []
    for attr_name, attr_value in attrs.iteritems():
      # Only pick the Field attributes.
      if issubclass(type(attr_value), Field):
        model[attr_name] = attr_value
        # Assign the class attribute to its default value.
        attrs[attr_name] = attr_value.GetDefault()
        if attr_value.IsPrimaryKey():
          primary_key.append(attr_name)
        if attr_value.IsDbIndex():
          db_indexes.append(attr_name)
    attrs['_model'] = model
    attrs['_primary_key'] = primary_key
    attrs['_db_indexes'] = db_indexes
    return super(ModelType, mcs).__new__(mcs, name, bases, attrs)


class Model(object):
  """The base class of models.

  A model is the data definition of the database table. Its attributes
  represent database fields, i.e. subclasses of Field.

  Properties:
    _model: The model dict, which contains the mapping of field names to
            field objects. It is used as the schema of the data model.
    _primary_key: The primary key list, which contains a list of the primary
                  key field names.
    _db_indexes: The indexed field list, which contains a list of the indexed
                 field names.
  """
  __metaclass__ = ModelType

  # The following class attributes are initialized in the metaclass.
  _model = {}
  _primary_key = []
  _db_indexes = []

  @classmethod
  def GetModelName(cls):
    """Gets the model name."""
    return cls.__name__

  @classmethod
  def GetDbSchema(cls, database_type):
    """Gets the schema dict, which maps a field name to a database type.

    Args:
      database_type: The type of underlying database, one of db.sqlite,
                     db.bigquery, db.cloud_sql
    """
    return dict((k, v.GetDbType(database_type)) for k, v in
        cls._model.iteritems())

  @classmethod
  def GetPrimaryKey(cls):
    """Gets the list of primary key field names."""
    return cls._primary_key

  @classmethod
  def GetDbIndexes(cls):
    """Gets the list of indexed field names."""
    return cls._db_indexes

  @classmethod
  def IsValid(cls, instance):
    """Is the given instance a valid model?"""
    return isinstance(instance, cls)

  @classmethod
  def GetFieldNames(cls):
    """Gets the tuple of all field names."""
    return tuple(f for f in cls._model.iterkeys())

  def __init__(self, *args, **kwargs):
    if args:
      if len(args) == 1:
        self._InitFromTuple(args[0])
      else:
        raise ValueError('Wrong arguments of instancing a Model object.')
    else:
      self._InitFromKwargs(**kwargs)

  def _InitFromTuple(self, values):
    """Initializes the Model object by giving a tuple."""
    field_names = self.GetFieldNames()
    if len(field_names) != len(values):
      raise ValueError('The size of given tuple is not matched.')
    kwargs = dict((k, v) for k, v in zip(field_names, values) if v)
    self._InitFromKwargs(**kwargs)

  def _InitFromKwargs(self, **kwargs):
    """Initializes the Model object by giving keyword arguments."""
    for field_name, field_value in kwargs.iteritems():
      if field_name not in self._model:
        raise ValueError('Field name %s not exists.' % field_name)
      field_object = self._model[field_name]
      # Use the default value if None.
      if field_value is None:
        field_value = field_object.GetDefault()
      elif not field_object.IsValid(field_value):
        raise ValueError('Field %s: %s not valid.' %
                         (field_name, field_value))
      # Convert it into a Python type.
      field_value = field_object.ToPython(field_value)
      setattr(self, field_name, field_value)

  def GetFields(self):
    """Gets the dict of all fields, which maps a field name to a value."""
    return dict((f, getattr(self, f)) for f in self._model.iterkeys())

  @classmethod
  def GetFieldObject(cls, name):
    """Gets the field object of this field name."""
    return cls._model[name]

  def GetFieldValues(self):
    """Gets the tuple of all field values."""
    return tuple(getattr(self, f) for f in self._model.iterkeys())

  def GetNonEmptyFields(self):
    """Gets the dict of all non-empty fields."""
    return dict((f, getattr(self, f)) for f in self._model.iterkeys()
                if getattr(self, f))

  def GetNonEmptyFieldNames(self):
    """Gets the tuple of all field names of non-empty fields."""
    return tuple(f for f in self._model.iterkeys() if getattr(self, f))

  def GetNonEmptyFieldValues(self):
    """Gets the tuple of all field values of non-empty fields."""
    return tuple(getattr(self, f) for f in self._model.iterkeys()
                 if getattr(self, f))

  def CloneOnlyPrimaryKey(self):
    """Clones this model object but with the primary key fields."""
    new_model = {}
    for field_name, field_value in self.GetFields().iteritems():
      if field_name in self._primary_key:
        new_model[field_name] = field_value
    return ToModelSubclass(self)(**new_model)


def ToModelSubclass(model):
  """Gets the class of a given instance of model subclass.

  Args:
    model: An instance of a subclass of Model, or just a subclass of Model.

  Raises:
    ValueError() if not a subclass of Model.
  """
  if not inspect.isclass(model):
    model = type(model)
  if issubclass(model, Model):
    return model
  else:
    raise ValueError('Not a valid Model subclass: %s' % model)
