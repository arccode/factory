# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import logging
import os
import sys

import minijack_common  # pylint: disable=W0611

import models
import settings


class DatabaseException(Exception):
  pass


def _Grouper(vals, chunk_size):
  """A generator to cut list into chunks and yield one by one."""
  for pos in xrange(0, len(vals), chunk_size):
    yield vals[pos:pos + chunk_size]


class Table(object):
  """A database table.

  It abstracts the behaviors of a database table, like table creation,
  row insertion, etc. It controls the database using SQL operators.

  Properties:
    _executor_factory: A factory of executor objects.
    _model: The model dict, the schema of the table.
    _table_name: The name of the table.
    _primary_key: A list of the primary key fields.
    _database: The underlying database.
  """
  def __init__(self, database):
    self._database = database
    self._executor_factory = database.GetExecutorFactory()
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
    sql_cmd = self._database.SqlCmdCreateTable(self._model)
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, commit=True)

  def CreateIndexes(self):
    """Creates the indexes of the table."""
    executor = self._executor_factory.NewExecutor()
    for sql_cmd in self._database.SqlCmdCreateIndexes(self._model):
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

    sql_cmd, args = self._database.SqlCmdInsert(row)
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
      sql_cmd, args = self._database.SqlCmdInsert(row)
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

    sql_cmd, args = self._database.SqlCmdUpdate(row)
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, args, commit=True)

  # TODO(pihsun): Replace calls of these query functions to QuerySet.
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

  def IterateRows(self, condition):
    """Iterates all the rows which match the given condition.

    Args:
      condition: A model instance describing the checking condition.

    Returns:
      An iterator of all matching rows.
    """
    return self.GetRows(condition, iter_all=True)

  def GetRows(self, condition, one_row=False, iter_all=False):
    """Gets all the rows which match the given condition.

    Args:
      condition: A model instance describing the checking condition.
      one_row: True if only returns the first row; otherwise, all the rows.
      iter_all: True to return a row iterator, instead of a list.

    Returns:
      A list of model instances containing all the matching rows when the
      argument iter_all == False; or a row iterator when iter_all == True.

    Raises:
      DatabaseException if not a valid model instance.
    """
    if not self._model.IsValid(condition):
      raise DatabaseException('The condition is a wrong model.')

    sql_cmd, args = self._database.SqlCmdSelect(condition)
    executor = self._executor_factory.NewExecutor()
    executor.Execute(sql_cmd, args)
    if iter_all:
      return executor.IterateAll(model=condition)
    elif one_row:
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

    sql_cmd, args = self._database.SqlCmdDelete(condition)
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


