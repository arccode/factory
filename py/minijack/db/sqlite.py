# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import sqlite3
import re

import minijack_common  # pylint: disable=W0611
from db import models
from db import DatabaseException, Table

import db.base


IntegrityError = sqlite3.IntegrityError


class Executor(db.base.BaseExecutor):
  """A database executor.

  It abstracts the underlying database execution behaviors, like executing
  an SQL query, fetching results, etc.

  Properties:
    _conn: The connection of the sqlite3 database.
    _cursor: The cursor of the sqlite3 database.
  """
  def __init__(self, conn):
    super(Executor, self).__init__()
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

  def GetDescription(self):
    """Gets the column names of the last query.

    Returns:
      A list of the columns names. Empty list if not a valid query.
    """
    if self._cursor.description:
      return [desc[0] for desc in self._cursor.description]
    else:
      return []

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
    return iter(lambda: self.FetchOne(model), None)


class ExecutorFactory(db.base.BaseExecutorFactory):
  """A factory to generate Executor objects.

  Properties:
    _conn: The connection of the sqlite3 database.
  """
  def __init__(self, conn):
    super(ExecutorFactory, self).__init__()
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


def _SqliteRegexp(pattern, val):
  return bool(re.search(pattern, val))


class Database(db.base.BaseDatabase):
  """A database to store Minijack results.

  It abstracts the underlying database. It uses sqlite3 as an implementation.

  Properties:
    _conn: The connection of the sqlite3 database.
    _master_table: The master table of the database.
    _tables: A dict of the created tables.
    _executor_factory: A factory of executor objects.
  """
  def __init__(self, filename):
    super(Database, self).__init__()
    self._conn = sqlite3.connect(filename)
    self._conn.create_function("regexp", 2, _SqliteRegexp)
    # Make sqlite3 always return bytestrings for the TEXT data type.
    self._conn.text_factory = str
    self._executor_factory = ExecutorFactory(self._conn)
    executor = self._executor_factory.NewExecutor()
    # Use MEMORY journaling mode which saves disk I/O.
    executor.Execute('PRAGMA journal_mode = MEMORY')
    # Don't wait OS to write all content to disk before the next action.
    executor.Execute('PRAGMA synchronous = OFF')
    # Initialize the master table of the database.
    self._master_table = Table(self)
    self._master_table.Init(sqlite_master)
    self._tables = {}

  def DoesTableExist(self, model):
    """Checks the table with the given model schema exists or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exists; otherwise, False.
    """
    condition = sqlite_master(type='table', name=model.GetModelName())
    return self._master_table.DoesRowExist(condition)

  def DoIndexesExist(self, model):
    """Checks the indexes with the given model schema exist or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exist; otherwise, False.
    """
    for field_name in model.GetDbIndexes():
      condition = sqlite_master(type='index',
          name='_'.join(['index', model.GetModelName(), field_name]))
      if not self._master_table.DoesRowExist(condition):
        return False
    return True

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
    return row.sql == self.SqlCmdCreateTable(model) if row else False

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
        table = Table(self)
        table.Init(model)
        if self.DoesTableExist(model):
          if not self.VerifySchema(model):
            raise DatabaseException('Different schema in table %s' % table_name)
        else:
          table.CreateTable()
        if not self.DoIndexesExist(model):
          logging.info(
              'Indexes of table %s not exist. Please wait to create them...',
              table_name)
          table.CreateIndexes()
        self._tables[table_name] = table
      else:
        raise DatabaseException('Table %s not initialized.' % table_name)
    return self._tables[table_name]

  def Close(self):
    """Closes the database."""
    if self._conn:
      self._conn.close()
      self._conn = None

  _operator_dict = dict([
      ('exact', '%(key)s = %(val)s'),
      ('gt', '%(key)s > %(val)s'),
      ('lt', '%(key)s < %(val)s'),
      ('gte', '%(key)s >= %(val)s'),
      ('lte', '%(key)s <= %(val)s'),
      ('regex', '%(key)s REGEXP %(val)s'),
      ('in', '%(key)s IN %(val)s'),
      ('contains', "%(key)s LIKE '%%%(val_str)s%%' ESCAPE '\\'"),
      ('startswith', "%(key)s LIKE '%(val_str)s%%' ESCAPE '\\'"),
      ('endswith', "%(key)s LIKE '%%%(val_str)s' ESCAPE '\\'"),
      ])

  @staticmethod
  def EscapeColumnName(name, table=None):
    """Escapes column name so some keyword can be used as column name"""
    if table:
      return '%s.[%s]' % (table, name)
    else:
      return '[%s]' % name

  @classmethod
  def Connect(cls):
    """Connects to the database if necessary, and returns a Database."""
    import settings
    return Database(settings.MINIJACK_DB_PATH)

  # TODO(pihsun): This only works when there is exactly one primary key field
  #               for parent model, so it won't work on ComponentDetail now.
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
    if not isinstance(parents, list):
      parents = [parents]
    pk = parents[0].GetPrimaryKey()[0]
    return self(child_type).IterFilterIn(
        pk, [getattr(p, pk) for p in parents])

  @staticmethod
  def GetMaxArguments():
    """
    Sqlite has a limit of 999 host parameters used in a single statement.
    Be safe and reserve some for other things.
    """
    return 900
