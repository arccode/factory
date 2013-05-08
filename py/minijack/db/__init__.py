# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import sqlite3

import models


IntegrityError = sqlite3.IntegrityError


class DatabaseException(Exception):
  pass


class Table(object):
  """A database table.

  It abstracts the behaviors of a database table, like table creation,
  row insertion, etc. It controls the database using SQL operators.

  Properties:
    _executor_factory: A factory of executor objects.
    _model: The model dict, the schema of the table.
    _table_name: The name of the table.
    _primary_key: A list of the primary key fields.
  """
  def __init__(self, executor_factory):
    self._executor_factory = executor_factory
    self._model = None
    self._table_name = None
    self._primary_key = []

  def Init(self, model):
    """Initializes the table.

    Args:
      model: A model class or a model instance.
    """
    self._model = models.ToModelSubclass(model)
    self._table_name = model.GetModelName()
    self._primary_key = model.GetPrimaryKey()

  def CreateTable(self):
    """Creates the table."""
    sql_cmd = self._model.SqlCmdCreateTable()
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, commit=True)

  def InsertRow(self, row):
    """Inserts a row into the table.

    Args:
      row: A model instance containing the insert content.

    Raises:
      DatabaseException if not a valid model instance.
    """
    if not self._model.IsValid(row):
      raise DatabaseException('Insert a row with a wrong model.')

    sql_cmd, args = row.SqlCmdInsert()
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, args, commit=True)

  def InsertRows(self, rows):
    """Inserts multiple rows into the table.

    Args:
      rows: A list of model instances containing the insert content.

    Raises:
      DatabaseException if not a valid model instance.
    """
    if not isinstance(rows, list):
      raise DatabaseException('The given row is not a list.')

    if not rows:
      return

    args_list = []
    for row in rows:
      if not self._model.IsValid(row):
        raise DatabaseException('Insert a row with a wrong model.')
      sql_cmd, args = row.SqlCmdInsert()
      args_list.append(args)

    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, args_list, commit=True, many=True)

  def UpdateRow(self, row):
    """Updates the row in the table.

    Args:
      row: A model instance containing the update content.

    Raises:
      DatabaseException if not a valid model instance.
    """
    if not self._model.IsValid(row):
      raise DatabaseException('Update a row with a wrong model.')

    sql_cmd, args = row.SqlCmdUpdate()
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, args, commit=True)

  def DoesRowExist(self, condition):
    """Checks if a row exists or not.

    Args:
      condition: A model instance describing the checking condition.

    Returns:
      True if exists; otherwise, False.
    """
    return bool(self.GetOneRow(condition))

  def GetOneRow(self, condition):
    """Gets the first row which matches the given condition.

    Args:
      condition: A model instance describing the checking condition.

    Returns:
      A model instance containing the first matching row.
    """
    return self.GetRows(condition, one_row=True)

  def GetRows(self, condition, one_row=False):
    """Gets allthe rows which match the given condition.

    Args:
      condition: A model instance describing the checking condition.
      one_row: True if only returns the first row; otherwise, all the rows.

    Returns:
      A list of model instances containing all the matching rows.

    Raises:
      DatabaseException if not a valid model instance.
    """
    if not self._model.IsValid(condition):
      raise DatabaseException('The condition is a wrong model.')

    sql_cmd, args = condition.SqlCmdSelect()
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, args)
    if one_row:
      return executor.FetchOne(model=condition)
    else:
      return executor.FetchAll(model=condition)

  def DeleteRows(self, condition):
    """Deletes all the rows which match the given condition.

    Args:
      condition: A model instance describing the checking condition.

    Raises:
      DatabaseException if not a valid model instance.
    """
    if not self._model.IsValid(condition):
      raise DatabaseException('The condition is a wrong model.')

    sql_cmd, args = condition.SqlCmdDelete()
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, args, commit=True)

  def UpdateOrInsertRow(self, row):
    """Updates the row or insert it if not exists.

    Args:
      row: A model instance containing the update content.

    Raises:
      DatabaseException if not a valid model instance.
    """
    if not self._model.IsValid(row):
      raise DatabaseException('Update/insert a row with a wrong model.')

    # We use the primary key as the condition to update the row, If there is no
    # primary key in the table, just simply insert it. Don't do update.
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
  """A database executor.

  It abstracts the underlying database execution behaviors, like executing
  an SQL query, fetching results, etc.

  Properties:
    _conn: The connection of the sqlite3 database.
    _cursor: The cursor of the sqlite3 database.
  """
  def __init__(self, conn):
    self._conn = conn
    self._cursor = self._conn.cursor()

  def Execute(self, sql_cmd, args=None, commit=False, many=False):
    """Executes an SQL command.

    Args:
      sql_cmd: The SQL command.
      args: The arguments passed to the SQL command, a tuple or a dict.
      commit: True to commit the transaction, used when modifying the content.
      many: Do multiple execution. If True, the args argument should be a list.
    """
    logging.debug('Execute SQL command: %s, %s;', sql_cmd, args)
    if not args:
      args = tuple()
    if many:
      self._cursor.executemany(sql_cmd, args)
    else:
      self._cursor.execute(sql_cmd, args)
    if commit:
      self._conn.commit()

  def FetchOne(self, model=None):
    """Fetches one row of the previous query.

    Args:
      model: The model instance or class, describing the schema. The return
             value is the same type of this model class. None to return a
             raw tuple.

    Returns:
      A model instance if the argument model is valid; otherwise, a raw tuple.
    """
    result = self._cursor.fetchone()
    if result and model:
      model = models.ToModelSubclass(model)
      return model(result)
    else:
      return result

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
    results = self._cursor.fetchall()
    if results and model:
      model = models.ToModelSubclass(model)
      return [model(result) for result in results]
    else:
      return results


