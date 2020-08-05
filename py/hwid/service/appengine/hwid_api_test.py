#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros.hwid.service.appengine.hwid_api"""

import gzip
import http
import json
import unittest

# pylint: disable=import-error, no-name-in-module, wrong-import-order
import flask
from google.protobuf import json_format
import mock
# pylint: enable=import-error, no-name-in-module, wrong-import-order

from cros.factory.hwid.service.appengine import app
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.v3 import validator as v3_validator
import hwid_api_messages_pb2  # pylint: disable=import-error


TEST_HWID = 'Foo'


# pylint: disable=protected-access
class HwidApiTest(unittest.TestCase):

  def setUp(self):
    super(HwidApiTest, self).setUp()
    patcher = mock.patch('__main__.app.hwid_api._hwid_manager')
    self.patch_hwid_manager = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.app.hwid_api._hwid_validator')
    self.patch_hwid_validator = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.app.hwid_api._hwid_updater')
    self.patch_hwid_updater = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch(
        '__main__.app.hwid_api._goldeneye_memcache_adapter')
    self.patch_goldeneye_memcache_adapter = patcher.start()
    self.addCleanup(patcher.stop)

    hwid_service = app.hwid_service
    self.app = hwid_service.test_client()
    hwid_service.test_request_context().push()

  def testGetBoards(self):
    boards = {'ALPHA', 'BRAVO', 'CHARLIE'}
    self.patch_hwid_manager.GetBoards.return_value = boards

    response = self.app.get(flask.url_for('hwid_api.GetBoards'))
    msg = hwid_api_messages_pb2.BoardsResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(sorted(list(boards)), sorted(list(msg.boards)))

  def testGetBoardsEmpty(self):
    boards = set()
    self.patch_hwid_manager.GetBoards.return_value = boards

    response = self.app.get(flask.url_for('hwid_api.GetBoards'))
    msg = hwid_api_messages_pb2.BoardsResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.boards))

  def testGetBomNone(self):
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (None, None)

    response = self.app.get(flask.url_for('hwid_api.GetBom', hwid=TEST_HWID))

    self.assertEqual(response.data, b'HWID not found.')
    self.assertEqual(response.status_code, http.HTTPStatus.NOT_FOUND)

    self.patch_hwid_manager.GetBomAndConfigless.assert_called_with(TEST_HWID)

  def testGetBomValueError(self):
    self.patch_hwid_manager.GetBomAndConfigless = mock.Mock(
        side_effect=ValueError('foo'))
    response = self.app.get(flask.url_for('hwid_api.GetBom', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.BomResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('foo', msg.error)
    self.assertEqual(0, len(msg.components))
    self.assertEqual(0, len(msg.labels))
    self.assertEqual('', msg.phase)

  def testGetBomKeyError(self):
    self.patch_hwid_manager.GetBomAndConfigless = mock.Mock(
        side_effect=KeyError('foo'))
    response = self.app.get(flask.url_for('hwid_api.GetBom', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.BomResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('\'foo\'', msg.error)
    self.assertEqual(0, len(msg.components))
    self.assertEqual(0, len(msg.labels))
    self.assertEqual('', msg.phase)

  def testGetBomEmpty(self):
    bom = hwid_manager.Bom()
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetBom', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.BomResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.components))
    self.assertEqual(0, len(msg.labels))

  def testGetBomComponents(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'foo': 'bar', 'baz': ['qux', 'rox']})
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetBom', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.BomResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(3, len(msg.components))
    self.assertIn(
        hwid_api_messages_pb2.Component(name='bar', componentClass='foo'),
        msg.components)
    self.assertEqual(0, len(msg.labels))

  def testGetBomLabels(self):
    bom = hwid_manager.Bom()
    bom.AddAllLabels({'foo': {'bar': None}, 'baz': {'qux': '1', 'rox': '2'}})
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetBom', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.BomResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.components))
    self.assertEqual(3, len(msg.labels))
    self.assertIn(
        hwid_api_messages_pb2.Label(componentClass='foo', name='bar'),
        msg.labels)
    self.assertIn(
        hwid_api_messages_pb2.Label(
            componentClass='baz', name='qux', value='1'),
        msg.labels)
    self.assertIn(
        hwid_api_messages_pb2.Label(
            componentClass='baz', name='rox', value='2'),
        msg.labels)

  def testGetHwids(self):
    hwids = ['alfa', 'bravo', 'charlie']
    self.patch_hwid_manager.GetHwids.return_value = hwids

    response = self.app.get(flask.url_for('hwid_api.GetHwids', board=TEST_HWID))
    msg = hwid_api_messages_pb2.HwidsResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(3, len(msg.hwids))
    self.assertIn('alfa', msg.hwids)
    self.assertIn('bravo', msg.hwids)
    self.assertIn('charlie', msg.hwids)

  def testGetHwidsEmpty(self):
    hwids = list()
    self.patch_hwid_manager.GetHwids.return_value = hwids

    response = self.app.get(flask.url_for('hwid_api.GetHwids', board=TEST_HWID))
    msg = hwid_api_messages_pb2.HwidsResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.hwids))

  def testGetHwidsErrors(self):
    self.patch_hwid_manager.GetHwids.side_effect = ValueError('foo')

    response = self.app.get(flask.url_for('hwid_api.GetHwids', board=TEST_HWID))
    self.assertEqual(response.data, ('Invalid input: %s' % TEST_HWID).encode())
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)

    response = self.app.get(
        flask.url_for('hwid_api.GetHwids', board=TEST_HWID) + '?'
        'withClasses=foo&withClasses=bar&withoutClasses=bar&withoutClasses=baz')

    self.assertEqual(response.data, (b'One or more component classes specified '
                                     b'for both with and without'))
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)

    response = self.app.get(
        flask.url_for('hwid_api.GetHwids', board=TEST_HWID) + '?'
        'withComponents=foo&withComponents=bar&withoutComponents=bar'
        '&withoutComponents=baz')

    self.assertEqual(response.data, (b'One or more components specified for '
                                     b'both with and without'))
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)

  def testGetComponentClasses(self):
    classes = ['alfa', 'bravo', 'charlie']
    self.patch_hwid_manager.GetComponentClasses.return_value = classes

    response = self.app.get(flask.url_for('hwid_api.GetComponentClasses',
                                          board=TEST_HWID))
    msg = hwid_api_messages_pb2.ComponentClassesResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(3, len(msg.componentClasses))
    self.assertIn('alfa', msg.componentClasses)
    self.assertIn('bravo', msg.componentClasses)
    self.assertIn('charlie', msg.componentClasses)

  def testGetComponentClassesEmpty(self):
    classes = list()
    self.patch_hwid_manager.GetComponentClasses.return_value = classes

    response = self.app.get(flask.url_for('hwid_api.GetComponentClasses',
                                          board=TEST_HWID))
    msg = hwid_api_messages_pb2.ComponentClassesResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.componentClasses))

  def testGetComponentClassesErrors(self):
    self.patch_hwid_manager.GetComponentClasses.side_effect = ValueError('foo')
    response = self.app.get(flask.url_for('hwid_api.GetComponentClasses',
                                          board=TEST_HWID))
    self.assertEqual(response.data, ('Invalid input: %s' % TEST_HWID).encode())
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)

  def testGetComponents(self):
    components = dict(uno=['alfa'], dos=['bravo'], tres=['charlie', 'delta'])

    self.patch_hwid_manager.GetComponents.return_value = components

    response = self.app.get(flask.url_for('hwid_api.GetComponents',
                                          board=TEST_HWID))
    msg = hwid_api_messages_pb2.ComponentsResponse()
    json_format.Parse(response.data, msg)

    alfa = hwid_api_messages_pb2.Component(componentClass='uno', name='alfa')
    bravo = hwid_api_messages_pb2.Component(componentClass='dos', name='bravo')
    charlie = hwid_api_messages_pb2.Component(componentClass='tres',
                                              name='charlie')
    three = hwid_api_messages_pb2.Component(componentClass='tres', name='delta')

    self.assertEqual(4, len(msg.components))
    self.assertIn(alfa, msg.components)
    self.assertIn(bravo, msg.components)
    self.assertIn(charlie, msg.components)
    self.assertIn(three, msg.components)

  def testGetComponentsWithConfigless(self):
    components = dict(uno=['alfa'], dos=['bravo'], tres=['charlie', 'delta'])

    self.patch_hwid_manager.GetComponents.return_value = components

    response = self.app.get(flask.url_for('hwid_api.GetComponents',
                                          board=TEST_HWID))
    msg = hwid_api_messages_pb2.ComponentsResponse()
    json_format.Parse(response.data, msg)

    alfa = hwid_api_messages_pb2.Component(componentClass='uno', name='alfa')
    bravo = hwid_api_messages_pb2.Component(componentClass='dos', name='bravo')
    charlie = hwid_api_messages_pb2.Component(componentClass='tres',
                                              name='charlie')
    three = hwid_api_messages_pb2.Component(componentClass='tres', name='delta')

    self.assertEqual(4, len(msg.components))
    self.assertIn(alfa, msg.components)
    self.assertIn(bravo, msg.components)
    self.assertIn(charlie, msg.components)
    self.assertIn(three, msg.components)

  def testGetComponentsEmpty(self):
    components = dict()

    self.patch_hwid_manager.GetComponents.return_value = components

    response = self.app.get(flask.url_for('hwid_api.GetComponents',
                                          board=TEST_HWID))
    msg = hwid_api_messages_pb2.ComponentsResponse()
    json_format.Parse(response.data, msg)

    response = self.app.get(flask.url_for('hwid_api.GetComponents',
                                          board=TEST_HWID))
    msg = hwid_api_messages_pb2.ComponentsResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.components))

  def testGetComponentsErrors(self):
    self.patch_hwid_manager.GetComponents.side_effect = ValueError('foo')

    response = self.app.get(flask.url_for('hwid_api.GetComponents',
                                          board=TEST_HWID))

    self.assertEqual(response.data, ('Invalid input: %s' % TEST_HWID).encode())
    self.assertEqual(response.status_code, http.HTTPStatus.BAD_REQUEST)

  def testValidateConfig(self):
    self.patch_hwid_validator.Validate = mock.Mock()

    response = self.app.post(flask.url_for('hwid_api.ValidateConfig'),
                             data=dict(hwidConfigContents='test'))
    msg = hwid_api_messages_pb2.ValidateConfigResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('', msg.errorMessage)

  def testValidateConfigInGzipContentEncoding(self):
    self.patch_hwid_validator.Validate = mock.Mock()

    data = json.dumps(dict(hwidConfigContents='test')).encode()
    response = self.app.post(flask.url_for('hwid_api.ValidateConfig'),
                             data=gzip.compress(data), headers={
                                 'Content-Type': 'application/json',
                                 'Content-Encoding': 'gzip'})
    msg = hwid_api_messages_pb2.ValidateConfigResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('', msg.errorMessage)

  def testValidateConfigErrors(self):
    self.patch_hwid_validator.Validate = mock.Mock(
        side_effect=v3_validator.ValidationError('msg'))

    response = self.app.post(flask.url_for('hwid_api.ValidateConfig'),
                             data=dict(hwidConfigContents='test'))
    msg = hwid_api_messages_pb2.ValidateConfigResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('msg', msg.errorMessage)

  def testValidateConfigAndUpdateChecksum(self):
    self.patch_hwid_validator.ValidateChange = mock.Mock()
    self.patch_hwid_updater.UpdateChecksum.return_value = 'test2'

    response = self.app.post(
        flask.url_for('hwid_api.ValidateConfigAndUpdateChecksum'),
        data=dict(hwidConfigContents='test'))
    msg = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('test2', msg.newHwidConfigContents)
    self.assertEqual('', msg.errorMessage)

  def testValidateConfigAndUpdateChecksumErrors(self):
    self.patch_hwid_updater.UpdateChecksum.return_value = 'test2'
    self.patch_hwid_validator.ValidateChange = mock.Mock(
        side_effect=v3_validator.ValidationError('msg'))

    response = self.app.post(
        flask.url_for('hwid_api.ValidateConfigAndUpdateChecksum'),
        data=dict(hwidConfigContents='test'))
    msg = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('', msg.newHwidConfigContents)
    self.assertEqual('msg', msg.errorMessage)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKU(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'cpu': ['bar1', 'bar2'], 'dram': ['foo']})
    bom.board = 'foo'
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetSKU', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.SKUResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('foo', msg.board)
    self.assertEqual('bar1_bar2', msg.cpu)
    self.assertEqual('1Mb', msg.memory)
    self.assertEqual(100000000, msg.memoryInBytes)
    self.assertEqual('foo_bar1_bar2_1Mb', msg.sku)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKUWithConfigless(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'cpu': ['bar1', 'bar2'], 'dram': ['foo']})
    bom.board = 'foo'
    configless = {'memory': 4}
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetSKU', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.SKUResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('foo', msg.board)
    self.assertEqual('bar1_bar2', msg.cpu)
    self.assertEqual('4GB', msg.memory)
    self.assertEqual(4294967296, msg.memoryInBytes)
    self.assertEqual('foo_bar1_bar2_4GB', msg.sku)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKUBadDRAM(self, mock_get_total_ram):
    mock_get_total_ram.side_effect = hwid_util.HWIDUtilException('X')
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'cpu': 'bar', 'dram': ['fail']})
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetSKU', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.SKUResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('X', msg.error)
    self.assertEqual('', msg.board)
    self.assertEqual('', msg.cpu)
    self.assertEqual(0, msg.memoryInBytes)
    self.assertEqual('', msg.memory)
    self.assertEqual('', msg.sku)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKUMissingCPU(self, mock_get_total_ram):
    mock_get_total_ram.return_value = ('2Mb', 2000000)
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'dram': ['some_memory_chip', 'other_memory_chip']})
    bom.board = 'foo'
    configless = None

    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetSKU', hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.SKUResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual('foo', msg.board)
    self.assertEqual('', msg.cpu)
    self.assertEqual(2000000, msg.memoryInBytes)
    self.assertEqual('2Mb', msg.memory)
    self.assertEqual('foo_None_2Mb', msg.sku)

  @mock.patch.object(hwid_util, 'GetSkuFromBom')
  def testGetDUTLabels(self, mock_get_sku_from_bom):
    self.patch_goldeneye_memcache_adapter.Get.return_value = [
        ('r1.*', 'b1', []), ('^Fo.*', 'found_device', [])
    ]
    bom = hwid_manager.Bom()
    bom.AddComponent('touchscreen', name='testscreen', is_vp_related=True)
    bom.board = 'foo'
    bom.phase = 'bar'
    configless = None

    mock_get_sku_from_bom.return_value = {
        'sku': 'TestSku',
        'board': None,
        'cpu': None,
        'memory_str': None,
        'total_bytes': None
    }

    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetDUTLabels',
                                          hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.DUTLabelResponse()
    json_format.Parse(response.data, msg)

    self.assertTrue(self.CheckForLabelValue(msg, 'phase', 'bar'))
    self.assertTrue(
        self.CheckForLabelValue(msg, 'variant', 'found_device'))
    self.assertTrue(self.CheckForLabelValue(msg, 'sku', 'TestSku'))
    self.assertTrue(self.CheckForLabelValue(msg, 'touchscreen'))
    self.assertTrue(self.CheckForLabelValue(msg, 'hwid_component'))
    self.assertEqual(5, len(msg.labels))

    self.patch_goldeneye_memcache_adapter.Get.return_value = None

    response = self.app.get(flask.url_for('hwid_api.GetDUTLabels',
                                          hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.DUTLabelResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.labels))
    self.assertEqual('Missing Regexp List', msg.error)

  @mock.patch.object(hwid_util, 'GetSkuFromBom')
  def testGetDUTLabelsWithConfigless(self, mock_get_sku_from_bom):
    self.patch_goldeneye_memcache_adapter.Get.return_value = [
        ('r1.*', 'b1', []), ('^Fo.*', 'found_device', [])
    ]
    bom = hwid_manager.Bom()
    bom.board = 'foo'
    bom.phase = 'bar'
    configless = {'feature_list': {'has_touchscreen': 1}}
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    mock_get_sku_from_bom.return_value = {
        'sku': 'TestSku',
        'board': None,
        'cpu': None,
        'memory_str': None,
        'total_bytes': None
    }

    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.app.get(flask.url_for('hwid_api.GetDUTLabels',
                                          hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.DUTLabelResponse()
    json_format.Parse(response.data, msg)

    self.assertTrue(self.CheckForLabelValue(msg, 'phase', 'bar'))
    self.assertTrue(
        self.CheckForLabelValue(msg, 'variant', 'found_device'))
    self.assertTrue(self.CheckForLabelValue(msg, 'sku', 'TestSku'))
    self.assertTrue(self.CheckForLabelValue(msg, 'touchscreen'))
    self.assertEqual(4, len(msg.labels))

    self.patch_goldeneye_memcache_adapter.Get.return_value = None

    response = self.app.get(flask.url_for('hwid_api.GetDUTLabels',
                                          hwid=TEST_HWID))
    msg = hwid_api_messages_pb2.DUTLabelResponse()
    json_format.Parse(response.data, msg)

    self.assertEqual(0, len(msg.labels))
    self.assertEqual('Missing Regexp List', msg.error)

  def CheckForLabelValue(self,
                         response,
                         label_to_check_for,
                         value_to_check_for=None):
    for label in response.labels:
      if label.name == label_to_check_for:
        if value_to_check_for and label.value != value_to_check_for:
          return False
        return True
    return False


if __name__ == '__main__':
  unittest.main()
