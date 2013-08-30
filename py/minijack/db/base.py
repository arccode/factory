# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import sys

import minijack_common  # pylint: disable=W0611
from db import QuerySet, Q


# TODO(pihsun): Unit test.
class BaseExecutor(object):
  """A database executor.

  It abstracts the underlying database execution behaviors, like executing
  an SQL query, fetching results, etc.
  """
  def Execute(self, sql_cmd, args=None, dummy_commit=False, many=False):
    """Executes an SQL command.

    Args:
      sql_cmd: The SQL command.
      args: The arguments passed to the SQL command, a tuple or a dict.
      commit: True to commit the transaction, used when modifying the content.
      many: Do multiple execution. If True, the args argument should be a list.
    """
    raise NotImplementedError()

  def GetDescription(self):
    """Gets the column names of the last query.

    Returns:
      A list of the columns names. Empty list if not a valid query.
    """
    raise NotImplementedError()

  def FetchOne(self, model=None):
    """Fetches one row of the previous query.

    Args:
      model: The model instance or class, describing the schema. The return
             value is the same type of this model class. None to return a
             raw tuple.

    Returns:
      A model instance if the argument model is valid; otherwise, a raw tuple.
      None when no more data is available.
    """
    raise NotImplementedError()

  def FetchAll(self, model=None):
    """Fetches all rows of the previous query.

    Args:
      model: The model instance or class, describing the schema. The return
             value is the same type of this model class. None to return a
             raw tuple.

    Returns:
      A list of model instances if the argument model is valid; otherwise, a
      list of raw tuples.
    """
    raise NotImplementedError()

  def IterateAll(self, model=None):
    """Iterates through all row of the previous query.

    Args:
      model: The model instance or class, describing the schema. The return
             value is the same type of this model class. None to return a
             raw tuple.

    Returns:
      A iterator to model instances if the argument model is valid;
      otherwise, a iterator to raw tuples.
    """
    raise NotImplementedError()


class BaseExecutorFactory(object):
  """A factory to generate Executor objects."""
  def NewExecutor(self):
    """Generates a new Executor object."""
    raise NotImplementedError()


