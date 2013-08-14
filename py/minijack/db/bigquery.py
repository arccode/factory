# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import httplib2

from apiclient.discovery import build
from apiclient.errors import HttpError

from oauth2client.client import SignedJwtAssertionCredentials

from db import models
from db import DatabaseException, Table

import db.base
import settings


def _EscapeArgument(arg):
  """Escapes the argument used in SQL statement of BigQuery"""
  if isinstance(arg, str) or isinstance(arg, unicode):
    ret = '"'
    dangerous_chars = set('%?,;\\\"\'&')
    for c in arg:
      if ord(c) < 32 or c in dangerous_chars:
        ret += "\\x%02x" % ord(c)
      else:
        ret += c
    ret += '"'
  elif isinstance(arg, int) or isinstance(arg, float):
    ret = str(arg)
  else:
    raise ValueError("Unknown type of argument in BigQuery's EscapeArgument")
  return ret


def _BuildQuery(sql_cmd, args):
  """Builds the real SQL query statement using original query and arguments.

  Since Google BigQuery API doesn't support query with arguments, we have to
  manually escape arguments and embed them into the SQL query statement.

  Args:
    sql_cmd: The original SQL query, with '?' as placeholder for arguments.
    args: The arguments in the query.
  """
  safe_args = [_EscapeArgument(arg) for arg in args]
  idx = 0
  ret = ""
  for c in sql_cmd:
    if c == '?':
      if idx == len(safe_args):
        raise DatabaseException(
            'Too many ? in query %s, %s' % (sql_cmd, args))
      ret += safe_args[idx]
      idx += 1
    else:
      ret += c
  if idx != len(safe_args):
    raise DatabaseException(
        'Too many arguments in query %s, %s' % (sql_cmd, args))
  return ret


class Executor(db.base.BaseExecutor):
  """A database executor.

  It abstracts the underlying database execution behaviors, like executing
  an SQL query, fetching results, etc.

  Properties:
    _service: The service object for Google BigQuery API client.
    _page_token: The pageToken retrived from BigQuery API.
    _job_id: The job id of last job.
    _column_names: The column names of the last query.
  """
  def __init__(self, service):
    super(Executor, self).__init__()
    self._service = service
    self._page_token = None
    self._job_id = None
    self._column_names = []

  def Execute(self, sql_cmd, args=None, dummy_commit=False, many=False):
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
    if isinstance(args, dict):
      raise NotImplementedError('Dictionary query arguments not implemented.')
    # TODO(pihsun): Implement these
    elif not isinstance(args, tuple) and not isinstance(args, list):
      raise ValueError('Unknown type for args %s' % args)
    if many:
      raise NotImplementedError('Multiple execution not implemented.')
    else:
      self._page_token = None
      try:
        query = _BuildQuery(sql_cmd, args)
        query_result = self._service.jobs().query(
            projectId=settings.PROJECT_ID,
            body={
              'kind': 'bigquery#queryRequest',
              'defaultDataset': {
                'datasetId': settings.DATASET_ID,
              },
              'query': query,
              'maxResults': 1,
              'preserveNulls': True,
            }).execute()
      except HttpError as e:
        self._page_token = None
        self._job_id = None
        self._column_names = []
        raise e
      else:
        if not query_result['jobComplete']:
          raise DatabaseException('Job not completed within time limit')
        # TODO(pihsun): We have the first row here, cache it for further use?
        self._job_id = query_result['jobReference']['jobId']
        self._column_names = [f['name']
                              for f in query_result['schema']['fields']]

  def GetDescription(self):
    """Gets the column names of the last query.

    Returns:
      A list of the columns names. Empty list if not a valid query.
    """
    return self._column_names

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
    query_result = self._service.jobs().getQueryResults(
        projectId=settings.PROJECT_ID,
        jobId=self._job_id,
        pageToken=self._page_token,
        maxResults=1).execute()
    if 'pageToken' in query_result:
      self._page_token = query_result['pageToken']
    if not 'rows' in query_result:
      # No result
      return None
    result = tuple(c['v'] for c in query_result['rows'][0]['f'])
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
    query_result = self._service.jobs().getQueryResults(
        projectId=settings.PROJECT_ID,
        jobId=self._job_id,
        pageToken=self._page_token).execute()
    if 'pageToken' in query_result:
      self._page_token = query_result['pageToken']
    if not 'rows' in query_result:
      # No result
      return []
    results = [tuple(c['v'] for c in r['f']) for r in query_result['rows']]
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
    return iter(self.FetchAll(model))


