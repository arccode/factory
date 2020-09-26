#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for cros.hwid.service.appengine.hwid_api"""

import os.path
import unittest
from unittest import mock

from cros.chromeoshwid import update_checksum
from cros.factory.hwid.service.appengine import hwid_api
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import validator as v3_validator
# pylint: disable=import-error, no-name-in-module
from cros.factory.hwid.service.appengine.proto import hwid_api_messages_pb2
# pylint: enable=import-error, no-name-in-module
from cros.factory.utils import file_utils


TEST_HWID = 'Foo'
TEST_HWID_CONTENT = ('prefix\n'
                     'checksum: 1234\n'
                     'suffix\n')
EXPECTED_REPLACE_RESULT = update_checksum.ReplaceChecksum(TEST_HWID_CONTENT)
GOLDEN_HWIDV3_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata', 'v3-golden.yaml')
GOLDEN_HWIDV3_CONTENT = file_utils.ReadFile(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'testdata',
        'v3-golden.yaml'))
HWIDV3_CONTENT_SYNTAX_ERROR_CHANGE = file_utils.ReadFile(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'testdata',
        'v3-syntax-error-change.yaml'))
HWIDV3_CONTENT_SCHEMA_ERROR_CHANGE = file_utils.ReadFile(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'testdata',
        'v3-schema-error-change.yaml'))


def _MockGetAVLName(unused_category, comp_name):
  return comp_name

