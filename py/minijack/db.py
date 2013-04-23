# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import inspect
import sqlite3

class DatabaseException(Exception):
  pass

class Field(object):
  '''The base class of fields.

  All the database fields are abstracted in fields, like integer fields
  (IntegerField), text fields (TextField), etc. This is the base class of
  all fields.

  Properties:
    _primary_key: True if this field is a primary key; otherwise, False.
  '''
  def __init__(self, primary_key=False):
    self._primary_key = primary_key

  def IsPrimaryKey(self):
    '''Is this field a primary key?'''
    return self._primary_key

  def IsValid(self, value):
    '''Is the given value a valid field?'''
    raise NotImplementedError()

  def ToPython(self, value):
    '''Converts the value to a Python type.'''
    raise NotImplementedError()

  def GetDefault(self):
    '''Gets the default value of this field.'''
    raise NotImplementedError()

  def GetDbType(self):
    '''Gets the database type of this field in a string.'''
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

class RealField(Field):
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
  '''The metaclass of Model.

  It initializes the following class attributes on the creation of Model:
    _name: A string of the name, the same as the Python Model name.
    _model: The model dict, which contains the mapping of field names to
            field objects. It is used as the schema of the data model.
    _primary_key: The primary key list, which contains a list of the primary
                  key field names.
  '''
  def __new__(mcs, name, bases, attrs):
    attrs['_name'] = name
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
  '''The base class of models.

  A model is the data definition of the database table. Its attributes
  represents database fields, i.e. subclasses of Field. This is the base
  class of all models.

  Properties:
    _name: A string of the name, the same as the Python Model name.
    _model: The model dict, which contains the mapping of field names to
            field objects. It is used as the schema of the data model.
    _primary_key: The primary key list, which contains a list of the primary
                  key field names.
  '''
  __metaclass__ = ModelType

  # The following class attributes are initialized in the metaclass.
  _name = None
  _model = {}
  _primary_key = []

  @classmethod
  def GetModelName(cls):
    '''Gets the model name.'''
    return cls._name

  @classmethod
  def GetDbSchema(cls):
    '''Gets the schema dict, which maps a field name to a database type.'''
    return dict((k, v.GetDbType()) for k, v in cls._model.iteritems())

  @classmethod
  def GetPrimaryKey(cls):
    '''Gets the list of primary key field names.'''
    return cls._primary_key

  @classmethod
  def IsValid(cls, instance):
    '''Is the given instance a valid model?'''
    return isinstance(instance, cls)

  @classmethod
  def GetFieldNames(cls):
    '''Get the tuple of all field names.'''
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
    '''Initializes the Model object by giving a tuple.'''
    field_names = self.GetFieldNames()
    if len(field_names) != len(values):
      raise ValueError('The size of given tuple is not matched.')
    kwargs = dict((k, v) for k, v in zip(field_names, values) if v)
    self._InitFromKwargs(**kwargs)

  def _InitFromKwargs(self, **kwargs):
    '''Initializes the Model object by giving keyword arguments.'''
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
    '''Get the dict of all fields, which maps a field name to a value.'''
    return dict((f, getattr(self, f)) for f in self._model.iterkeys())

  def GetFieldValues(self):
    '''Get the tuple of all field values.'''
    return tuple(getattr(self, f) for f in self._model.iterkeys())

  def GetNonEmptyFields(self):
    '''Get the dict of all non-empty fields.'''
    return dict((f, getattr(self, f)) for f in self._model.iterkeys()
                if getattr(self, f))

  def GetNonEmptyFieldNames(self):
    '''Get the tuple of all field names of non-empty fields.'''
    return tuple(f for f in self._model.iterkeys() if getattr(self, f))

  def GetNonEmptyFieldValues(self):
    '''Get the tuple of all field values of non-empty fields.'''
    return tuple(getattr(self, f) for f in self._model.iterkeys()
                 if getattr(self, f))

  def CloneOnlyPrimaryKey(self):
    '''Clone this model object but with the primary key fields.'''
    new_model = {}
    for field_name, field_value in self.GetFields().iteritems():
      if field_name in self._primary_key:
        new_model[field_name] = field_value
    return ToModelSubclass(self)(**new_model)