class ExecutorFactory(db.base.BaseExecutorFactory):
  """A factory to generate Executor objects.

  Properties:
    _service: The service object for Google BigQuery API client.
  """
  def __init__(self, service):
    super(ExecutorFactory, self).__init__()
    self._service = service

  def NewExecutor(self):
    """Generates a new Executor object."""
    return Executor(self._service)


class Database(db.base.BaseDatabase):
  """A database to store Minijack results.

  It abstracts the underlying database.
  It uses BigQuery's dataset as an implementation.

  Properties:
    _service: The service object for Google BigQuery API client.
    _tables: A dict of the created tables.
    _executor_factory: A factory of executor objects.
    _table_names: All table names in the dataset, cache when first fetched.
  """
  def __init__(self):
    super(Database, self).__init__()
    credential = SignedJwtAssertionCredentials(
      settings.GOOGLE_API_ID,
      settings.GOOGLE_API_PRIVATE_KEY,
      scope=[
        'https://www.googleapis.com/auth/bigquery',
      ])
    http = httplib2.Http(timeout=60)
    http = credential.authorize(http)

    self._service = build('bigquery', 'v2', http=http)
    self._tables = {}
    self._executor_factory = ExecutorFactory(self._service)
    self._table_names = None

  def DoesTableExist(self, model):
    """Checks the table with the given model schema exists or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exists; otherwise, False.
    """
    if self._table_names is None:
      result = self._service.tables().list(
          projectId=settings.PROJECT_ID,
          datasetId=settings.DATASET_ID).execute()
      self._table_names = set(t['tableReference']['tableId']
                              for t in result['tables'])
    return model.GetModelName() in self._table_names

  def DoIndexesExist(self, model):
    """Checks the indexes with the given model schema exist or not.

    Args:
      model: A model class or a model instance.

    Returns:
      True if exist; otherwise, False.
    """
    # There's no index in BigQuery.
    # Since if this is False, we would attempt to execute the 'CREATE INDEX'
    # SQL in BigQuery, and would result in an error.
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
    # TODO(pihsun): Implement the check.
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
        table = Table(self._executor_factory)
        table.Init(model)
        if self.DoesTableExist(model):
          if not self.VerifySchema(model):
            raise DatabaseException('Different schema in table %s' % table_name)
        else:
          raise DatabaseException(
              'Table %s doesn\'t exist in BigQuery' % table_name)
        self._tables[table_name] = table
      else:
        raise DatabaseException('Table %s not initialized.' % table_name)
    return self._tables[table_name]

  def Close(self):
    """Closes the database."""
    pass

  def Update(self, model):
    """Updates the model in the database."""
    raise DatabaseException('Can\'t do update on BigQuery')

  def DeleteAll(self, condition):
    """Deletes all the models which match the given condition."""
    raise DatabaseException('Can\'t do delete on BigQuery')

  def UpdateOrInsert(self, model):
    """Updates the model or insert it if not exists."""
    raise DatabaseException('Can\'t do update on BigQuery')

  _operator_dict = dict([
      ('exact', '%(key)s = %(val)s'),
      ('gt', '%(key)s > %(val)s'),
      ('lt', '%(key)s < %(val)s'),
      ('gte', '%(key)s >= %(val)s'),
      ('lte', '%(key)s <= %(val)s'),
      ('regex', 'REGEXP_MATCH(%(key)s, %(val)s)'),
      ('in', '%(key)s IN %(val)s'),
      ('contains', '%(key)s CONTAINS %(val)s'),
      ('startswith', 'LEFT(%(key), LENGTH(%(val))) = %(val)'),
      ('endswith', 'RIGHT(%(key), LENGTH(%(val))) = %(val)'),
      ])

  @staticmethod
  def EscapeColumnName(name, table=None):
    """Escape column name so some keyword can be used as column name"""
    if table:
      return '[%s.%s]' % (table, name)
    else:
      return '[%s]' % name

  _database = None

  @classmethod
  def Connect(cls):
    """Connects to the database if necessary, and returns a Database."""
    if cls._database is None:
      cls._database = Database()
    return cls._database

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
    fields = [self.EscapeColumnName(f) if f == pk
              else self.EscapeColumnName(f, child_type.nested_name)
              + ' AS ' + self.EscapeColumnName(f)
              for f in child_type.GetFieldNames()]
    sql_where = (self.EscapeColumnName(pk) + ' IN (' +
                 ','.join(['?'] * len(parents)) + ')')
    sql_cmd = ('SELECT %s FROM %s WHERE %s' %
               (','.join(f for f in fields),
                self.EscapeColumnName(parents[0].GetModelName()),
                sql_where))
    field_values = [getattr(p, pk) for p in parents]
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, field_values)
    return executor.FetchAll(model=child_type)

