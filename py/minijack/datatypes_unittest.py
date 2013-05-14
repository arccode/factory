#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.datatypes import EventStream, EventPacket


_YAML_STR_EXAMPLE = """EVENT: preamble
SEQ: 3622
TIME: '2013-04-08T03:16:23.250Z'
boot_id: 855b3e77-730a-4689-bbe5-6e64dbaeb939
boot_sequence: 74
device_id: d0:xx:xx:xx:xx:df
factory_md5sum: 73611df4926a2e63aed0e95993b81492
filename: GoogleRequiredTests.Finalize-ca5d4c0c-36c9-4473-bdae-3393553ed0c8
image_id: 1af4675a-b4cd-4f1f-9a4d-a28d402ed81b
log_id: ca5d4c0c-36c9-4473-bdae-3393553ed0c8
---
EVENT: test_states
SEQ: 3623
TIME: '2013-04-08T03:16:23.327Z'
test_states:
  id: null
  path: null
  subtests:
  - id: SMT
    path: SMT
    subtests:
    - count: 1
      error_msg: null
      id: Start
      path: SMT.Start
      status: PASSED
    - id: ShopFloor1
      path: SMT.ShopFloor1
      subtests:
      - count: 2
        error_msg: null
        id: SyncShopFloor
        path: SMT.ShopFloor1.SyncShopFloor
        status: PASSED
    - count: 1
      error_msg: null
      id: CheckeMMCFirmwareVersion
      path: SMT.CheckeMMCFirmwareVersion
      tag: Special.Watermark
      status: PASSED
  - id: FATP
    path: FATP
    subtests:
    - count: 1
      error_msg: null
      id: Start
      path: FATP.Start
      status: PASSED
    - count: 1
      error_msg: null
      id: VerifyTouchDeviceFirmware
      path: FATP.VerifyTouchDeviceFirmware
      status: PASSED
---
EVENT: waived_tests
SEQ: 3624
TIME: '2013-04-08T03:16:39.156Z'
waived_tests: []
---
"""


class EventStreamTest(unittest.TestCase):
  def setUp(self):
    self._yaml_str_list = _YAML_STR_EXAMPLE.split('\n')

  def testLoadFromYaml(self):
    yaml_str = '\n'.join(self._yaml_str_list)
    stream = EventStream(None, yaml_str)
    self.assertEqual('d0:xx:xx:xx:xx:df', stream.preamble['device_id'])
    self.assertEqual(2, len(stream))
    self.assertEqual('test_states', stream[0]['EVENT'])
    self.assertEqual(3, len(stream[0]['test_states']))
    self.assertEqual(2, len(stream[0]['test_states']['subtests']))
    self.assertEqual(3, len(stream[0]['test_states']['subtests'][0]))
    self.assertEqual('SMT', stream[0]['test_states']['subtests'][0]['id'])
    self.assertEqual(3624, stream[1]['SEQ'])
    self.assertListEqual([], stream[1]['waived_tests'])

  def testMissingEvent(self):
    self._yaml_str_list.remove('EVENT: test_states')
    yaml_str = '\n'.join(self._yaml_str_list)
    stream = EventStream(None, yaml_str)
    self.assertEqual('d0:xx:xx:xx:xx:df', stream.preamble['device_id'])
    self.assertEqual(1, len(stream))

  def testMissingPreamble(self):
    yaml_str = '\n'.join(self._yaml_str_list[11:])  # drop the preamble event
    stream = EventStream(None, yaml_str)
    self.assertIs(None, stream.preamble)
    self.assertEqual(2, len(stream))

  def testMissingPreambleEvent(self):
    self._yaml_str_list.remove('EVENT: preamble')
    yaml_str = '\n'.join(self._yaml_str_list)
    stream = EventStream(None, yaml_str)
    self.assertIs(None, stream.preamble)
    self.assertEqual(2, len(stream))

  def testWrongYAML(self):
    self._yaml_str_list.remove('  - id: SMT')
    yaml_str = '\n'.join(self._yaml_str_list)
    stream = EventStream(None, yaml_str)
    self.assertEqual('d0:xx:xx:xx:xx:df', stream.preamble['device_id'])
    self.assertEqual(0, len(stream))


class EventPacketTest(unittest.TestCase):
  def setUp(self):
    yaml_str = _YAML_STR_EXAMPLE
    self._stream = EventStream(None, yaml_str)

  def testEventPacket(self):
    packet = EventPacket(None, self._stream.preamble, self._stream[0])
    self.assertEqual('d0:xx:xx:xx:xx:df', packet.preamble['device_id'])
    self.assertEqual('test_states', packet.event['EVENT'])

  def testEventId(self):
    packet = EventPacket(None, self._stream.preamble, self._stream[0])
    self.assertEqual('GvRnWrTNTx-aTaKNQC7YGwAAAOJw', packet.GetEventId())

  def testFlattenAttr(self):
    packet = EventPacket(None, self._stream.preamble, self._stream[0])
    generator = EventPacket.FlattenAttr(packet.event)
    flattened = dict((k, v) for k, v in generator)
    self.assertEqual(37, len(flattened))
    self.assertIn('test_states.id', flattened)
    self.assertNotIn('test_states.subtests', flattened)
    self.assertNotIn('test_states.subtests.0', flattened)
    self.assertIn('test_states.subtests.0.id', flattened)
    self.assertEqual('SMT', flattened['test_states.subtests.0.id'])
    self.assertIn('test_states.subtests.0.subtests.1.subtests.0.id', flattened)
    self.assertEqual('SyncShopFloor',
        flattened['test_states.subtests.0.subtests.1.subtests.0.id'])

  def testFindAttrContainingKey(self):
    packet = EventPacket(None, self._stream.preamble, self._stream[0])
    attr_dict = packet.FindAttrContainingKey('tag')
    self.assertEqual(6, len(attr_dict))
    self.assertIn('tag', attr_dict)
    self.assertIn('path', attr_dict)
    self.assertIn('SMT.CheckeMMCFirmwareVersion', attr_dict['path'])


if __name__ == "__main__":
  logging.disable(logging.ERROR)
  unittest.main()
