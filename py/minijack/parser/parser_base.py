# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.common import MakeList

class ParserBase(object):
  '''The base class of parsers.

  An parser is a customized class which analyses event logs and converts
  the knowledge into a database.

  All parser classes should inherit this ParserBase class and implement/reuse
  the following methods:
    setup(self): This method is called on Minijack start-up.
    cleanup(self): This method is called on Minijack shut-down.
    handle_xxx(self, preamble, event): This method is called when an event,
        with event id == 'xxx', is received. The preamble and event arguments
        contain the Python dict of the preamble and the event. A parser class
        contains multiple handle_xxx(). The handle_all() is special, which is
        called on every event.

  Note that all the parser module should be added into __init__.py. Otherwise,
  they are not loaded by default.

  Some naming conversions:
    module file name: xxx_parser.py
    module name: xxx_parser
    class name: XxxParser

  TODO(waihong): Unit tests.

  Properties:
    _conn: The connection object of the database.
    table: The table name in the database, only one table in a parser.
    pkey: The list of the primary keys in the table.
  '''
  def __init__(self, conn):
    self._conn = conn
    self.table = None
    self.pkey = []

  def setup(self):
    '''This method is called on Minijack start-up.'''
    pass

  def cleanup(self):
    '''This method is called on Minijack shut-down.'''
    pass

  # TODO(waihong): Move the following helper methods to a better place.

  def setup_table(self, table_name, schema_dict, primary_key=None):
    '''Configures the table information.

    Args:
      table_name: The table name in the database, only one table in a parse.
      schema_dict: A dict to descibe the table schema, i.e. keys as column
                   names while values as data types.
      primary_key: A list of the column names of the primary key.
    '''
    self.table = table_name
    if primary_key is None:
      self.pkey = []
    else:
      self.pkey = MakeList(primary_key)

    # Construct the SQL command.
    fields = [k + ' ' + v for k, v in schema_dict.iteritems()]
    if primary_key:
      fields.append('PRIMARY KEY ( %s )' % ', '.join(self.pkey))
    sql_cmd = ('CREATE TABLE IF NOT EXISTS %s ( %s )' %
               (self.table,
                ', '.join(fields)))

    logging.debug('Execute SQL command: %s;', sql_cmd)
    c = self._conn.cursor()
    c.execute(sql_cmd)
    self._conn.commit()

  def update_or_insert_row(self, update_dict):
    '''Updates the row or insert it if not exists.

    Args:
      update_dict: A dict to describe the update content, i.e. keys as column
                   names while values as the update values.
    '''
    # If there is no primary key in the table, just insert it.
    if not self.pkey:
      self.insert_row(update_dict)
      return

    # Create a condition dict containing the primary key.
    cond_dict = dict((k, v) for k, v in update_dict.iteritems()
                     if k in self.pkey)
    if None in cond_dict.itervalues():
      logging.warn('Update/insert a row without Primary key.')
      return

    # Search the primary key from the table to determine update or insert.
    if self.does_row_exist(cond_dict):
      self.update_row(update_dict)
    else:
      self.insert_row(update_dict)

  def does_row_exist(self, cond_dict):
    '''Checks if a row exists or not.

    Args:
      cond_dict: A dict to describe the checking condition, the WHERE clause,
                 i.e. keys as column names while values as the expected values.

    Returns:
      True if exists; otherwise, False.
    '''
    return bool(self.get_one_row(cond_dict, cond_dict.keys()))

  def get_one_row(self, cond_dict, select=None):
    '''Gets the first row which matches the given condition.

    Args:
      cond_dict: A dict to describe the checking condition, the WHERE clause,
                 i.e. keys as column names while values as the expected values.
      select: A list of the column names it gets, the SELECT clause.
              If not given, select all columns.

    Returns:
      A list of the content of the first matching row.
    '''
    return self.get_rows(cond_dict, select, one_row=True)

  def get_rows(self, cond_dict, select=None, one_row=False):
    '''Gets all the rows which match the given condition.

    Args:
      cond_dict: A dict to describe the checking condition, the WHERE clause,
                 i.e. keys as column names while values as the expected values.
      select: A list of the column names it gets, the SELECT clause.
              If not given, select all columns.
      one_row: True if only returns the first row; otherwise, all the rows.

    Returns:
      A list of all the matching rows.
    '''
    # Construct the SQL command.
    fields = cond_dict.keys()
    values = cond_dict.values()
    sql_cmd = ('SELECT %s FROM %s WHERE %s' %
               (', '.join(select) if select else '*',
                self.table,
                ' AND '.join([f + ' = ?' for f in fields])))

    logging.debug('Execute SQL command: %s; %s', sql_cmd, tuple(values))
    c = self._conn.cursor()
    c.execute(sql_cmd, tuple(values))
    return c.fetchone() if one_row else c.fetchall()

  def update_row(self, update_dict):
    '''Updates the row in the table.

    Args:
      update_dict: A dict to describe the update content, i.e. keys as column
                   names while values as the update values.
    '''
    # Create a primary key dict for the WHERE condition.
    pkey_dict = dict((k, v) for k, v in update_dict.iteritems()
                     if k in self.pkey)
    # Filter out all None fields.
    update_dict = dict((k, v) for k, v in update_dict.iteritems() if v)
    # Construct the SQL command.
    fields = update_dict.keys()
    values = update_dict.values()
    sql_cmd = ('UPDATE %s SET %s WHERE %s' %
               (self.table,
                ', '.join([f + ' = ?' for f in fields]),
                ' AND '.join(f + ' = ?' for f in pkey_dict.iterkeys())))
    values.extend(pkey_dict.values())

    logging.debug('Execute SQL command: %s; %s', sql_cmd, tuple(values))
    c = self._conn.cursor()
    c.execute(sql_cmd, tuple(values))
    self._conn.commit()

  def insert_row(self, insert_dict):
    '''Inserts the row into the table.

    Args:
      insert_dict: A dict to describe the insert content, i.e. keys as column
                   names while values as the insert values.
    '''
    # Filter out all None fields.
    insert_dict = dict((k, v) for k, v in insert_dict.iteritems() if v)
    # Construct the SQL command.
    fields = insert_dict.keys()
    values = insert_dict.values()
    sql_cmd = ('INSERT INTO %s ( %s ) VALUES ( %s )' %
               (self.table,
                ', '.join(fields),
                ', '.join('?' * len(fields))))

    logging.debug('Execute SQL command: %s; %s', sql_cmd, tuple(values))
    c = self._conn.cursor()
    c.execute(sql_cmd, tuple(values))
    self._conn.commit()
