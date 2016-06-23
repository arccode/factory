# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import minijack_common  # pylint: disable=W0611
from minijack.db import models
from minijack.db import DatabaseException, Table
from minijack.db import base as db_base


class Executor(db_base.BaseExecutor):
  """A database executor.

  It abstracts the underlying database execution behaviors, like executing
  an SQL query, fetching results, etc.

  Properties:
    _conn: The connection of the Google Cloud SQL database.
    _cursor: The cursor of the Google Cloud SQL database.
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
    sql_cmd = sql_cmd.replace('?', '%s')
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


class ExecutorFactory(db_base.BaseExecutorFactory):
  """A factory to generate Executor objects.

  Properties:
    _conn: The connection of the Google Cloud SQL database.
  """

  def __init__(self, conn):
    super(ExecutorFactory, self).__init__()
    self._conn = conn

  def NewExecutor(self):
    """Generates a new Executor object."""
    return Executor(self._conn)


class Database(db_base.BaseDatabase):
  """A database to store Minijack results.

  It abstracts the underlying database.
  It uses Google Cloud SQL as an implementation.

  Properties:
    _conn: The connection of the Google Cloud SQL database.
    _tables: A dict of the created tables.
    _executor_factory: A factory of executor objects.
  """

  def __init__(self, instance_name, database_name):
    super(Database, self).__init__()
    # This module only exist on Google App Engine.
    from google.appengine.api import rdbms  # pylint: disable=E0611, F0401
    self._conn = rdbms.connect(instance=instance_name, database=database_name)
    self._executor_factory = ExecutorFactory(self._conn)
    self._tables = {}

  def DoesTableExist(self, model):
    """Checks the table with the given model schema exists or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exists; otherwise, False.
    """
    executor = self._executor_factory.NewExecutor()
    executor.Execute('SHOW tables')
    return model.GetModelName() in (r[0] for r in executor.FetchAll())

  def DoIndexesExist(self, model):
    """Checks the indexes with the given model schema exist or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exist; otherwise, False.
    """
    # TODO(pihsun): Implement this.
    # Temporary returns True to avoid creating index again.
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
    # TODO(pihsun): Implement this.
    # Temporary returns True to avoid verification fail.
    return True

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
      ('contains', "%(key)s LIKE '%%%(val_str)s%%' ESCAPE '\\\\'"),
      ('startswith', "%(key)s LIKE '%(val_str)s%%' ESCAPE '\\\\'"),
      ('endswith', "%(key)s LIKE '%%%(val_str)s' ESCAPE '\\\\'"),
  ])

  @staticmethod
  def EscapeColumnName(name, table=None):
    """Escapes column name so some keyword can be used as column name"""
    # TODO(pihsun): MySQL doesn't support escaped column name after AS,
    #               so "SELECT (c1) as (alias1) from t1" won't work.
    #               Don't do escape now since there are no MySQL keywords in
    #               column name now, but should fix this if there are more
    #               columns later.
    if table:
      return '%s.%s' % (table, name)
    else:
      return '%s' % name

  @classmethod
  def Connect(cls):
    """Connects to the database if necessary, and returns a Database."""
    # Disable lint error since the file only exist if using Cloud SQL.
    import settings_cloud_sql  # pylint: disable=F0401
    return Database(settings_cloud_sql.INSTANCE_NAME,
                    settings_cloud_sql.DATABASE_NAME)

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
