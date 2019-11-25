#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros.hwid.service.appengine.hwid_api"""

import unittest

# pylint: disable=import-error, no-name-in-module
import endpoints
import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import hwid_api
from cros.factory.hwid.service.appengine import hwid_api_messages
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.v3 import validator as v3_validator


TEST_HWID = 'Foo'


# pylint: disable=protected-access
class HwidApiTest(unittest.TestCase):

  def setUp(self):
    CONFIG.hwid_manager = mock.Mock()
    self.api = hwid_api.HwidApi()

  def testGetBoards(self):
    request = hwid_api_messages.BoardsRequest()
    boards = {'ALPHA', 'BRAVO', 'CHARLIE'}
    CONFIG.hwid_manager.GetBoards.return_value = boards

    response = self.api.GetBoards(request)

    self.assertEqual(sorted(list(boards)), sorted(list(response.boards)))

  def testGetBoardsEmpty(self):
    request = hwid_api_messages.BoardsRequest()
    boards = set()
    CONFIG.hwid_manager.GetBoards.return_value = boards

    response = self.api.GetBoards(request)

    self.assertEqual(0, len(response.boards))

  def testGetBomNone(self):
    request = hwid_api.HwidApi.GET_BOM_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    CONFIG.hwid_manager.GetBomAndConfigless = mock.Mock(
        return_value=(None, None))

    self.assertRaises(endpoints.NotFoundException, self.api.GetBom, request)

    CONFIG.hwid_manager.GetBomAndConfigless.assert_called_with(TEST_HWID)

  def testGetBomValueError(self):
    request = hwid_api.HwidApi.GET_BOM_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    CONFIG.hwid_manager.GetBomAndConfigless = mock.Mock(
        side_effect=ValueError('foo'))
    response = self.api.GetBom(request)
    self.assertEqual('foo', response.error)
    self.assertEqual([], response.components)
    self.assertEqual([], response.labels)
    self.assertIsNone(response.phase)

  def testGetBomKeyError(self):
    request = hwid_api.HwidApi.GET_BOM_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    CONFIG.hwid_manager.GetBomAndConfigless = mock.Mock(
        side_effect=KeyError('foo'))
    response = self.api.GetBom(request)
    self.assertEqual('\'foo\'', response.error)
    self.assertEqual([], response.components)
    self.assertEqual([], response.labels)
    self.assertIsNone(response.phase)

  def testGetBomEmpty(self):
    request = hwid_api.HwidApi.GET_BOM_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    bom = hwid_manager.Bom()
    configless = None
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetBom(request)

    self.assertEqual(0, len(response.components))
    self.assertEqual(0, len(response.labels))

  def testGetBomComponents(self):
    request = hwid_api.HwidApi.GET_BOM_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'foo': 'bar', 'baz': ['qux', 'rox']})
    configless = None
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetBom(request)

    self.assertEqual(3, len(response.components))
    self.assertIn(
        hwid_api_messages.Component(name='bar', componentClass='foo'),
        response.components)
    self.assertEqual(0, len(response.labels))

  def testGetBomLabels(self):
    request = hwid_api.HwidApi.GET_BOM_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    bom = hwid_manager.Bom()
    bom.AddAllLabels({'foo': {'bar': None}, 'baz': {'qux': '1', 'rox': '2'}})
    configless = None
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetBom(request)

    self.assertEqual(0, len(response.components))
    self.assertEqual(3, len(response.labels))
    self.assertIn(
        hwid_api_messages.Label(componentClass='foo', name='bar'),
        response.labels)
    self.assertIn(
        hwid_api_messages.Label(componentClass='baz', name='qux', value='1'),
        response.labels)
    self.assertIn(
        hwid_api_messages.Label(componentClass='baz', name='rox', value='2'),
        response.labels)

  def testGetHwids(self):
    request = hwid_api.HwidApi.GET_HWIDS_REQUEST.combined_message_class(
        board=TEST_HWID)
    hwids = ['alfa', 'bravo', 'charlie']
    CONFIG.hwid_manager.GetHwids.return_value = hwids

    response = self.api.GetHwids(request)

    self.assertEqual(3, len(response.hwids))
    self.assertIn('alfa', response.hwids)
    self.assertIn('bravo', response.hwids)
    self.assertIn('charlie', response.hwids)

  def testGetHwidsEmpty(self):
    request = hwid_api.HwidApi.GET_HWIDS_REQUEST.combined_message_class(
        board=TEST_HWID)
    hwids = list()
    CONFIG.hwid_manager.GetHwids.return_value = hwids

    response = self.api.GetHwids(request)

    self.assertEqual(0, len(response.hwids))

  def testGetHwidsErrors(self):
    request = hwid_api.HwidApi.GET_HWIDS_REQUEST.combined_message_class(
        board=TEST_HWID)
    CONFIG.hwid_manager.GetHwids = mock.Mock(side_effect=ValueError('foo'))
    self.assertRaises(endpoints.BadRequestException, self.api.GetHwids, request)

    CONFIG.hwid_manager.GetHwids.return_value = []

    request = hwid_api.HwidApi.GET_HWIDS_REQUEST.combined_message_class(
        board=TEST_HWID,
        withClasses=['foo', 'bar'],
        withoutClasses=['bar', 'baz'])
    self.assertRaises(endpoints.BadRequestException, self.api.GetHwids, request)

    request = request = (
        hwid_api.HwidApi.GET_HWIDS_REQUEST.combined_message_class(
            board=TEST_HWID,
            withComponents=['foo', 'bar'],
            withoutComponents=['bar', 'baz']))
    self.assertRaises(endpoints.BadRequestException, self.api.GetHwids, request)

  def testGetComponentClasses(self):
    request = (
        hwid_api.HwidApi.GET_COMPONENT_CLASSES_REQUEST.combined_message_class(
            board=TEST_HWID))
    classes = ['alfa', 'bravo', 'charlie']
    CONFIG.hwid_manager.GetComponentClasses.return_value = classes

    response = self.api.GetComponentClasses(request)

    self.assertEqual(3, len(response.componentClasses))
    self.assertIn('alfa', response.componentClasses)
    self.assertIn('bravo', response.componentClasses)
    self.assertIn('charlie', response.componentClasses)

  def testGetComponentClassesEmpty(self):
    request = (
        hwid_api.HwidApi.GET_COMPONENT_CLASSES_REQUEST.combined_message_class(
            board=TEST_HWID))
    classes = list()
    CONFIG.hwid_manager.GetComponentClasses.return_value = classes

    response = self.api.GetComponentClasses(request)

    self.assertEqual(0, len(response.componentClasses))

  def testGetComponentClassesErrors(self):
    request = (
        hwid_api.HwidApi.GET_COMPONENT_CLASSES_REQUEST.combined_message_class(
            board=TEST_HWID))
    CONFIG.hwid_manager.GetComponentClasses = (
        mock.Mock(side_effect=ValueError('foo')))
    self.assertRaises(endpoints.BadRequestException,
                      self.api.GetComponentClasses, request)

  def testGetComponents(self):
    request = hwid_api.HwidApi.GET_COMPONENTS_REQUEST.combined_message_class(
        board=TEST_HWID)

    components = dict(uno=['alfa'], dos=['bravo'], tres=['charlie', 'delta'])
    alfa = hwid_api_messages.Component(componentClass='uno', name='alfa')
    bravo = hwid_api_messages.Component(componentClass='dos', name='bravo')
    charlie = hwid_api_messages.Component(componentClass='tres', name='charlie')
    three = hwid_api_messages.Component(componentClass='tres', name='delta')

    CONFIG.hwid_manager.GetComponents.return_value = components

    response = self.api.GetComponents(request)

    self.assertEqual(4, len(response.components))
    self.assertIn(alfa, response.components)
    self.assertIn(bravo, response.components)
    self.assertIn(charlie, response.components)
    self.assertIn(three, response.components)

  def testGetComponentsWithConfigless(self):
    request = hwid_api.HwidApi.GET_COMPONENTS_REQUEST.combined_message_class(
        board=TEST_HWID)

    components = dict(uno=['alfa'], dos=['bravo'], tres=['charlie', 'delta'])
    alfa = hwid_api_messages.Component(componentClass='uno', name='alfa')
    bravo = hwid_api_messages.Component(componentClass='dos', name='bravo')
    charlie = hwid_api_messages.Component(componentClass='tres', name='charlie')
    three = hwid_api_messages.Component(componentClass='tres', name='delta')

    CONFIG.hwid_manager.GetComponents.return_value = components

    response = self.api.GetComponents(request)

    self.assertEqual(4, len(response.components))
    self.assertIn(alfa, response.components)
    self.assertIn(bravo, response.components)
    self.assertIn(charlie, response.components)
    self.assertIn(three, response.components)

  def testGetComponentsEmpty(self):
    request = hwid_api.HwidApi.GET_COMPONENTS_REQUEST.combined_message_class(
        board=TEST_HWID)
    components = dict()
    CONFIG.hwid_manager.GetComponents.return_value = components

    response = self.api.GetComponents(request)

    self.assertEqual(0, len(response.components))

  def testGetComponentsErrors(self):
    request = hwid_api.HwidApi.GET_COMPONENTS_REQUEST.combined_message_class(
        board=TEST_HWID)
    CONFIG.hwid_manager.GetComponents = mock.Mock(side_effect=ValueError('foo'))
    self.assertRaises(endpoints.BadRequestException, self.api.GetComponents,
                      request)

  def testValidateConfig(self):
    request = hwid_api_messages.ValidateConfigRequest(hwidConfigContents='test')
    self.api._hwid_validator.Validate = mock.Mock()

    response = self.api.ValidateConfig(request)

    self.assertEqual(None, response.errorMessage)

  def testValidateConfigErrors(self):
    request = hwid_api_messages.ValidateConfigRequest(hwidConfigContents='test')
    self.api._hwid_validator.Validate = mock.Mock(
        side_effect=v3_validator.ValidationError('msg'))

    response = self.api.ValidateConfig(request)

    self.assertEqual('msg', response.errorMessage)

  def testValidateConfigAndUpdateChecksum(self):
    request = hwid_api_messages.ValidateConfigAndUpdateChecksumRequest(
        hwidConfigContents='test')
    self.api._hwid_validator.ValidateChange = mock.Mock()
    self.api._hwid_updater.UpdateChecksum = mock.Mock()
    self.api._hwid_updater.UpdateChecksum.return_value = 'test2'

    response = self.api.ValidateConfigAndUpdateChecksum(request)

    self.assertEqual('test2', response.newHwidConfigContents)
    self.assertEqual(None, response.errorMessage)

  def testValidateConfigAndUpdateChecksumErrors(self):
    request = hwid_api_messages.ValidateConfigAndUpdateChecksumRequest(
        hwidConfigContents='test')
    self.api._hwid_validator.ValidateChange = mock.Mock(
        side_effect=v3_validator.ValidationError('msg'))
    self.api._hwid_updater.UpdateChecksum = mock.Mock()
    self.api._hwid_updater.UpdateChecksum.return_value = 'test2'

    response = self.api.ValidateConfigAndUpdateChecksum(request)

    self.assertEqual(None, response.newHwidConfigContents)
    self.assertEqual('msg', response.errorMessage)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKU(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    request = hwid_api.HwidApi.GET_SKU_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'cpu': ['bar1', 'bar2'], 'dram': ['foo']})
    bom.board = 'foo'
    configless = None
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetSKU(request)

    self.assertEqual('foo', response.board)
    self.assertEqual('bar1_bar2', response.cpu)
    self.assertEqual('1Mb', response.memory)
    self.assertEqual(100000000, response.memoryInBytes)
    self.assertEqual('foo_bar1_bar2_1Mb', response.sku)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKUWithConfigless(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    request = hwid_api.HwidApi.GET_SKU_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'cpu': ['bar1', 'bar2'], 'dram': ['foo']})
    bom.board = 'foo'
    configless = {'memory': 4}
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetSKU(request)

    self.assertEqual('foo', response.board)
    self.assertEqual('bar1_bar2', response.cpu)
    self.assertEqual('4GB', response.memory)
    self.assertEqual(4294967296, response.memoryInBytes)
    self.assertEqual('foo_bar1_bar2_4GB', response.sku)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKUBadDRAM(self, mock_get_total_ram):
    mock_get_total_ram.side_effect = hwid_util.HWIDUtilException('X')
    request = hwid_api.HwidApi.GET_SKU_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'cpu': 'bar', 'dram': ['fail']})
    configless = None
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
    response = self.api.GetSKU(request)
    self.assertEqual('X', response.error)
    self.assertIsNone(response.board)
    self.assertIsNone(response.cpu)
    self.assertIsNone(response.memoryInBytes)
    self.assertIsNone(response.memory)
    self.assertIsNone(response.sku)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSKUMissingCPU(self, mock_get_total_ram):
    mock_get_total_ram.return_value = ('2Mb', 2000000)
    request = hwid_api.HwidApi.GET_SKU_REQUEST.combined_message_class(
        hwid=TEST_HWID)
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'dram': ['some_memory_chip', 'other_memory_chip']})
    bom.board = 'foo'
    configless = None

    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetSKU(request)

    self.assertEqual('foo', response.board)
    self.assertEqual(None, response.cpu)
    self.assertEqual(2000000, response.memoryInBytes)
    self.assertEqual('2Mb', response.memory)
    self.assertEqual('foo_None_2Mb', response.sku)

  @mock.patch.object(hwid_util, 'GetSkuFromBom')
  def testGetDUTLabels(self, mock_get_sku_from_bom):
    self.api._goldeneye_memcache_adaptor = mock.MagicMock()
    self.api._goldeneye_memcache_adaptor.Get.return_value = [
        ('r1.*', 'b1', []), ('^Fo.*', 'found_device', [])
    ]
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'touchscreen': ['testscreen']})
    bom.board = 'foo'
    bom.phase = 'bar'
    configless = None
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
    request = hwid_api.HwidApi.GET_DUTLABEL_REQUEST.combined_message_class(
        hwid=TEST_HWID)

    mock_get_sku_from_bom.return_value = {
        'sku': 'TestSku',
        'board': None,
        'cpu': None,
        'memory_str': None,
        'total_bytes': None
    }

    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetDUTLabels(request)

    self.assertTrue(self.CheckForLabelValue(response, 'phase', 'bar'))
    self.assertTrue(
        self.CheckForLabelValue(response, 'variant', 'found_device'))
    self.assertTrue(self.CheckForLabelValue(response, 'sku', 'TestSku'))
    self.assertTrue(self.CheckForLabelValue(response, 'touchscreen'))
    self.assertEqual(4, len(response.labels))

    self.api._goldeneye_memcache_adaptor.Get.return_value = None

    response = self.api.GetDUTLabels(request)
    self.assertEqual(0, len(response.labels))
    self.assertEqual('Missing Regexp List', response.error)

  @mock.patch.object(hwid_util, 'GetSkuFromBom')
  def testGetDUTLabelsWithConfigless(self, mock_get_sku_from_bom):
    self.api._goldeneye_memcache_adaptor = mock.MagicMock()
    self.api._goldeneye_memcache_adaptor.Get.return_value = [
        ('r1.*', 'b1', []), ('^Fo.*', 'found_device', [])
    ]
    bom = hwid_manager.Bom()
    bom.board = 'foo'
    bom.phase = 'bar'
    configless = {'feature_list': {'has_touchscreen': 1}}
    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
    request = hwid_api.HwidApi.GET_DUTLABEL_REQUEST.combined_message_class(
        hwid=TEST_HWID)

    mock_get_sku_from_bom.return_value = {
        'sku': 'TestSku',
        'board': None,
        'cpu': None,
        'memory_str': None,
        'total_bytes': None
    }

    CONFIG.hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    response = self.api.GetDUTLabels(request)

    self.assertTrue(self.CheckForLabelValue(response, 'phase', 'bar'))
    self.assertTrue(
        self.CheckForLabelValue(response, 'variant', 'found_device'))
    self.assertTrue(self.CheckForLabelValue(response, 'sku', 'TestSku'))
    self.assertTrue(self.CheckForLabelValue(response, 'touchscreen'))
    self.assertEqual(4, len(response.labels))

    self.api._goldeneye_memcache_adaptor.Get.return_value = None

    response = self.api.GetDUTLabels(request)
    self.assertEqual(0, len(response.labels))
    self.assertEqual('Missing Regexp List', response.error)

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