class ExecutorFactory(object):
  """A factory to generate Executor objects.

  Properties:
    _conn: The connection of the sqlite3 database.
  """
  def __init__(self, conn):
    self._conn = conn

  def NewExecutor(self):
    """Generates a new Executor object."""
    return Executor(self._conn)


# Don't change the class name. 'sqlite_master' is the special table in Sqlite.
class sqlite_master(models.Model):
  """The master table of Sqlite database which contains the info of tables."""
  type     = models.TextField()
  name     = models.TextField()
  tbl_name = models.TextField()
  rootpage = models.IntegerField()
  sql      = models.TextField()


class Database(object):
  """A database to store Minijack results.

  It abstracts the underlying database. It uses sqlite3 as an implementation.

  Properties:
    _conn: The connection of the sqlite3 database.
    _master_table: The master table of the database.
    _tables: A dict of the created tables.
    _executor_factory: A factory of executor objects.
  """
  def __init__(self):
    self._conn = None
    self._master_table = None
    self._tables = {}
    self._executor_factory = None

  def __del__(self):
    self.Close()

  def Init(self, filename):
    """Initializes the database.

    Args:
      filename: The filename of the database.
    """
    self._conn = sqlite3.connect(filename)
    # Make sqlite3 always return bytestrings for the TEXT data type.
    self._conn.text_factory = str
    self._executor_factory = ExecutorFactory(self._conn)
    executor = self._executor_factory.NewExecutor()
    # Use MEMORY journaling mode which saves disk I/O.
    executor.Execute('PRAGMA journal_mode = MEMORY')
    # Don't wait OS to write all content to disk before the next action.
    executor.Execute('PRAGMA synchronous = OFF')
    # Initialize the master table of the database.
    self._master_table = Table(self._executor_factory)
    self._master_table.Init(sqlite_master)

  def DoesTableExist(self, model):
    """Checks the table with the given model schema exists or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exists; otherwise, False.
    """
    condition = sqlite_master(name=model.GetModelName())
    return self._master_table.DoesRowExist(condition)

  def GetExecutorFactory(self):
    """Gets the executor factory."""
    return self._executor_factory

  def VerifySchema(self, model):
    """Verifies the table in the database has the same given model schema.

    Args:
      model: A model class or a model instance.

    Returns:
      True if the same schema; otherwise, False.
    """
    condition = sqlite_master(name=model.GetModelName())
    row = self._master_table.GetOneRow(condition)
    return row.sql == model.SqlCmdCreateTable() if row else False

  def GetOrCreateTable(self, model):
    """Gets or creates a table using the schema of the given model.

    Args:
      model: A string, a model class, or a model instance.

    Returns:
      The table instance.
    """
    if isinstance(model, str):
      table_name = model
    else:
      table_name = model.GetModelName()
    if table_name not in self._tables:
      if not isinstance(model, str):
        table = Table(self._executor_factory)
        table.Init(model)
        if self.DoesTableExist(model):
          if not self.VerifySchema(model):
            raise DatabaseException('Different schema in table %s' % table_name)
        else:
          table.CreateTable()
        self._tables[table_name] = table
      else:
        raise DatabaseException('Table %s not initialized.' % table_name)
    return self._tables[table_name]

  def Close(self):
    """Closes the database."""
    if self._conn:
      self._conn.close()
      self._conn = None

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

  def GetOne(self, condition):
    """Gets the first model which matches the given condition."""
    table = self.GetOrCreateTable(condition)
    return table.GetOneRow(condition)

  def GetAll(self, condition):
    """Gets all the models which match the given condition."""
    table = self.GetOrCreateTable(condition)
    return table.GetRows(condition)

  def DeleteAll(self, condition):
    """Deletes all the models which match the given condition."""
    table = self.GetOrCreateTable(condition)
    table.DeleteRows(condition)

  def UpdateOrInsert(self, model):
    """Updates the model or insert it if not exists."""
    table = self.GetOrCreateTable(model)
    table.UpdateOrInsertRow(model)