class Q(object):
  """An expression in WHERE clause of a SQL statement.

  Properties:
    _args: The '?' arguments in SQL statement.
    _sql: The representing SQL statement.
    _database: The database connection.
  """

  @staticmethod
  def _ReprValue(val):
    """Parses an object to a SQL-compatible representation.

    Args:
      val: The value to be parsed.
    Returns:
      A pair (sql, args), sql is the SQL-compatible representation, which
      has all arguments that needs ecsaping as '?', and args is a list of
      arguments that should be substituted into these '?'.
    """
    if (isinstance(val, str) or isinstance(val, unicode) or
        isinstance(val, int) or isinstance(val, float)):
      return '?', [val]
    elif isinstance(val, list) or isinstance(val, tuple):
      sub_list = []
      arg_list = []
      for v in val:
        sub, args = Q._ReprValue(v)
        sub_list.append(sub)
        arg_list += args
      return ('(%s)' % ','.join(sub_list)), arg_list
    else:
      raise ValueError('Unknown type %s used in Query value' % type(val))

  @staticmethod
  def _ParseCondition(kwargs):
    """Parses the condition options used in initialize of Q object.

    Args:
      kwargs: The options.
    Returns:
      A list of (column name, sql operator name, value).
    """
    for k, v in kwargs.iteritems():
      ks = k.rsplit('__', 1)
      if len(ks) == 1:
        ks.append('exact')
      yield ks + [v]

  def __deepcopy__(self, dummy_memo):
    ret = Q.__new__(Q)
    ret._database = self._database
    ret._sql = self._sql
    ret._args = copy.copy(self._args)
    return ret

  def __init__(self, database, **kwargs):
    self._args = []
    self._database = database
    condition_list = []
    for key, op, val in Q._ParseCondition(kwargs):
      op_str = self._database.GetOperator(op)
      val_repr, cur_args = Q._ReprValue(val)
      condition_list.append(op_str % {
          'key': self._database.EscapeColumnName(key),
          # TODO(pihsun): Fix this for SQL LIKE with % or _ inside.
          'val_str': str(val),
          'val': val_repr,
          })
      self._args += cur_args * op_str.count('%(val)')
    self._sql = ' AND '.join('(%s)' % c for c in condition_list)

  def __nonzero__(self):
    return bool(self._sql)

  def __and__(self, other):
    if not (self and other):
      # one of the operands is empty.
      return self or other
    ret = Q(self._database)
    ret._args = self._args + other.GetArgs()
    ret._sql = '(%s) AND (%s)' % (self._sql, other.GetSql())
    return ret

  def __or__(self, other):
    if not (self and other):
      # one of the operands is empty.
      return self or other
    ret = Q(self._database)
    ret._args = self._args + other.GetArgs()
    ret._sql = '%s OR %s' % (self._sql, other.GetSql())
    return ret

  def __invert__(self):
    if not self:
      raise ValueError("Can't invert an empty Q object.")
    ret = Q(self._database)
    ret._args = self._args
    ret._sql = 'NOT (%s)' % self._sql
    return ret

  def GetSql(self):
    """Gets the underlying SQL statement of this Q object"""
    return self._sql

  def GetArgs(self):
    """Gets the underlying arguments of this Q object"""
    return self._args