class BaseDatabase(object):
  """A database to store Minijack results.

  It abstracts the underlying database.
  """
  def __del__(self):
    self.Close()

  def QuerySet(self, model):
    return QuerySet(self, model)

  def Q(self, **kwargs):
    return Q(self, **kwargs)

  __call__ = QuerySet

  def DoesTableExist(self, model):
    """Checks the table with the given model schema exists or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exists; otherwise, False.
    """
    raise NotImplementedError()

  def DoIndexesExist(self, model):
    """Checks the indexes with the given model schema exist or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exist; otherwise, False.
    """
    raise NotImplementedError()

  def GetExecutorFactory(self):
    """Gets the executor factory."""
    raise NotImplementedError()

  def VerifySchema(self, model):
    """Verifies the table in the database has the same given model schema.

    Args:
      model: A model class or a model instance.

    Returns:
      True if the same schema; otherwise, False.
    """
    raise NotImplementedError()

  def GetOrCreateTable(self, model):
    """Gets or creates a table using the schema of the given model.

    Args:
      model: A string, a model class, or a model instance.

    Returns:
      The table instance.
    """
    raise NotImplementedError()

  def Close(self):
    """Closes the database."""
    raise NotImplementedError()

  _operator_dict = dict()

  @classmethod
  def GetOperator(cls, op):
    """Gets the string used for formatting the operation"""
    return cls._operator_dict[op]

  # The following methods help accessing tables easily. They automatically
  # get the proper tables and do the jobs on the tables.

  def Insert(self, model):
    """Inserts a model into the database."""
    table = self.GetOrCreateTable(model)
    table.InsertRow(model)

  def InsertMany(self, model_list):
    """Inserts multiple models into the database."""
    if model_list and len(model_list) >= 1:
      table = self.GetOrCreateTable(model_list[0])
      table.InsertRows(model_list)

  def Update(self, model):
    """Updates the model in the database."""
    table = self.GetOrCreateTable(model)
    table.UpdateRow(model)

  def CheckExists(self, model):
    """Checks if the model exists or not."""
    table = self.GetOrCreateTable(model)
    return table.DoesRowExist(model)

  # TODO(pihsun): No longer need these since QuerySet is enough.
  def GetOne(self, condition):
    """Gets the first model which matches the given condition."""
    table = self.GetOrCreateTable(condition)
    return table.GetOneRow(condition)

  def GetAll(self, condition):
    """Gets all the models which match the given condition."""
    table = self.GetOrCreateTable(condition)
    return table.GetRows(condition)

  def IterateAll(self, condition):
    """Iterates all the models which match the given condition."""
    table = self.GetOrCreateTable(condition)
    return table.IterateRows(condition)

  def DeleteAll(self, condition):
    """Deletes all the models which match the given condition."""
    table = self.GetOrCreateTable(condition)
    table.DeleteRows(condition)

  def UpdateOrInsert(self, model):
    """Updates the model or insert it if not exists."""
    table = self.GetOrCreateTable(model)
    table.UpdateOrInsertRow(model)

  @staticmethod
  def EscapeColumnName(name, table=None):
    """Escapes column name so some keyword can be used as column name"""
    if table:
      return '%s.%s' % (table, name)
    else:
      return name

  @classmethod
  def Connect(cls):
    """Connects to the database if necessary, and returns a Database."""
    raise NotImplementedError()

  def GetRelated(self, child_type, parents):
    """Gets all related child_type objects of parent.

    For example, if model B is nested in model A, calling with child_type = B
    and parents = list of instance of A would retrieve all B that is nested
    inside one of parents.

    Args:
      child_type: The type of the object to be retrived.
      parents: A list of reference parent objects

    Returns:
      The related objects
    """
    raise NotImplementedError()

  @staticmethod
  def GetMaxArguments():
    return sys.maxint

  @classmethod
  def SqlCmdCreateTable(cls, model):
    """Gets the SQL command of creating a table using the model schema."""
    columns = [k + ' ' + v for k, v in model.GetDbSchema(cls).iteritems()]
    primary_key = model.GetPrimaryKey()
    if primary_key:
      columns.append('PRIMARY KEY ( %s )' % ', '.join(primary_key))
    sql_cmd = ('CREATE TABLE %s ( %s )' %
               (model.GetModelName(),
                ', '.join(columns)))
    return sql_cmd

  @classmethod
  def SqlCmdCreateIndexes(cls, model):
    """Gets the SQL commands of creating indexes using the model schema."""
    sql_cmds = []
    for field_name in model.GetDbIndexes():
      sql_cmds.append('CREATE INDEX %s ON %s ( %s )' % (
          '_'.join(['index', model.GetModelName(), field_name]),
          model.GetModelName(),
          field_name))
    return sql_cmds

  @classmethod
  def SqlCmdInsert(cls, row):
    """Gets the SQL command tuple of inserting a row into the table."""
    # Insert all fields even they are ''/0, i.e. the default values.
    field_names = row.GetFieldNames()
    field_values = row.GetFieldValues()
    sql_cmd = ('INSERT INTO %s ( %s ) VALUES ( %s )' %
               (row.GetModelName(),
                ', '.join(field_names),
                ', '.join('?' * len(field_names))))
    return sql_cmd, field_values

  @classmethod
  def SqlCmdUpdate(cls, row):
    """Gets the SQL command tuple of updating a row into the table."""
    # Update the non-empty fields, using the primary key as the condition.
    field_names = row.GetFieldNames()
    field_names = row.GetNonEmptyFieldNames()
    field_values = row.GetNonEmptyFieldValues()
    conditions = row.CloneOnlyPrimaryKey()
    condition_names = conditions.GetNonEmptyFieldNames()
    condition_values = conditions.GetNonEmptyFieldValues()
    sql_cmd = ('UPDATE %s SET %s WHERE %s' %
               (row.GetModelName(),
                ', '.join([f + ' = ?' for f in field_names]),
                ' AND '.join(f + ' = ?' for f in condition_names)))
    return sql_cmd, field_values + condition_values

  # TODO(pihsun): See if anyone calls this, change to QuerySet, remove this.
  @classmethod
  def SqlCmdSelect(cls, row):
    """Gets the SQL command tuple of selecting the matched rows."""
    # Use the non-empty fields as the condition.
    field_names = row.GetNonEmptyFieldNames()
    field_values = row.GetNonEmptyFieldValues()
    sql_cmd = ('SELECT %s FROM [%s]%s%s' %
               (', '.join('[' + f + ']' for f in row.GetFieldNames()),
                row.GetModelName(),
                ' WHERE ' if field_names else '',
                ' AND '.join(['[' + f + '] = ?' for f in field_names])))
    return sql_cmd, field_values

  @classmethod
  def SqlCmdDelete(cls, row):
    """Gets the SQL command tuple of deleting the matched rows."""
    # Use the non-empty fields as the condition.
    field_names = row.GetNonEmptyFieldNames()
    field_values = row.GetNonEmptyFieldValues()
    sql_cmd = ('DELETE FROM %s%s%s' % (
                row.GetModelName(),
                ' WHERE ' if field_names else '',
                ' AND '.join([f + ' = ?' for f in field_names])))
    return sql_cmd, field_values
