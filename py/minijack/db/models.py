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
  """
  def __init__(self, primary_key=False):
    self._primary_key = primary_key

  def IsPrimaryKey(self):
    """Is this field a primary key?"""
    return self._primary_key

  def IsValid(self, value):
    """Is the given value a valid field?"""
    raise NotImplementedError()

  def ToPython(self, value):
    """Converts the value to a Python type."""
    raise NotImplementedError()

  def GetDefault(self):
    """Gets the default value of this field."""
    raise NotImplementedError()

  def GetDbType(self):
    """Gets the database type of this field in a string."""
    raise NotImplementedError()


class IntegerField(Field):
  def IsValid(self, value):
    return isinstance(value, int)

  def ToPython(self, value):
    return int(value)

  def GetDefault(self):
    return 0

  def GetDbType(self):
    return 'INTEGER'


class FloatField(Field):
  def IsValid(self, value):
    # Both float and int are acceptable.
    return isinstance(value, float) or isinstance(value, int)

  def ToPython(self, value):
    return float(value)

  def GetDefault(self):
    return 0.0

  def GetDbType(self):
    return 'REAL'


class TextField(Field):
  def IsValid(self, value):
    return isinstance(value, str)

  def ToPython(self, value):
    return str(value)

  def GetDefault(self):
    return ''

  def GetDbType(self):
    return 'TEXT'


class ModelType(type):
  """The metaclass of Model.

  It initializes the following class attributes on the creation of Model:
    _model: The model dict, which contains the mapping of field names to
            field objects. It is used as the schema of the data model.
    _primary_key: The primary key list, which contains a list of the primary
                  key field names.
  """
  def __new__(mcs, name, bases, attrs):
    model = {}
    primary_key = []
    for attr_name, attr_value in attrs.iteritems():
      # Only pick the Field attributes.
      if issubclass(type(attr_value), Field):
        model[attr_name] = attr_value
        # Assign the class attribute to its default value.
        attrs[attr_name] = attr_value.GetDefault()
        if attr_value.IsPrimaryKey():
          primary_key.append(attr_name)
    attrs['_model'] = model
    attrs['_primary_key'] = primary_key
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
  """
  __metaclass__ = ModelType

  # The following class attributes are initialized in the metaclass.
  _model = {}
  _primary_key = []

  @classmethod
  def GetModelName(cls):
    """Gets the model name."""
    return cls.__name__

  @classmethod
  def GetDbSchema(cls):
    """Gets the schema dict, which maps a field name to a database type."""
    return dict((k, v.GetDbType()) for k, v in cls._model.iteritems())

  @classmethod
  def GetPrimaryKey(cls):
    """Gets the list of primary key field names."""
    return cls._primary_key

  @classmethod
  def IsValid(cls, instance):
    """Is the given instance a valid model?"""
    return isinstance(instance, cls)

  @classmethod
  def GetFieldNames(cls):
    """Gets the tuple of all field names."""
    return tuple(f for f in cls._model.iterkeys())

  @classmethod
  def SqlCmdCreateTable(cls):
    """Gets the SQL command of creating a table using the model schema."""
    columns = [k + ' ' + v for k, v in cls.GetDbSchema().iteritems()]
    primary_key = cls.GetPrimaryKey()
    if primary_key:
      columns.append('PRIMARY KEY ( %s )' % ', '.join(primary_key))
    sql_cmd = ('CREATE TABLE %s ( %s )' %
               (cls.GetModelName(),
                ', '.join(columns)))
    return sql_cmd

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

  def SqlCmdInsert(self):
    """Gets the SQL command tuple of inserting a row into the table."""
    # Insert all fields even they are ''/0, i.e. the default values.
    field_names = self.GetFieldNames()
    field_values = self.GetFieldValues()
    sql_cmd = ('INSERT INTO %s ( %s ) VALUES ( %s )' %
               (self.GetModelName(),
                ', '.join(field_names),
                ', '.join('?' * len(field_names))))
    return sql_cmd, field_values

  def SqlCmdUpdate(self):
    """Gets the SQL command tuple of updating a row into the table."""
    # Update the non-empty fields, using the primary key as the condition.
    field_names = self.GetFieldNames()
    field_names = self.GetNonEmptyFieldNames()
    field_values = self.GetNonEmptyFieldValues()
    conditions = self.CloneOnlyPrimaryKey()
    condition_names = conditions.GetNonEmptyFieldNames()
    condition_values = conditions.GetNonEmptyFieldValues()
    sql_cmd = ('UPDATE %s SET %s WHERE %s' %
               (self.GetModelName(),
                ', '.join([f + ' = ?' for f in field_names]),
                ' AND '.join(f + ' = ?' for f in condition_names)))
    return sql_cmd, field_values + condition_values

  def SqlCmdSelect(self):
    """Gets the SQL command tuple of selecting the matched rows."""
    # Use the non-empty fields as the condition.
    field_names = self.GetNonEmptyFieldNames()
    field_values = self.GetNonEmptyFieldValues()
    sql_cmd = ('SELECT %s FROM %s%s%s' %
               (', '.join(self.GetFieldNames()),
                self.GetModelName(),
                ' WHERE ' if field_names else '',
                ' AND '.join([f + ' = ?' for f in field_names])))
    return sql_cmd, field_values

  def SqlCmdDelete(self):
    """Gets the SQL command tuple of deleting the matched rows."""
    # Use the non-empty fields as the condition.
    field_names = self.GetNonEmptyFieldNames()
    field_values = self.GetNonEmptyFieldValues()
    sql_cmd = ('DELETE FROM %s%s%s' % (
                self.GetModelName(),
                ' WHERE ' if field_names else '',
                ' AND '.join([f + ' = ?' for f in field_names])))
    return sql_cmd, field_values


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
