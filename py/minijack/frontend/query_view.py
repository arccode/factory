# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
import json
import re
import sys
import traceback
import logging

from django.shortcuts import render
from django.http import HttpResponse

import minijack_common  # pylint: disable=W0611
from db import Database
from models import Event, Device, Attr, Test
from models import Component, ComponentDetail


def BuildTableSchemaString(schema):
  ret = []
  for field in schema['fields']:
    # Nested field
    if 'fields' in field:
      ret += [(field['name'] + '.' + f, t)
              for (f, t) in BuildTableSchemaString(field)]
    else:
      ret.append((field['name'], field['type']))
  return ret


def FormatExceptionOnly():
  """Formats the current exception string.

  Must only be called from inside an exception handler.

  Returns:
    A string.
  """
  return '\n'.join(
    traceback.format_exception_only(*sys.exc_info()[:2])).strip()


def GetQueryView(request):
  sql_query = request.GET.get('s', '')
  output = request.GET.get('output', '')
  columns = []
  results = []
  error_message = None
  usage_message = None

  if sql_query:
    sql_lower = sql_query.lower()
    pattern = 'select .*'
    matches = re.match(pattern, sql_lower)
    if matches:
      try:
        database = Database.Connect()
        executor = database.GetExecutorFactory().NewExecutor()
        executor.Execute(sql_query)
        results = executor.FetchAll()
        logging.debug(results)
        columns = executor.GetDescription()
      except:  # pylint: disable=W0702
        error_message = 'Failed to execute SQL query "%s":\n%s' % (
            sql_query, FormatExceptionOnly())
    else:
      error_message = 'Not a valid select statement "%s"' % sql_query
  else:
    # TODO(pihsun): Fix schemas message when using BigQuery
    usage_message = ('<p>Type the SQL select statement in the above box. '
        'Table schemas:</p>')
    for model in (Event, Attr, Test, Device, Component, ComponentDetail):
      usage_message += ('<p>' +
          ' '.join([w if w.isupper() else '<b>' + w + '</b>'
            for w in model.SqlCmdCreateTable().split(' ')]) +
          '</p>\n')

  if output.lower() == 'json':
    return HttpResponse(json.dumps(results), content_type="application/json")
  else:
    context = {
      'sql_query': sql_query,
      'column_list': columns,
      'result_list': results,
      'error_message': error_message,
      'usage_message': usage_message,
    }
    return render(request, 'query_life.html', context)
