#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common
import os
import re
import unittest
import yaml

from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import event_log

MAC_RE = re.compile(r'^([a-f0-9]{2}:){5}[a-f0-9]{2}$')
UUID_RE = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-'
                     '[a-f0-9]{4}-[a-f0-9]{12}$')


class EventLogTest(unittest.TestCase):
  def testGetBootId(self):
    assert UUID_RE.match(event_log.GetBootId())

  def testGetDeviceId(self):
    device_id = event_log.GetDeviceId()
    assert (MAC_RE.match(device_id) or
            UUID_RE.match(device_id)), device_id

    # Remove device_id and make sure we get the same thing
    # back again, re-reading it from disk or the wlan0 interface
    event_log.device_id = None
    self.assertEqual(device_id, event_log.GetDeviceId())

    self.assertNotEqual(device_id, event_log.GetImageId())

  def testGetImageId(self):
    image_id = event_log.GetImageId()
    assert UUID_RE.match(image_id), image_id

    # Remove image_id and make sure we get the same thing
    # back again, re-reading it from disk
    event_log.image_id = None
    self.assertEqual(image_id, event_log.GetImageId())

    # Remove the image_id file; now we should get something
    # *different* back.
    event_log.image_id = None
    os.unlink(event_log.IMAGE_ID_PATH)
    self.assertNotEqual(image_id, event_log.GetImageId())

  def testEventLogDefer(self):
    self._testEventLog(True)

  def testEventLogNoDefer(self):
    self._testEventLog(False)

  def _testEventLog(self, defer):
    log = event_log.EventLog('test', defer=defer)
    self.assertEqual(os.path.exists(log.path), not defer)

    event0 = dict(a='A',
                  b=1,
                  c=[1,2],
                  d={'D1': 3, 'D2': 4},
                  e=['E1', {'E2': 'E3'}],
                  f=True,
                  g=u"<<<囧>>>".encode('utf-8'))
    log.Log('event0', **event0)
    log.Log('event1')
    log.Close()

    try:
      log.Log('should-fail')
      self.fail('Expected exception')
    except:
      pass

    log_data = list(yaml.load_all(open(log.path, "r")))
    self.assertEqual(4, len(log_data))

    for i in log_data[0:3]:
      # Check and remove times, to make everything else easier to compare
      assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$',
                      i['TIME']), i['TIME']
      del i['TIME']

    self.assertEqual(
      ['EVENT', 'SEQ', 'boot_id', 'device_id', 'filename', 'image_id',
       'log_id'],
      sorted(log_data[0].keys()))
    self.assertEqual('preamble', log_data[0]['EVENT'])
    self.assertEqual(0, log_data[0]['SEQ'])
    self.assertEqual(event_log.GetBootId(), log_data[0]['boot_id'])
    self.assertEqual(event_log.GetDeviceId(), log_data[0]['device_id'])
    self.assertEqual(event_log.GetImageId(), log_data[0]['image_id'])
    self.assertEqual(os.path.basename(log.path), log_data[0]['filename'])
    self.assertEqual('test-' + log_data[0]['log_id'],
                     log_data[0]['filename'])

    event0.update(dict(EVENT='event0', SEQ=1))
    self.assertEqual(event0, log_data[1])
    self.assertEqual(dict(EVENT='event1', SEQ=2), log_data[2])
    self.assertEqual(None, log_data[3])

  def testDeferWithoutEvents(self):
    log = event_log.EventLog('test', defer=True)
    path = log.path
    log.Close()
    self.assertFalse(os.path.exists(path))

if __name__ == "__main__":
    unittest.main()
