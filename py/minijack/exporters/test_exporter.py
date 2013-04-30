# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack import model
from cros.factory.minijack.exporters import exporter_base

class TestExporter(exporter_base.ExporterBase):
  '''The exporter to create the Test table.

  TODO(waihong): Unit tests.
  '''
  def __init__(self, database):
    super(TestExporter, self).__init__(database)
    self._table = None

  def Setup(self):
    '''This method is called on Minijack start-up.'''
    super(TestExporter, self).Setup()
    self._table = self._database.GetOrCreateTable(model.Test)

  def Handle_start_test(self, preamble, event):
    '''A handler for a start_test event.'''
    row = model.Test(
      invocation     = event.get('invocation'),
      device_id      = preamble.get('device_id'),
      factory_md5sum = preamble.get('factory_md5sum'),
      image_id       = preamble.get('image_id'),
      path           = event.get('path'),
      pytest_name    = event.get('pytest_name'),
      start_time     = event.get('TIME'),
    )
    self._table.UpdateOrInsertRow(row)

  def Handle_end_test(self, preamble, event):
    '''A handler for an end_test event.'''
    row = model.Test(
      invocation     = event.get('invocation'),
      device_id      = preamble.get('device_id'),
      factory_md5sum = preamble.get('factory_md5sum'),
      image_id       = preamble.get('image_id'),
      path           = event.get('path'),
      pytest_name    = event.get('pytest_name'),
      status         = event.get('status'),
      end_time       = event.get('TIME'),
      duration       = event.get('duration'),
      dargs          = event.get('dargs'),
    )
    self._table.UpdateOrInsertRow(row)