def ToModelSubclass(model):
  '''Get the class of a given instance of model subclass.

  Args:
    model: An instance of a subclass of Model, or just a subclass of Model.

  Raises:
    ValueError() if not a subclass of Model.
  '''
  if not inspect.isclass(model):
    model = type(model)
  if issubclass(model, Model):
    return model
  else:
    raise ValueError('Not a valid Model subclass: %s' % model)

class Table(object):
  '''A database table.

  It abstracts the behaviors of a database table, like table creation,
  row insertion, etc. It controls the database using SQL operators.

  Properties:
    _executor_factory: A factory of executor objects.
    _model: The model dict, the schema of the table.
    _table_name: The name of the table.
    _primary_key: A list of the primary key fields.
  '''
  def __init__(self, executor_factory):
    self._executor_factory = executor_factory
    self._model = None
    self._table_name = None
    self._primary_key = []

  def Init(self, model):
    '''Initializes the table, creating it if not exists.'''
    self._model = ToModelSubclass(model)
    self._table_name = model.GetModelName()
    self._primary_key = model.GetPrimaryKey()
    # Construct the SQL command.
    columns = [k + ' ' + v for k, v in model.GetDbSchema().iteritems()]
    if self._primary_key:
      columns.append('PRIMARY KEY ( %s )' % ', '.join(self._primary_key))
    sql_cmd = ('CREATE TABLE IF NOT EXISTS %s ( %s )' %
               (self._table_name,
                ', '.join(columns)))
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, commit=True)

  def InsertRow(self, row):
    '''Inserts the row into the table.

    Args:
      row: A model instance containing the insert content.

    Raises:
      DatabaseException if not a valid model instance.
    '''
    if not self._model.IsValid(row):
      raise DatabaseException('Insert a row with a wrong model.')

    field_names = row.GetNonEmptyFieldNames()
    field_values = row.GetNonEmptyFieldValues()
    sql_cmd = ('INSERT INTO %s ( %s ) VALUES ( %s )' %
               (self._table_name,
                ', '.join(field_names),
                ', '.join('?' * len(field_names))))
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, field_values, True)

  def UpdateRow(self, row):
    '''Updates the row in the table.

    Args:
      row: A model instance containing the update content.

    Raises:
      DatabaseException if not a valid model instance.
    '''
    if not self._model.IsValid(row):
      raise DatabaseException('Update a row with a wrong model.')

    field_names = row.GetNonEmptyFieldNames()
    field_values = row.GetNonEmptyFieldValues()
    conditions = row.CloneOnlyPrimaryKey()
    condition_names = conditions.GetNonEmptyFieldNames()
    condition_values = conditions.GetNonEmptyFieldValues()
    sql_cmd = ('UPDATE %s SET %s WHERE %s' %
               (self._table_name,
                ', '.join([f + ' = ?' for f in field_names]),
                ' AND '.join(f + ' = ?' for f in condition_names)))
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, field_values + condition_values, True)

  def DoesRowExist(self, condition):
    '''Checks if a row exists or not.

    Args:
      condition: A model instance describing the checking condition.

    Returns:
      True if exists; otherwise, False.
    '''
    return bool(self.GetOneRow(condition))

  def GetOneRow(self, condition):
    '''Gets the first row which matches the given condition.

    Args:
      condition: A model instance describing the checking condition.

    Returns:
      A model instance containing the first matching row.
    '''
    return self.GetRows(condition, one_row=True)

  def GetRows(self, condition, one_row=False):
    '''Gets all the rows which match the given condition.

    Args:
      condition: A model instance describing the checking condition.
      one_row: True if only returns the first row; otherwise, all the rows.

    Returns:
      A list of model instances containing all the matching rows.

    Raises:
      DatabaseException if not a valid model instance.
    '''
    if not self._model.IsValid(condition):
      raise DatabaseException('The condition is a wrong model.')

    field_names = condition.GetNonEmptyFieldNames()
    field_values = condition.GetNonEmptyFieldValues()
    sql_cmd = ('SELECT %s FROM %s%s%s' %
               (', '.join(condition.GetFieldNames()),
                self._table_name,
                ' WHERE ' if field_names else '',
                ' AND '.join([f + ' = ?' for f in field_names])))
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, field_values)
    if one_row:
      return executor.FetchOne(model=condition)
    else:
      return executor.FetchAll(model=condition)

  def UpdateOrInsertRow(self, row):
    '''Updates the row or insert it if not exists.

    Args:
      row: A model instance containing the update content.

    Raises:
      DatabaseException if not a valid model instance.
    '''
    if not self._model.IsValid(row):
      raise DatabaseException('Update/insert a row with a wrong model.')

    # If there is no primary key in the table, just insert it.
    if not self._primary_key:
      self.InsertRow(row)
      return

    # Create a model containing the primary key as checking condition.
    condition = row.CloneOnlyPrimaryKey()
    if set(self._primary_key) != set(condition.GetNonEmptyFieldNames()):
      raise DatabaseException('Update/insert a row without a primary key.')

    # Search the primary key from the table to determine update or insert.
    if self.DoesRowExist(condition):
      self.UpdateRow(row)
    else:
      self.InsertRow(row)

