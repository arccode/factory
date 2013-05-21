#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.datatypes import EventPacket
from cros.factory.minijack.datatypes import GenerateEventStreamsFromYaml


_YAML_STR = """EVENT: preamble
LOG_ID: ca5d4c0c-36c9-4473-bdae-3393553ed0c8
PREFIX: GoogleRequiredTests.Finalize
SEQ: 3622
TIME: '2013-04-08T03:16:23.250Z'
boot_id: 855b3e77-730a-4689-bbe5-6e64dbaeb939
boot_sequence: 74
device_id: d0:xx:xx:xx:xx:df
factory_md5sum: 73611df4926a2e63aed0e95993b81492
image_id: 1af4675a-b4cd-4f1f-9a4d-a28d402ed81b
log_id: ca5d4c0c-36c9-4473-bdae-3393553ed0c8
---
EVENT: test_states
LOG_ID: ca5d4c0c-36c9-4473-bdae-3393553ed0c8
PREFIX: GoogleRequiredTests.Finalize
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
LOG_ID: ca5d4c0c-36c9-4473-bdae-3393553ed0c8
PREFIX: GoogleRequiredTests.Finalize
SEQ: 3624
TIME: '2013-04-08T03:16:39.156Z'
waived_tests: []
---
EVENT: preamble
LOG_ID: e01b3506-04bd-45c7-9e69-635d157d0255
PREFIX: SMT.Start
SEQ: 1003625
TIME: '2013-05-20T08:30:57.184Z'
boot_id: b3cfd577-27b1-4879-bdd2-2cc53a9fcb1a
boot_sequence: 0
device_id: d0:xx:xx:xx:xx:df
factory_md5sum: 3f69297518adc2729ad0e9176995951c
reimage_id: e01b34ff-e2b9-4778-9b25-d970624c7411
---
EVENT: factory_installed
LOG_ID: e01b3506-04bd-45c7-9e69-635d157d0255
PREFIX: SMT.Start
SEQ: 1003626
TIME: '2013-05-20T08:30:57.216Z'
ro_version: xxxxxx_v1.4.35-a8ac50f
rw_version: xxxxxx_v1.4.35-a8ac50f
---
"""

class EventStreamTest(unittest.TestCase):
  def setUp(self):
    self._yaml_str_list = _YAML_STR.split('\n')

  def testGenerateEventStreamsFromYaml(self):
    yaml_str = '\n'.join(self._yaml_str_list)
    streams = GenerateEventStreamsFromYaml(None, yaml_str)
    stream = next(streams, None)
    self.assertEqual('d0:xx:xx:xx:xx:df', stream.preamble['device_id'])
    self.assertEqual(2, len(stream))
    self.assertEqual('test_states', stream[0]['EVENT'])
    self.assertEqual(3, len(stream[0]['test_states']))
    self.assertEqual(2, len(stream[0]['test_states']['subtests']))
    self.assertEqual(3, len(stream[0]['test_states']['subtests'][0]))
    self.assertEqual('SMT', stream[0]['test_states']['subtests'][0]['id'])
    self.assertEqual(3624, stream[1]['SEQ'])
    self.assertListEqual([], stream[1]['waived_tests'])
    stream = next(streams, None)
    self.assertEqual('d0:xx:xx:xx:xx:df', stream.preamble['device_id'])
    self.assertEqual(1, len(stream))
    stream = next(streams, None)
    self.assertIs(None, stream)

  def testMissingEvent(self):
    self._yaml_str_list.remove('EVENT: test_states')
    yaml_str = '\n'.join(self._yaml_str_list)
    stream = next(GenerateEventStreamsFromYaml(None, yaml_str), None)
    self.assertEqual('d0:xx:xx:xx:xx:df', stream.preamble['device_id'])
    self.assertEqual(1, len(stream))

  def testMissingPreamble(self):
    # Drop the preamble event
    yaml_str = '\n'.join(self._yaml_str_list[11:])
    stream = next(GenerateEventStreamsFromYaml(None, yaml_str), None)
    self.assertIs(None, stream.preamble)
    self.assertEqual(2, len(stream))

  def testMissingPreambleEvent(self):
    self._yaml_str_list.remove('EVENT: preamble')
    yaml_str = '\n'.join(self._yaml_str_list)
    stream = next(GenerateEventStreamsFromYaml(None, yaml_str), None)
    self.assertIs(None, stream.preamble)
    self.assertEqual(2, len(stream))

  def testWrongYAML(self):
    self._yaml_str_list.remove('  - id: SMT')
    yaml_str = '\n'.join(self._yaml_str_list)
    stream = next(GenerateEventStreamsFromYaml(None, yaml_str), None)
    self.assertEqual('d0:xx:xx:xx:xx:df', stream.preamble['device_id'])
    self.assertEqual(0, len(stream))


class EventPacketTest(unittest.TestCase):
  def setUp(self):
    yaml_str = _YAML_STR
    self._stream = next(GenerateEventStreamsFromYaml(None, yaml_str), None)

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
    self.assertEqual(39, len(flattened))
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
