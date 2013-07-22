# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import re

from django.http import HttpResponse
from django.template import Context, loader

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import db
from cros.factory.minijack.frontend import settings
from cros.factory.minijack.models import Event, Attr, Test, Device
from cros.factory.minijack.models import Component, ComponentDetail
from cros.factory.test import utils


MINIJACK_DB = settings.DATABASES['default']['NAME']


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
        database = db.Database()
        database.Init(MINIJACK_DB)

        executor = database.GetExecutorFactory().NewExecutor()
        executor.Execute(sql_query)
        results = executor.FetchAll()
        columns = executor.GetDescription()
      except:  # pylint: disable=W0702
        error_message = 'Failed to execute SQL query "%s":\n%s' % (
            sql_query, utils.FormatExceptionOnly())
    else:
      error_message = 'Not a valid select statement "%s"' % sql_query

  else:
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
    template = loader.get_template('query_life.html')
    context = Context({
      'sql_query': sql_query,
      'column_list': columns,
      'result_list': results,
      'error_message': error_message,
      'usage_message': usage_message,
    })
    return HttpResponse(template.render(context))