class Executor(object):
  '''A database executor.

  It abstracts the underlying database execution behaviors, like executing
  an SQL query, fetching results, etc.

  Properties:
    _conn: The connection of the sqlite3 database.
    _cursor: The cursor of the sqlite3 database.
  '''
  def __init__(self, conn):
    self._conn = conn
    self._cursor = None

  def Execute(self, sql_cmd, args=None, commit=False):
    '''Executes an SQL command.

    Args:
      sql_cmd: The SQL command.
      args: The arguments passed to the SQL command.
      commit: True to commit the transaction, used when modifying the content.
    '''
    logging.debug('Execute SQL command: %s, %s;', sql_cmd, args)
    self._cursor = self._conn.cursor()
    if args:
      self._cursor.execute(sql_cmd, args)
    else:
      self._cursor.execute(sql_cmd)
    if commit:
      self._conn.commit()

  def FetchOne(self, model=None):
    '''Fetches one row of the previous query.

    Args:
      model: The model instance or class, describing the schema. The return
             value is the same type of this model class. None to return a
             raw tuple.

    Returns:
      A model instance if the argument model is valid; otherwise, a raw tuple.
    '''
    result = self._cursor.fetchone()
    if result and model:
      model = ToModelSubclass(model)
      return model(result)
    else:
      return result

  def FetchAll(self, model=None):
    '''Fetches all rows of the previous query.

    Args:
      model: The model instance or class, describing the schema. The return
             value is the same type of this model class. None to return a
             raw tuple.

    Returns:
      A list of model instances if the argument model is valid; otherwise, a
      list of raw tuples.
    '''
    results = self._cursor.fetchall()
    if results and model:
      model = ToModelSubclass(model)
      return [model(result) for result in results]
    else:
      return results

class ExecutorFactory(object):
  '''A factory to generate Executor objects.

  Properties:
    _conn: The connection of the sqlite3 database.
  '''
  def __init__(self, conn):
    self._conn = conn

  def NewExecutor(self):
    '''Generates a new Executor object.'''
    return Executor(self._conn)

class Database(object):
  '''A database to store Minijack results.

  It abstracts the underlying database. It uses sqlite3 as an implementation.

  Properties:
    _conn: The connection of the sqlite3 database.
    _tabels: A dict of the created tables.
    _executor_factory: A factory of executor objects.
  '''
  def __init__(self):
    self._conn = None
    self._tables = {}
    self._executor_factory = None

  def Init(self, filename):
    '''Initializes the database.'''
    self._conn = sqlite3.connect(filename)
    # Make sqlite3 always return bytestrings for the TEXT data type.
    self._conn.text_factory = str
    self._executor_factory = ExecutorFactory(self._conn)

  def GetExecutorFactory(self):
    '''Gets the executor factory.'''
    return self._executor_factory

  def GetOrCreateTable(self, model):
    '''Gets or creates a table using the schema of the given model.'''
    if isinstance(model, str):
      table_name = model
    else:
      table_name = model.GetModelName()
    if table_name not in self._tables:
      if not isinstance(model, str):
        table = Table(self._executor_factory)
        table.Init(model)
        self._tables[table_name] = table
      else:
        raise DatabaseException('Table %s not initialized.' % table_name)
    return self._tables[table_name]

  def Close(self):
    '''Closes the database.'''
    self._conn.close()
