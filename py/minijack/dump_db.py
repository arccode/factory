#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This program dumps all datas in a local sqlite database into device.json,
test.json, event.json and component.json that are suitable to be imported to
Google BigQuery using the schemas in schemas/.

To use it, invoke as a standalone program:
  ./dump_db.py [options]
"""

import json
import logging

import minijack_common  # pylint: disable=W0611
import db
from models import ComponentDetail
from models import Device, Test, Component
from models import Event, Attr


def Main():
  logging.basicConfig(level=logging.INFO)
  database = db.Database.Connect()

  logging.info('Dumping Device.')
  with open('device.json', 'w') as f:
    for d in database(Device).Values():
      json.dump(d, f, separators=(',', ':'), sort_keys=True)
      f.write('\n')

  logging.info('Dumping Test.')
  with open('test.json', 'w') as f:
    for t in database(Test).Values():
      json.dump(t, f, separators=(',', ':'), sort_keys=True)
      f.write('\n')

  ATTR_LENGTH_LIMIT = 100000
  logging.info('Dumping Event.')
  with open('event.json', 'w') as f:
    for e in database(Event).Values():
      e['attrs'] = []
      for a in database(Attr).Filter(event_id=e['event_id']).Values():
        e['attrs'].append(dict((k, v[:ATTR_LENGTH_LIMIT])
                               for k, v in a.iteritems()
                               if k != 'event_id'))
      json.dump(e, f, separators=(',', ':'), sort_keys=True)
      f.write('\n')

  logging.info('Dumping Component.')
  with open('component.json', 'w') as f:
    for c in database(Component).Values():
      c['details'] = []
      for cd in database(ComponentDetail).Filter(
          device_id=c['device_id'],
          component_class=c['component_class']).Values():
        c['details'].append(dict((k, v[:ATTR_LENGTH_LIMIT])
                               for k, v in cd.iteritems()
                               if k != 'device_id' and k != 'component_class'))
      json.dump(c, f, separators=(',', ':'), sort_keys=True)
      f.write('\n')


if __name__ == "__main__":
  Main()