class QuerySet(object):
  """A SELECT statement in SQL.

  It abstract the underlying SQL SELECT statement, and try to mimic what
  Django's QuerySet does, but only do statements that only needs a select.
  Unlike what Django does, all methods directly mutate the object. Use
  copy.deepcopy() when need to duplicate a QuerySet.

  TODO(pihsun): Add unicode support if needed.

  Properties:
    _model: The model type to be selected.
    _database: The database connection.
    _order: The columns used in 'ORDER BY' clause.
    _condition: A Q object, which is the condition used in 'WHERE' clause.
    _column_list: The columns to be selected.
    _return_type: The type of return value of GetOne/GetAll, which is one of
                  'model', 'dict', 'tuple', 'tuple_flat', 'tuple_distinct'.
    _join_select: A QuerySet representing the SELECT statement to be joined,
                  or None if there's no join.
    _join_on: A list of pair (table 1 column name, table 2 column name), JOIN
              ON when these columns are equal.
    _annotate_dict: A dict of name to (aggregate function, target field name)
                    that is used to annotate extra fields.
  """
  def __init__(self, database, model):
    self._model = models.ToModelSubclass(model)
    self._database = database
    self._order = None
    self._column_list = model.GetFieldNames()
    self._return_type = 'model'
    self._condition = self._database.Q()
    self._join_select = None
    self._join_on = []
    self._annotate_dict = dict()

  def __iter__(self):
    """Iterates all the models which match the given condition."""
    sql_query, args = self.BuildQuery()
    executor = self._database.GetExecutorFactory().NewExecutor()
    executor.Execute(sql_query, args)
    if self._return_type == 'model':
      return executor.IterateAll(model=self._model)
    elif self._return_type == 'tuple':
      return executor.IterateAll()
    elif self._return_type == 'dict':
      desc = executor.GetDescription()
      return (dict(zip(desc, row)) for row in executor.IterateAll())
    elif (self._return_type == 'tuple_flat' or
          self._return_type == 'tuple_distinct'):
      return (row[0] for row in executor.FetchAll())
    else:
      raise ValueError('Unknown return type %s in QuerySet' % self._return_type)

  def __deepcopy__(self, dummy_memo):
    ret = QuerySet.__new__(QuerySet)
    for m in ['_database', '_model', '_return_type']:
      setattr(ret, m, getattr(self, m))
    for m in ['_order', '_column_list', '_condition', '_join_select',
              '_join_on', '_annotate_dict']:
      setattr(ret, m, copy.deepcopy(getattr(self, m)))
    return ret

  def GetDatabase(self):
    return self._database

  def GetModel(self):
    return self._model

  def Values(self, *args):
    """Only selects columns in args, and make result a dict.

    Args:
      args: List of column to select. If empty, don't change the columns
            selected.
    """
    if args:
      self._column_list = args
    self._return_type = 'dict'
    return self

  def ValuesList(self, *args, **kwargs):
    """Only selects columns in args, and make result a tuple.

    Args:
      args: List of column to select. If empty, don't change the columns
            selected.
      kwargs: Options. Currently support two options:
        flat=True: When only one column selected, returned results would be
                   single values rather a one-element list.
                   e.g. return would be [1, 2, 3] instead of [(1,), (2,), (3,)]
        distinct=True: Imply flat=True, returned result would be distinct values
                       of selected column.
    """
    if args:
      self._column_list = args
    self._return_type = 'tuple'
    for k, v in kwargs.iteritems():
      if k == 'flat':
        if v:
          if len(args) != 1:
            raise ValueError('Args should contain one item when flat=True')
          self._return_type = 'tuple_flat'
      elif k == 'distinct':
        if v:
          if len(args) != 1:
            raise ValueError('Args should contain one item when distinct=True')
          self._return_type = 'tuple_distinct'
      else:
        raise ValueError('Unknown keyword argument %s in ValuesList' % k)
    return self

  def OrderBy(self, *args):
    """Orders the result by columns in args"""
    self._order = args
    return self

  def Filter(self, *args, **kwargs):
    """Selects rows that match the conditions"""
    cond = self._database.Q(**kwargs)
    for arg in args:
      cond = cond & arg
    self._condition = self._condition & cond
    return self

  def Exclude(self, *args, **kwargs):
    """Selects rows that don't match the conditions"""
    cond = self._database.Q(**kwargs)
    for arg in args:
      cond = cond & arg
    self._condition = self._condition & ~cond
    return self

  def Join(self, queryset, **kwargs):
    """Joins the result table with the provided QuerySet.

    Args:
      queryset: A QuerySet representing the SELECT statement to be joined,
                or None if there's no join.
      kwargs: A list of pair (table 1 column name, table 2 column name), JOIN
              ON when these columns are equal.
    """
    self._join_select = queryset
    self._join_on = kwargs.items()
    return self

  def Annotate(self, **kwargs):
    """Annotates the result with extra fields, would group all non-annotate
    field together.

    Args:
      kwargs: A dict like {'max_count': ('max', 'count_passed')}, indicating the
              extra annotated field's name, aggregate function, and target name.
    """
    self._annotate_dict.update(kwargs)
    return self

  def BuildQuery(self):
    """Returns the SQL statement and arguments of this query"""
    def EscapeColumnName(c):
      if self._join_select:
        return self._database.EscapeColumnName(c, 't1')
      else:
        return self._database.EscapeColumnName(c)
    args = []
    ret = 'SELECT'
    select_list = ['%s%s' % (EscapeColumnName(c),
                             ' AS ' + self._database.EscapeColumnName(c)
                             if self._join_select else '')
                   for c in self._column_list]
    if self._annotate_dict and (
        self._return_type == 'tuple_flat' or
        self._return_type == 'tuple_distinct'):
      raise ValueError(
          'There should be no Annotate() when distinct=True or flat=True')
    select_list += ['%s(%s) AS %s' % (op.upper(), EscapeColumnName(name),
                                      self._database.EscapeColumnName(k))
                    for k, (op, name) in self._annotate_dict.iteritems()]
    ret += ' ' + ','.join(select_list)
    ret += ' FROM'
    ret += ' ' + self._model.GetModelName() + ' AS t1'

    if self._join_select:
      ret += ' JOIN ('
      sql, cur_args = self._join_select.BuildQuery()
      ret += sql
      args += cur_args
      ret += ') AS t2 ON '
      ret += ' AND '.join('%s = %s' %
                          (EscapeColumnName(c1),
                           self._database.EscapeColumnName(c2, 't2'))
                          for c1, c2 in self._join_on)

    if self._condition:
      ret += ' WHERE ' + self._condition.GetSql()
      args += self._condition.GetArgs()

    if self._order:
      ret += ' ORDER BY'
      order_list = []
      for order in self._order:
        if order.startswith('-'):
          order_list.append(EscapeColumnName(order[1:]) + ' DESC')
        else:
          order_list.append(EscapeColumnName(order))
      ret += ' ' + (','.join(order_list))

    if self._annotate_dict:
      if self._return_type == 'tuple_distinct':
        raise ValueError("distinct=True and Annotate() can't be used together")
      if self._return_type == 'model':
        raise ValueError(
            'Should use Values() or ValuesList() when using Annotate()')
      ret += ' GROUP BY '
      ret += ','.join('%s' % EscapeColumnName(c) for c in self._column_list)
    elif self._return_type == 'tuple_distinct':
      ret += ' GROUP BY '
      ret += EscapeColumnName(self._column_list[0])

    return ret, tuple(args)

  def GetOne(self):
    """Gets the first model which matches the given condition."""
    sql_query, args = self.BuildQuery()
    sql_query += ' LIMIT 1'
    executor = self._database.GetExecutorFactory().NewExecutor()
    executor.Execute(sql_query, args)
    if self._return_type == 'model':
      return executor.FetchOne(model=self._model)
    elif self._return_type == 'tuple':
      return executor.FetchOne()
    elif self._return_type == 'dict':
      return dict(zip(executor.GetDescription(), executor.FetchOne()))
    elif (self._return_type == 'tuple_flat' or
          self._return_type == 'tuple_distinct'):
      return executor.FetchOne()[0]
    else:
      raise ValueError('Unknown return type %s in QuerySet' % self._return_type)

  def GetAll(self):
    """Gets all the models which match the given condition."""
    sql_query, args = self.BuildQuery()
    executor = self._database.GetExecutorFactory().NewExecutor()
    executor.Execute(sql_query, args)
    if self._return_type == 'model':
      return executor.FetchAll(model=self._model)
    elif self._return_type == 'tuple':
      return executor.FetchAll()
    elif self._return_type == 'dict':
      desc = executor.GetDescription()
      return [dict(zip(desc, row)) for row in executor.FetchAll()]
    elif (self._return_type == 'tuple_flat' or
          self._return_type == 'tuple_distinct'):
      return [row[0] for row in executor.FetchAll()]
    else:
      raise ValueError('Unknown return type %s in QuerySet' % self._return_type)

  def IterFilterIn(self, col, vals):
    """A custom generator equivalent to queryset.filter(col__in=vals)
    Used to bypass the limit of 999 records per query in sqlite.
    Query 900 items each loop, and concat the result.
    See https://code.djangoproject.com/ticket/17788 for more detail.
    """
    chunk_size = self._database.GetMaxArguments()
    for vs in _Grouper(list(vals), chunk_size):
      for v in copy.deepcopy(self).Filter(**{(col + '__in'): vs}):
        yield v


if settings.IS_APPENGINE:
  if settings.BACKEND_DATABASE == 'bigquery':
    from db.bigquery import Executor, ExecutorFactory, Database
  elif settings.BACKEND_DATABASE == 'cloud_sql':
    from db.cloud_sql import Executor, ExecutorFactory, Database
  else:
    logging.exception('Unknown database %s', settings.BACKEND_DATABASE)
    sys.exit(os.EX_DATAERR)
else:
  from db.sqlite import Executor, ExecutorFactory, Database
