# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.exporters.base import ExporterBase
from cros.factory.minijack.models import Test


class TestExporter(ExporterBase):
  """The exporter to create the Test table.

  TODO(waihong): Unit tests.
  """
  def Setup(self):
    """This method is called on Minijack start-up."""
    super(TestExporter, self).Setup()
    self._database.GetOrCreateTable(Test)

  def Handle_start_test(self, packet):
    """A handler for a start_test event."""
    row = Test(
      invocation     = packet.event.get('invocation'),
      event_id       = packet.GetEventId(),
      event_seq      = int(packet.event.get('SEQ')),
      device_id      = packet.preamble.get('device_id'),
      factory_md5sum = packet.preamble.get('factory_md5sum'),
      reimage_id     = (packet.preamble.get('reimage_id') or
                        packet.preamble.get('image_id')),
      path           = packet.event.get('path'),
      pytest_name    = packet.event.get('pytest_name'),
      start_time     = packet.event.get('TIME'),
    )
    self._database.UpdateOrInsert(row)

  def Handle_end_test(self, packet):
    """A handler for an end_test event."""
    row = Test(
      invocation     = packet.event.get('invocation'),
      event_id       = packet.GetEventId(),
      event_seq      = int(packet.event.get('SEQ')),
      device_id      = packet.preamble.get('device_id'),
      factory_md5sum = packet.preamble.get('factory_md5sum'),
      reimage_id     = (packet.preamble.get('reimage_id') or
                        packet.preamble.get('image_id')),
      path           = packet.event.get('path'),
      pytest_name    = packet.event.get('pytest_name'),
      status         = packet.event.get('status'),
      end_time       = packet.event.get('TIME'),
      duration       = packet.event.get('duration'),
      # Only keep the first line of error_msg for a quick look.
      error_msg      = packet.event.get('error_msg', '').split('\n')[0],
    )
    self._database.UpdateOrInsert(row)