# pylint: disable=protected-access
class HwidApiTest(unittest.TestCase):

  def setUp(self):
    super(HwidApiTest, self).setUp()
    patcher = mock.patch('__main__.hwid_api._hwid_manager')
    self.patch_hwid_manager = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.hwid_api._goldeneye_memcache_adapter')
    self.patch_goldeneye_memcache_adapter = patcher.start()
    self.addCleanup(patcher.stop)

    self.service = hwid_api.ProtoRPCService()

  def testGetBoards(self):
    boards = {'ALPHA', 'BRAVO', 'CHARLIE'}
    self.patch_hwid_manager.GetBoards.return_value = boards

    req = hwid_api_messages_pb2.BoardsRequest()
    msg = self.service.GetBoards(req)

    self.assertEqual(
        hwid_api_messages_pb2.BoardsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, boards=sorted(boards)),
        msg)

  def testGetBoardsEmpty(self):
    boards = set()
    self.patch_hwid_manager.GetBoards.return_value = boards

    req = hwid_api_messages_pb2.BoardsRequest()
    msg = self.service.GetBoards(req)

    self.assertEqual(
        hwid_api_messages_pb2.BoardsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetBomNone(self):
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (None, None)

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.NOT_FOUND,
            error='HWID not found.'), msg)

    self.patch_hwid_manager.GetBomAndConfigless.assert_called_with(
        TEST_HWID, False)

  def testGetBomFastKnownBad(self):
    bad_hwid = "FOO TEST"

    req = hwid_api_messages_pb2.BomRequest(hwid=bad_hwid)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.KNOWN_BAD_HWID,
            error='No metadata present for the requested board: %s' % bad_hwid),
        msg)

  def testGetBomValueError(self):
    self.patch_hwid_manager.GetBomAndConfigless = mock.Mock(
        side_effect=ValueError('foo'))
    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST, error='foo'), msg)

  def testGetBomKeyError(self):
    self.patch_hwid_manager.GetBomAndConfigless = mock.Mock(
        side_effect=KeyError('foo'))
    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.NOT_FOUND, error='\'foo\''),
        msg)

  def testGetBomEmpty(self):
    bom = hwid_manager.Bom()
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetBomComponents(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'foo': 'bar',
        'baz': ['qux', 'rox']
    })
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, components=[
                hwid_api_messages_pb2.Component(name='qux',
                                                componentClass='baz'),
                hwid_api_messages_pb2.Component(name='rox',
                                                componentClass='baz'),
                hwid_api_messages_pb2.Component(name='bar',
                                                componentClass='foo'),
            ]), msg)

  def testGetBomComponentsWithVerboseFlag(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'battery': 'battery_small',
        'cpu': ['cpu_0', 'cpu_1']
    }, comp_db=database.Database.LoadFile(GOLDEN_HWIDV3_FILE,
                                          verify_checksum=False), verbose=True)
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID, verbose=True)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, components=[
                hwid_api_messages_pb2.Component(
                    name='battery_small', componentClass='battery', fields=[
                        hwid_api_messages_pb2.Field(name='size',
                                                    value='2500000'),
                        hwid_api_messages_pb2.Field(name='tech',
                                                    value='Battery Li-ion')
                    ]),
                hwid_api_messages_pb2.Component(
                    name='cpu_0', componentClass='cpu', fields=[
                        hwid_api_messages_pb2.Field(name='cores', value='4'),
                        hwid_api_messages_pb2.Field(name='name',
                                                    value='CPU @ 1.80GHz')
                    ]),
                hwid_api_messages_pb2.Component(
                    name='cpu_1', componentClass='cpu', fields=[
                        hwid_api_messages_pb2.Field(name='cores', value='4'),
                        hwid_api_messages_pb2.Field(name='name',
                                                    value='CPU @ 2.00GHz')
                    ])
            ]), msg)

  def testGetBomLabels(self):
    bom = hwid_manager.Bom()
    bom.AddAllLabels({
        'foo': {
            'bar': None
        },
        'baz': {
            'qux': '1',
            'rox': '2'
        }
    })
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, labels=[
                hwid_api_messages_pb2.Label(componentClass='foo', name='bar'),
                hwid_api_messages_pb2.Label(componentClass='baz', name='qux',
                                            value='1'),
                hwid_api_messages_pb2.Label(componentClass='baz', name='rox',
                                            value='2'),
            ]), msg)

  def testGetHwids(self):
    hwids = ['alfa', 'bravo', 'charlie']
    self.patch_hwid_manager.GetHwids.return_value = hwids

    req = hwid_api_messages_pb2.HwidsRequest(board=TEST_HWID)
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            hwids=['alfa', 'bravo', 'charlie']), msg)

  def testGetHwidsEmpty(self):
    hwids = list()
    self.patch_hwid_manager.GetHwids.return_value = hwids

    req = hwid_api_messages_pb2.HwidsRequest(board=TEST_HWID)
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetHwidsErrors(self):
    self.patch_hwid_manager.GetHwids.side_effect = ValueError('foo')

    req = hwid_api_messages_pb2.HwidsRequest(board=TEST_HWID)
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='Invalid input: %s' % TEST_HWID), msg)

    req = hwid_api_messages_pb2.HwidsRequest(board=TEST_HWID,
                                             withClasses=['foo', 'bar'],
                                             withoutClasses=['bar', 'baz'])
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='One or more component classes specified for both with and '
            'without'), msg)

    req = hwid_api_messages_pb2.HwidsRequest(board=TEST_HWID,
                                             withComponents=['foo', 'bar'],
                                             withoutComponents=['bar', 'baz'])
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='One or more components specified for both with and without'),
        msg)

  def testGetComponentClasses(self):
    classes = ['alfa', 'bravo', 'charlie']
    self.patch_hwid_manager.GetComponentClasses.return_value = classes

    req = hwid_api_messages_pb2.ComponentClassesRequest(board=TEST_HWID)
    msg = self.service.GetComponentClasses(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentClassesResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            componentClasses=['alfa', 'bravo', 'charlie']), msg)

  def testGetComponentClassesEmpty(self):
    classes = list()
    self.patch_hwid_manager.GetComponentClasses.return_value = classes

    req = hwid_api_messages_pb2.ComponentClassesRequest(board=TEST_HWID)
    msg = self.service.GetComponentClasses(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentClassesResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetComponentClassesErrors(self):
    self.patch_hwid_manager.GetComponentClasses.side_effect = ValueError('foo')
    req = hwid_api_messages_pb2.ComponentClassesRequest(board=TEST_HWID)
    msg = self.service.GetComponentClasses(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentClassesResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='Invalid input: %s' % TEST_HWID), msg)

  def testGetComponents(self):
    components = dict(uno=['alfa'], dos=['bravo'], tres=['charlie', 'delta'])

    self.patch_hwid_manager.GetComponents.return_value = components

    req = hwid_api_messages_pb2.ComponentsRequest(board=TEST_HWID)
    msg = self.service.GetComponents(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, components=[
                hwid_api_messages_pb2.Component(componentClass='uno',
                                                name='alfa'),
                hwid_api_messages_pb2.Component(componentClass='dos',
                                                name='bravo'),
                hwid_api_messages_pb2.Component(componentClass='tres',
                                                name='charlie'),
                hwid_api_messages_pb2.Component(componentClass='tres',
                                                name='delta'),
            ]), msg)

  def testGetComponentsEmpty(self):
    components = dict()

    self.patch_hwid_manager.GetComponents.return_value = components

    req = hwid_api_messages_pb2.ComponentsRequest(board=TEST_HWID)
    msg = self.service.GetComponents(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetComponentsErrors(self):
    self.patch_hwid_manager.GetComponents.side_effect = ValueError('foo')

    req = hwid_api_messages_pb2.ComponentsRequest(board=TEST_HWID)
    msg = self.service.GetComponents(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='Invalid input: %s' % TEST_HWID,
        ), msg)

  @mock.patch('cros.factory.hwid.service.appengine.hwid_api._hwid_validator')
  def testValidateConfig(self, patch_hwid_validator):
    patch_hwid_validator.Validate = mock.Mock()

    req = hwid_api_messages_pb2.ValidateConfigRequest(hwidConfigContents='test')
    msg = self.service.ValidateConfig(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  @mock.patch('cros.factory.hwid.service.appengine.hwid_api._hwid_validator')
  def testValidateConfigErrors(self, patch_hwid_validator):
    patch_hwid_validator.Validate = mock.Mock(
        side_effect=v3_validator.ValidationError('msg'))

    req = hwid_api_messages_pb2.ValidateConfigRequest(hwidConfigContents='test')
    msg = self.service.ValidateConfig(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            errorMessage='msg'), msg)

  @mock.patch('cros.factory.hwid.service.appengine.hwid_api._hwid_validator')
  def testValidateConfigAndUpdateChecksum(self, patch_hwid_validator):
    patch_hwid_validator.ValidateChange = mock.Mock()

    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwidConfigContents=TEST_HWID_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            newHwidConfigContents=EXPECTED_REPLACE_RESULT), msg)

  @mock.patch('cros.factory.hwid.service.appengine.hwid_api._hwid_validator')
  def testValidateConfigAndUpdateChecksumErrors(self, patch_hwid_validator):
    patch_hwid_validator.ValidateChange = mock.Mock(
        side_effect=v3_validator.ValidationError('msg'))

    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwidConfigContents=TEST_HWID_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            errorMessage='msg'), msg)

  def testValidateConfigAndUpdateChecksumSyntaxError(self):
    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwidConfigContents=HWIDV3_CONTENT_SYNTAX_ERROR_CHANGE,
        prevHwidConfigContents=GOLDEN_HWIDV3_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.YAML_ERROR, errorMessage=(
                'while parsing a block mapping\n'
                '  in "<unicode string>", line 73, column 3:\n'
                '      audio_codec:\n'
                '      ^\n'
                'expected <block end>, but found \'<block mapping start>\'\n'
                '  in "<unicode string>", line 103, column 7:\n'
                '          cpu: cpu_0\n'
                '          ^')), msg)

  def testValidateConfigAndUpdateChecksumSchemaError(self):
    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwidConfigContents=HWIDV3_CONTENT_SCHEMA_ERROR_CHANGE,
        prevHwidConfigContents=GOLDEN_HWIDV3_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.SCHEMA_ERROR, errorMessage=(
                '''OrderedDict([('type', OrderedDict([('SSD', 'object')])), ('''
                ''''size', '16G'), ('serial', Value('^#123\\\\d+$', is_re=Tru'''
                '''e))]) does not match any type in [Dict('probed key-value p'''
                '''airs', key_type=Scalar('probed key', <class 'str'>), value'''
                '''_type=AnyOf([Scalar('probed value', <class 'str'>), Scalar'''
                '''('probed value', <class 'bytes'>), Scalar('probed value re'''
                '''gex', <class 'cros.factory.hwid.v3.rule.Value'>)]), size=['''
                '''1, inf]), Scalar('none', <class 'NoneType'>)]''')), msg)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSku(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'cpu': ['bar1', 'bar2'],
        'dram': ['foo']
    })
    bom.board = 'foo'
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    req = hwid_api_messages_pb2.SkuRequest(hwid=TEST_HWID)
    msg = self.service.GetSku(req)

    self.assertEqual(
        hwid_api_messages_pb2.SkuResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, board='foo',
            cpu='bar1_bar2', memory='1Mb', memoryInBytes=100000000,
            sku='foo_bar1_bar2_1Mb'), msg)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSkuWithConfigless(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'cpu': ['bar1', 'bar2'],
        'dram': ['foo']
    })
    bom.board = 'foo'
    configless = {
        'memory': 4
    }
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    req = hwid_api_messages_pb2.SkuRequest(hwid=TEST_HWID)
    msg = self.service.GetSku(req)

    self.assertEqual(
        hwid_api_messages_pb2.SkuResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, board='foo',
            cpu='bar1_bar2', memory='4GB', memoryInBytes=4294967296,
            sku='foo_bar1_bar2_4GB'), msg)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSkuBadDRAM(self, mock_get_total_ram):
    mock_get_total_ram.side_effect = hwid_util.HWIDUtilException('X')
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'cpu': 'bar',
        'dram': ['fail']
    })
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    req = hwid_api_messages_pb2.SkuRequest(hwid=TEST_HWID)
    msg = self.service.GetSku(req)

    self.assertEqual(
        hwid_api_messages_pb2.SkuResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST, error='X'), msg)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSkuMissingCPU(self, mock_get_total_ram):
    mock_get_total_ram.return_value = ('2Mb', 2000000)
    bom = hwid_manager.Bom()
    bom.AddAllComponents({'dram': ['some_memory_chip', 'other_memory_chip']})
    bom.board = 'foo'
    configless = None

    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    req = hwid_api_messages_pb2.SkuRequest(hwid=TEST_HWID)
    msg = self.service.GetSku(req)

    self.assertEqual(
        hwid_api_messages_pb2.SkuResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, board='foo',
            memoryInBytes=2000000, memory='2Mb', sku='foo_None_2Mb'), msg)

  @mock.patch.object(hwid_util, 'GetSkuFromBom')
  def testGetDutLabels(self, mock_get_sku_from_bom):
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
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName

    req = hwid_api_messages_pb2.DutLabelsRequest(hwid=TEST_HWID)
    msg = self.service.GetDutLabels(req)

    self.assertTrue(self.CheckForLabelValue(msg, 'phase', 'bar'))
    self.assertTrue(self.CheckForLabelValue(msg, 'variant', 'found_device'))
    self.assertTrue(self.CheckForLabelValue(msg, 'sku', 'TestSku'))
    self.assertTrue(self.CheckForLabelValue(msg, 'touchscreen'))
    self.assertTrue(self.CheckForLabelValue(msg, 'hwid_component'))
    self.assertEqual(5, len(msg.labels))

    self.patch_goldeneye_memcache_adapter.Get.return_value = None

    req = hwid_api_messages_pb2.DutLabelsRequest(hwid=TEST_HWID)
    msg = self.service.GetDutLabels(req)

    self.assertEqual(
        hwid_api_messages_pb2.DutLabelsResponse(
            status=hwid_api_messages_pb2.Status.SERVER_ERROR,
            error='Missing Regexp List', possible_labels=[
                'hwid_component',
                'phase',
                'sku',
                'stylus',
                'touchpad',
                'touchscreen',
                'variant',
            ]), msg)

  @mock.patch.object(hwid_util, 'GetSkuFromBom')
  def testGetDutLabelsWithConfigless(self, mock_get_sku_from_bom):
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

    req = hwid_api_messages_pb2.DutLabelsRequest(hwid=TEST_HWID)
    msg = self.service.GetDutLabels(req)

    self.assertTrue(self.CheckForLabelValue(msg, 'phase', 'bar'))
    self.assertTrue(self.CheckForLabelValue(msg, 'variant', 'found_device'))
    self.assertTrue(self.CheckForLabelValue(msg, 'sku', 'TestSku'))
    self.assertTrue(self.CheckForLabelValue(msg, 'touchscreen'))
    self.assertEqual(4, len(msg.labels))

    self.patch_goldeneye_memcache_adapter.Get.return_value = None

    req = hwid_api_messages_pb2.DutLabelsRequest(hwid=TEST_HWID)
    msg = self.service.GetDutLabels(req)

    self.assertEqual(
        hwid_api_messages_pb2.DutLabelsResponse(
            status=hwid_api_messages_pb2.Status.SERVER_ERROR,
            error='Missing Regexp List', possible_labels=[
                'hwid_component',
                'phase',
                'sku',
                'stylus',
                'touchpad',
                'touchscreen',
                'variant',
            ]), msg)

  def CheckForLabelValue(self, response, label_to_check_for,
                         value_to_check_for=None):
    for label in response.labels:
      if label.name == label_to_check_for:
        if value_to_check_for and label.value != value_to_check_for:
          return False
        return True
    return False


if __name__ == '__main__':
  unittest.main()
