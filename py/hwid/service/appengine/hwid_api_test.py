#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for cros.hwid.service.appengine.hwid_api"""

import os.path
import textwrap
import unittest
from unittest import mock

from cros.chromeoshwid import update_checksum
from cros.factory.hwid.service.appengine import hwid_api
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_repo
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.service.appengine import hwid_validator
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import contents_analyzer
from cros.factory.hwid.v3 import database
# pylint: disable=import-error, no-name-in-module
from cros.factory.hwid.service.appengine.proto import hwid_api_messages_pb2
# pylint: enable=import-error, no-name-in-module
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.utils import file_utils


TEST_MODEL = 'FOO'
TEST_HWID = 'Foo'
TEST_HWID_CONTENT = 'prefix\nchecksum: 1234\nsuffix\n'
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

TEST_PREV_HWID_DB_CONTENT = 'prefix\nchecksum: 1234\nimage_id:\nsuffix_v0\n'
TEST_HWID_DB_EDITABLE_SECTION_CONTENT = 'image_id:\nsuffix_v1\n'


def _MockGetAVLName(unused_category, comp_name):
  return comp_name


def _MockGetPrimaryIdentifier(unused_model, unused_category, comp_name):
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

    patcher = mock.patch('__main__.hwid_api._hwid_repo_manager')
    self.patch_hwid_repo_manager = patcher.start()
    self.addCleanup(patcher.stop)

    patcher = mock.patch('__main__.hwid_api._hwid_validator')
    self.patch_hwid_validator = patcher.start()
    self.addCleanup(patcher.stop)

    self.service = hwid_api.ProtoRPCService()

  def testGetProjects(self):
    projects = {'ALPHA', 'BRAVO', 'CHARLIE'}
    self.patch_hwid_manager.GetProjects.return_value = projects

    req = hwid_api_messages_pb2.ProjectsRequest()
    msg = self.service.GetProjects(req)

    self.assertEqual(
        hwid_api_messages_pb2.ProjectsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            projects=sorted(projects)), msg)

  def testGetProjectsEmpty(self):
    projects = set()
    self.patch_hwid_manager.GetProjects.return_value = projects

    req = hwid_api_messages_pb2.ProjectsRequest()
    msg = self.service.GetProjects(req)

    self.assertEqual(
        hwid_api_messages_pb2.ProjectsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetBomNone(self):
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(None, None, None)
    }

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.NOT_FOUND,
            error='HWID not found.'), msg)

    self.patch_hwid_manager.BatchGetBomAndConfigless.assert_called_with(
        [TEST_HWID], False)

  def testGetBomFastKnownBad(self):
    bad_hwid = "FOO TEST"

    req = hwid_api_messages_pb2.BomRequest(hwid=bad_hwid)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.KNOWN_BAD_HWID,
            error='No metadata present for the requested project: %s' %
            bad_hwid), msg)

  def testGetBomValueError(self):
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(None, None, ValueError('foo'))
    }
    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST, error='foo'), msg)

  def testGetBomKeyError(self):
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(None, None, KeyError('foo'))
    }
    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.NOT_FOUND, error='\'foo\''),
        msg)

  def testGetBomEmpty(self):
    bom = hwid_manager.Bom()
    configless = None
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetBomInternalError(self):
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {}

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            error='Internal error',
            status=hwid_api_messages_pb2.Status.SERVER_ERROR), msg)

  def testGetBomComponents(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'foo': 'bar',
        'baz': ['qux', 'rox']
    })
    configless = None
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName
    self.patch_hwid_manager.GetPrimaryIdentifier.side_effect = (
        _MockGetPrimaryIdentifier)

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, components=[
                hwid_api_messages_pb2.Component(name='qux',
                                                component_class='baz'),
                hwid_api_messages_pb2.Component(name='rox',
                                                component_class='baz'),
                hwid_api_messages_pb2.Component(name='bar',
                                                component_class='foo'),
            ]), msg)

  def testBatchGetBom(self):
    hwid1 = 'TEST HWID 1'
    bom1 = hwid_manager.Bom()
    bom1.AddAllComponents({
        'foo1': 'bar1',
        'baz1': ['qux1', 'rox1']
    })

    hwid2 = 'TEST HWID 2'
    bom2 = hwid_manager.Bom()
    bom2.AddAllComponents({
        'foo2': 'bar2',
        'baz2': ['qux2', 'rox2']
    })
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        hwid1: hwid_manager.BomAndConfigless(bom1, None, None),
        hwid2: hwid_manager.BomAndConfigless(bom2, None, None),
    }
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName
    self.patch_hwid_manager.GetPrimaryIdentifier.side_effect = (
        _MockGetPrimaryIdentifier)

    req = hwid_api_messages_pb2.BatchGetBomRequest(hwid=[hwid1, hwid2])
    msg = self.service.BatchGetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BatchGetBomResponse(
            boms={
                hwid1:
                    hwid_api_messages_pb2.BatchGetBomResponse.Bom(
                        status=hwid_api_messages_pb2.Status.SUCCESS,
                        components=[
                            hwid_api_messages_pb2.Component(
                                name='qux1', component_class='baz1'),
                            hwid_api_messages_pb2.Component(
                                name='rox1', component_class='baz1'),
                            hwid_api_messages_pb2.Component(
                                name='bar1', component_class='foo1'),
                        ]),
                hwid2:
                    hwid_api_messages_pb2.BatchGetBomResponse.Bom(
                        status=hwid_api_messages_pb2.Status.SUCCESS,
                        components=[
                            hwid_api_messages_pb2.Component(
                                name='qux2', component_class='baz2'),
                            hwid_api_messages_pb2.Component(
                                name='rox2', component_class='baz2'),
                            hwid_api_messages_pb2.Component(
                                name='bar2', component_class='foo2'),
                        ]),
            }, status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testBatchGetBomWithError(self):
    hwid1 = 'TEST HWID 1'
    hwid2 = 'TEST HWID 2'
    hwid3 = 'TEST HWID 3'
    hwid4 = 'TEST HWID 4'
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'foo': 'bar',
        'baz': ['qux', 'rox']
    })
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        hwid1:
            hwid_manager.BomAndConfigless(None, None,
                                          ValueError('value error')),
        hwid2:
            hwid_manager.BomAndConfigless(None, None, KeyError('Invalid key')),
        hwid3:
            hwid_manager.BomAndConfigless(None, None,
                                          IndexError('index error')),
        hwid4:
            hwid_manager.BomAndConfigless(bom, None, None),
    }
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName
    self.patch_hwid_manager.GetPrimaryIdentifier.side_effect = (
        _MockGetPrimaryIdentifier)

    req = hwid_api_messages_pb2.BatchGetBomRequest(hwid=[hwid1, hwid2])
    msg = self.service.BatchGetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BatchGetBomResponse(
            boms={
                hwid1:
                    hwid_api_messages_pb2.BatchGetBomResponse.Bom(
                        status=hwid_api_messages_pb2.Status.BAD_REQUEST,
                        error='value error'),
                hwid2:
                    hwid_api_messages_pb2.BatchGetBomResponse.Bom(
                        status=hwid_api_messages_pb2.Status.NOT_FOUND,
                        error='\'Invalid key\''),
                hwid3:
                    hwid_api_messages_pb2.BatchGetBomResponse.Bom(
                        status=hwid_api_messages_pb2.Status.SERVER_ERROR,
                        error='index error'),
                hwid4:
                    hwid_api_messages_pb2.BatchGetBomResponse.Bom(
                        status=hwid_api_messages_pb2.Status.SUCCESS,
                        components=[
                            hwid_api_messages_pb2.Component(
                                name='qux', component_class='baz'),
                            hwid_api_messages_pb2.Component(
                                name='rox', component_class='baz'),
                            hwid_api_messages_pb2.Component(
                                name='bar', component_class='foo'),
                        ]),
            }, status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='value error'), msg)

  def testGetDutLabelsCheckIsVPRelated(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents(
        {
            'battery': 'battery_small',
            'camera': 'camera_0',
            'cpu': ['cpu_0', 'cpu_1'],
        }, comp_db=database.Database.LoadFile(
            GOLDEN_HWIDV3_FILE, verify_checksum=False), require_vp_info=True)
    bom.project = 'foo'
    bom.phase = 'bar'
    configless = None
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName
    self.patch_hwid_manager.GetPrimaryIdentifier.side_effect = (
        _MockGetPrimaryIdentifier)

    req = hwid_api_messages_pb2.DutLabelsRequest(hwid=TEST_HWID)
    msg = self.service.GetDutLabels(req)

    self.assertEqual(
        hwid_api_messages_pb2.DutLabelsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            labels=[
                # Only components with 'is_vp_related=True' will be reported as
                # hwid_component.
                hwid_api_messages_pb2.DutLabel(name='hwid_component',
                                               value='battery/battery_small'),
                hwid_api_messages_pb2.DutLabel(name='hwid_component',
                                               value='camera/camera_0'),
                hwid_api_messages_pb2.DutLabel(name='phase', value='bar'),
                hwid_api_messages_pb2.DutLabel(name='sku',
                                               value='foo_cpu_0_cpu_1_0B'),
            ],
            possible_labels=[
                'hwid_component',
                'phase',
                'sku',
                'stylus',
                'touchpad',
                'touchscreen',
                'variant',
            ]),
        msg)

  def testGetBomComponentsWithVerboseFlag(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents(
        {
            'battery': 'battery_small',
            'cpu': ['cpu_0', 'cpu_1'],
            'camera': 'camera_0',
        }, comp_db=database.Database.LoadFile(
            GOLDEN_HWIDV3_FILE, verify_checksum=False), verbose=True)
    configless = None
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName
    self.patch_hwid_manager.GetPrimaryIdentifier.side_effect = (
        _MockGetPrimaryIdentifier)

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID, verbose=True)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, components=[
                hwid_api_messages_pb2.Component(
                    name='battery_small', component_class='battery', fields=[
                        hwid_api_messages_pb2.Field(name='manufacturer',
                                                    value='manufacturer1'),
                        hwid_api_messages_pb2.Field(name='model_name',
                                                    value='model1'),
                        hwid_api_messages_pb2.Field(name='technology',
                                                    value='Battery Li-ion')
                    ]),
                hwid_api_messages_pb2.Component(
                    name='camera_0', component_class='camera', fields=[
                        hwid_api_messages_pb2.Field(name='idProduct',
                                                    value='abcd'),
                        hwid_api_messages_pb2.Field(name='idVendor',
                                                    value='4567'),
                        hwid_api_messages_pb2.Field(name='name', value='Camera')
                    ], avl_info=hwid_api_messages_pb2.AvlInfo(cid=0),
                    has_avl=True),
                hwid_api_messages_pb2.Component(
                    name='cpu_0', component_class='cpu', fields=[
                        hwid_api_messages_pb2.Field(name='cores', value='4'),
                        hwid_api_messages_pb2.Field(name='name',
                                                    value='CPU @ 1.80GHz')
                    ], avl_info=hwid_api_messages_pb2.AvlInfo(cid=0),
                    has_avl=True),
                hwid_api_messages_pb2.Component(
                    name='cpu_1', component_class='cpu', fields=[
                        hwid_api_messages_pb2.Field(name='cores', value='4'),
                        hwid_api_messages_pb2.Field(name='name',
                                                    value='CPU @ 2.00GHz')
                    ], avl_info=hwid_api_messages_pb2.AvlInfo(cid=1),
                    has_avl=True)
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
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, labels=[
                hwid_api_messages_pb2.Label(component_class='foo', name='bar'),
                hwid_api_messages_pb2.Label(component_class='baz', name='qux',
                                            value='1'),
                hwid_api_messages_pb2.Label(component_class='baz', name='rox',
                                            value='2'),
            ]), msg)

  def testGetBomAvlInfo(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents(
        {'dram': ['dram_1234_5678', 'dram_1234_5678#4', 'not_dram_1234_5678']},
        comp_db=database.Database.LoadFile(GOLDEN_HWIDV3_FILE,
                                           verify_checksum=False), verbose=True)
    configless = None
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName
    self.patch_hwid_manager.GetPrimaryIdentifier.side_effect = (
        _MockGetPrimaryIdentifier)

    req = hwid_api_messages_pb2.BomRequest(hwid=TEST_HWID, verbose=True)
    msg = self.service.GetBom(req)

    self.assertEqual(
        hwid_api_messages_pb2.BomResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, components=[
                hwid_api_messages_pb2.Component(
                    name='dram_1234_5678', component_class='dram', fields=[
                        hwid_api_messages_pb2.Field(name='part', value='part2'),
                        hwid_api_messages_pb2.Field(name='size', value='4G'),
                    ], avl_info=hwid_api_messages_pb2.AvlInfo(
                        cid=1234, qid=5678), has_avl=True),
                hwid_api_messages_pb2.Component(
                    name='dram_1234_5678#4', component_class='dram', fields=[
                        hwid_api_messages_pb2.Field(name='part', value='part2'),
                        hwid_api_messages_pb2.Field(name='size', value='4G'),
                        hwid_api_messages_pb2.Field(name='slot', value='3'),
                    ], avl_info=hwid_api_messages_pb2.AvlInfo(
                        cid=1234, qid=5678), has_avl=True),
                hwid_api_messages_pb2.Component(
                    name='not_dram_1234_5678', component_class='dram', fields=[
                        hwid_api_messages_pb2.Field(name='part', value='part3'),
                        hwid_api_messages_pb2.Field(name='size', value='4G'),
                    ]),
            ]), msg)

  def testGetHwids(self):
    hwids = ['alfa', 'bravo', 'charlie']
    self.patch_hwid_manager.GetHwids.return_value = hwids

    req = hwid_api_messages_pb2.HwidsRequest(project=TEST_HWID)
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            hwids=['alfa', 'bravo', 'charlie']), msg)

  def testGetHwidsEmpty(self):
    hwids = list()
    self.patch_hwid_manager.GetHwids.return_value = hwids

    req = hwid_api_messages_pb2.HwidsRequest(project=TEST_HWID)
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetHwidsErrors(self):
    self.patch_hwid_manager.GetHwids.side_effect = ValueError('foo')

    req = hwid_api_messages_pb2.HwidsRequest(project=TEST_HWID)
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='Invalid input: %s' % TEST_HWID), msg)

    req = hwid_api_messages_pb2.HwidsRequest(project=TEST_HWID,
                                             with_classes=['foo', 'bar'],
                                             without_classes=['bar', 'baz'])
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='One or more component classes specified for both with and '
            'without'), msg)

    req = hwid_api_messages_pb2.HwidsRequest(project=TEST_HWID,
                                             with_components=['foo', 'bar'],
                                             without_components=['bar', 'baz'])
    msg = self.service.GetHwids(req)

    self.assertEqual(
        hwid_api_messages_pb2.HwidsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='One or more components specified for both with and without'),
        msg)

  def testGetComponentClasses(self):
    classes = ['alfa', 'bravo', 'charlie']
    self.patch_hwid_manager.GetComponentClasses.return_value = classes

    req = hwid_api_messages_pb2.ComponentClassesRequest(project=TEST_HWID)
    msg = self.service.GetComponentClasses(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentClassesResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            component_classes=['alfa', 'bravo', 'charlie']), msg)

  def testGetComponentClassesEmpty(self):
    classes = list()
    self.patch_hwid_manager.GetComponentClasses.return_value = classes

    req = hwid_api_messages_pb2.ComponentClassesRequest(project=TEST_HWID)
    msg = self.service.GetComponentClasses(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentClassesResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetComponentClassesErrors(self):
    self.patch_hwid_manager.GetComponentClasses.side_effect = ValueError('foo')
    req = hwid_api_messages_pb2.ComponentClassesRequest(project=TEST_HWID)
    msg = self.service.GetComponentClasses(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentClassesResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='Invalid input: %s' % TEST_HWID), msg)

  def testGetComponents(self):
    components = dict(uno=['alfa'], dos=['bravo'], tres=['charlie', 'delta'])

    self.patch_hwid_manager.GetComponents.return_value = components

    req = hwid_api_messages_pb2.ComponentsRequest(project=TEST_HWID)
    msg = self.service.GetComponents(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, components=[
                hwid_api_messages_pb2.Component(component_class='uno',
                                                name='alfa'),
                hwid_api_messages_pb2.Component(component_class='dos',
                                                name='bravo'),
                hwid_api_messages_pb2.Component(component_class='tres',
                                                name='charlie'),
                hwid_api_messages_pb2.Component(component_class='tres',
                                                name='delta'),
            ]), msg)

  def testGetComponentsEmpty(self):
    components = dict()

    self.patch_hwid_manager.GetComponents.return_value = components

    req = hwid_api_messages_pb2.ComponentsRequest(project=TEST_HWID)
    msg = self.service.GetComponents(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testGetComponentsErrors(self):
    self.patch_hwid_manager.GetComponents.side_effect = ValueError('foo')

    req = hwid_api_messages_pb2.ComponentsRequest(project=TEST_HWID)
    msg = self.service.GetComponents(req)

    self.assertEqual(
        hwid_api_messages_pb2.ComponentsResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error='Invalid input: %s' % TEST_HWID,
        ), msg)

  def testValidateConfig(self):
    req = hwid_api_messages_pb2.ValidateConfigRequest(
        hwid_config_contents='test')
    msg = self.service.ValidateConfig(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS), msg)

  def testValidateConfigErrors(self):
    self.patch_hwid_validator.Validate.side_effect = (
        hwid_validator.ValidationError([
            hwid_validator.Error(hwid_validator.ErrorCode.CONTENTS_ERROR, 'msg')
        ]))

    req = hwid_api_messages_pb2.ValidateConfigRequest(
        hwid_config_contents='test')
    msg = self.service.ValidateConfig(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error_message='msg'), msg)

  def testValidateConfigAndUpdateChecksum(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {})

    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwid_config_contents=TEST_HWID_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            new_hwid_config_contents=EXPECTED_REPLACE_RESULT, model=TEST_MODEL),
        msg)

  def testValidateConfigAndUpdateUpdatedComponents(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {
        'wireless': [
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1111_2222', 1111, 2222,
                common.COMPONENT_STATUS.unqualified, True),
            contents_analyzer.NameChangedComponentInfo(
                'wireless_hello_world', 0, 0, common.COMPONENT_STATUS.supported,
                False)
        ]
    })

    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwid_config_contents=TEST_HWID_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    supported = hwid_api_messages_pb2.NameChangedComponent.SUPPORTED
    unqualified = hwid_api_messages_pb2.NameChangedComponent.UNQUALIFIED

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS,
            new_hwid_config_contents=EXPECTED_REPLACE_RESULT,
            name_changed_components_per_category={
                'wireless':
                    hwid_api_messages_pb2.NameChangedComponents(entries=[
                        hwid_api_messages_pb2.NameChangedComponent(
                            cid=1234, qid=5678, support_status=supported,
                            component_name='wireless_1234_5678',
                            has_cid_qid=True),
                        hwid_api_messages_pb2.NameChangedComponent(
                            cid=1111, qid=2222, support_status=unqualified,
                            component_name='wireless_1111_2222',
                            has_cid_qid=True),
                        hwid_api_messages_pb2.NameChangedComponent(
                            cid=0, qid=0, support_status=supported,
                            component_name='wireless_hello_world',
                            has_cid_qid=False)
                    ])
            }, model=TEST_MODEL), msg)

  def testValidateConfigAndUpdateChecksumErrors(self):
    self.patch_hwid_validator.ValidateChange.side_effect = (
        hwid_validator.ValidationError([
            hwid_validator.Error(hwid_validator.ErrorCode.CONTENTS_ERROR, 'msg')
        ]))

    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwid_config_contents=TEST_HWID_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error_message='msg'), msg)

  def testValidateConfigAndUpdateChecksumSchemaError(self):
    validation_error = hwid_validator.ValidationError(
        [hwid_validator.Error(hwid_validator.ErrorCode.SCHEMA_ERROR, 'msg')])
    self.patch_hwid_validator.ValidateChange.side_effect = validation_error
    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwid_config_contents=HWIDV3_CONTENT_SCHEMA_ERROR_CHANGE,
        prev_hwid_config_contents=GOLDEN_HWIDV3_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.SCHEMA_ERROR,
            error_message='msg'), msg)

  def testValidateConfigAndUpdateChecksumUnknwonStatus(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {
        'wireless': [
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1111_2222', 1111, 2222, 'new_status', True)
        ]
    })
    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwid_config_contents=TEST_HWID_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error_message='Unknown status: \'new_status\''), msg)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSku(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'cpu': ['bar1', 'bar2'],
        'dram': ['foo']
    })
    bom.project = 'foo'
    configless = None
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

    req = hwid_api_messages_pb2.SkuRequest(hwid=TEST_HWID)
    msg = self.service.GetSku(req)

    self.assertEqual(
        hwid_api_messages_pb2.SkuResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, project='foo',
            cpu='bar1_bar2', memory='1Mb', memory_in_bytes=100000000,
            sku='foo_bar1_bar2_1Mb'), msg)

  @mock.patch.object(hwid_util, 'GetTotalRamFromHwidData')
  def testGetSkuWithConfigless(self, mock_get_total_ram):
    mock_get_total_ram.return_value = '1Mb', 100000000
    bom = hwid_manager.Bom()
    bom.AddAllComponents({
        'cpu': ['bar1', 'bar2'],
        'dram': ['foo']
    })
    bom.project = 'foo'
    configless = {
        'memory': 4
    }
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

    req = hwid_api_messages_pb2.SkuRequest(hwid=TEST_HWID)
    msg = self.service.GetSku(req)

    self.assertEqual(
        hwid_api_messages_pb2.SkuResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, project='foo',
            cpu='bar1_bar2', memory='4GB', memory_in_bytes=4294967296,
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
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

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
    bom.project = 'foo'
    configless = None

    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

    req = hwid_api_messages_pb2.SkuRequest(hwid=TEST_HWID)
    msg = self.service.GetSku(req)

    self.assertEqual(
        hwid_api_messages_pb2.SkuResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, project='foo',
            memory_in_bytes=2000000, memory='2Mb', sku='foo_None_2Mb'), msg)

  @mock.patch.object(hwid_util, 'GetSkuFromBom')
  def testGetDutLabels(self, mock_get_sku_from_bom):
    self.patch_goldeneye_memcache_adapter.Get.return_value = [
        ('r1.*', 'b1', []), ('^Fo.*', 'found_device', [])
    ]
    bom = hwid_manager.Bom()
    bom.AddComponent('touchscreen', name='testscreen', is_vp_related=True)
    bom.project = 'foo'
    bom.phase = 'bar'
    configless = None

    mock_get_sku_from_bom.return_value = {
        'sku': 'TestSku',
        'project': None,
        'cpu': None,
        'memory_str': None,
        'total_bytes': None
    }

    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }
    self.patch_hwid_manager.GetAVLName.side_effect = _MockGetAVLName
    self.patch_hwid_manager.GetPrimaryIdentifier.side_effect = (
        _MockGetPrimaryIdentifier)

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

  def testGetPossibleDutLabels(self):
    req = hwid_api_messages_pb2.DutLabelsRequest(hwid='')
    msg = self.service.GetDutLabels(req)

    self.assertEqual(
        hwid_api_messages_pb2.DutLabelsResponse(
            status=hwid_api_messages_pb2.Status.SUCCESS, possible_labels=[
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
    bom.project = 'foo'
    bom.phase = 'bar'
    configless = {
        'feature_list': {
            'has_touchscreen': 1
        }
    }
    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

    mock_get_sku_from_bom.return_value = {
        'sku': 'TestSku',
        'project': None,
        'cpu': None,
        'memory_str': None,
        'total_bytes': None
    }

    self.patch_hwid_manager.BatchGetBomAndConfigless.return_value = {
        TEST_HWID: hwid_manager.BomAndConfigless(bom, configless, None)
    }

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

  def testGetHwidDbEditableSectionProjectDoesntExist(self):
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.side_effect = ValueError

    req = hwid_api_messages_pb2.GetHwidDbEditableSectionRequest(
        project='test_project')

    with self.assertRaises(protorpc_utils.ProtoRPCException) as ex:
      self.service.GetHwidDbEditableSection(req)

    self.assertEqual(ex.exception.code,
                     protorpc_utils.RPCCanonicalErrorCode.NOT_FOUND)

  def testGetHwidDbEditableSectionNotV3(self):
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 2,
                                 'v2/test_project'))

    req = hwid_api_messages_pb2.GetHwidDbEditableSectionRequest(
        project='test_project')

    with self.assertRaises(protorpc_utils.ProtoRPCException) as ex:
      self.service.GetHwidDbEditableSection(req)

    self.assertEqual(ex.exception.code,
                     protorpc_utils.RPCCanonicalErrorCode.FAILED_PRECONDITION)

  def testGetHwidDbEditableSectionSuccess(self):
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = textwrap.dedent("""\
        # some prefix
        checksum: "string"

        image_id:
          line0

          line1
          line2\r
        line3

        """)

    req = hwid_api_messages_pb2.GetHwidDbEditableSectionRequest(
        project='test_project')
    resp = self.service.GetHwidDbEditableSection(req)

    self.assertEqual(
        resp.hwid_db_editable_section,
        '\n'.join(['image_id:', '  line0', '', '  line1', '  line2', 'line3']))

  def testValidateHwidDbEditableSectionChangeSchemaError(self):
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT
    validation_error = hwid_validator.ValidationError(
        [hwid_validator.Error(hwid_validator.ErrorCode.SCHEMA_ERROR, 'msg')])
    self.patch_hwid_validator.ValidateChange.side_effect = validation_error

    req = hwid_api_messages_pb2.ValidateHwidDbEditableSectionChangeRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.ValidateHwidDbEditableSectionChange(req)

    self.assertEqual(len(resp.validation_result.errors), 1)
    self.assertEqual(
        resp.validation_result.errors[0],
        hwid_api_messages_pb2.HwidDbEditableSectionChangeValidationResult.Error(
            code=hwid_api_messages_pb2
            .HwidDbEditableSectionChangeValidationResult.SCHEMA_ERROR,
            message='msg'))

  def testValidateHwidDbEditableSectionChangePassed(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {})
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT

    req = hwid_api_messages_pb2.ValidateHwidDbEditableSectionChangeRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.ValidateHwidDbEditableSectionChange(req)

    self.assertTrue(resp.validation_token)
    self.assertFalse(resp.validation_result.errors)

  def testValidateHwidDbEditableSectionChangeReturnUpdatedComponents(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {
        'wireless': [
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1111_2222', 1111, 2222,
                common.COMPONENT_STATUS.unqualified, True),
            contents_analyzer.NameChangedComponentInfo(
                'wireless_hello_world', 0, 0, common.COMPONENT_STATUS.supported,
                False)
        ]
    })
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT

    req = hwid_api_messages_pb2.ValidateHwidDbEditableSectionChangeRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.ValidateHwidDbEditableSectionChange(req)

    supported = hwid_api_messages_pb2.NameChangedComponent.SUPPORTED
    unqualified = hwid_api_messages_pb2.NameChangedComponent.UNQUALIFIED

    ValidationResultMsg = (
        hwid_api_messages_pb2.HwidDbEditableSectionChangeValidationResult)
    self.assertEqual(
        ValidationResultMsg(
            name_changed_components_per_category={
                'wireless':
                    hwid_api_messages_pb2.NameChangedComponents(entries=[
                        hwid_api_messages_pb2.NameChangedComponent(
                            cid=1234, qid=5678, support_status=supported,
                            component_name='wireless_1234_5678',
                            has_cid_qid=True),
                        hwid_api_messages_pb2.NameChangedComponent(
                            cid=1111, qid=2222, support_status=unqualified,
                            component_name='wireless_1111_2222',
                            has_cid_qid=True),
                        hwid_api_messages_pb2.NameChangedComponent(
                            cid=0, qid=0, support_status=supported,
                            component_name='wireless_hello_world',
                            has_cid_qid=False)
                    ])
            }), resp.validation_result)

  def testValidateHwidDbEditableSectionChangeUnknownStatus(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {
        'wireless': [
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            contents_analyzer.NameChangedComponentInfo(
                'wireless_1111_2222', 1111, 2222, 'new_status', True)
        ]
    })
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT

    req = hwid_api_messages_pb2.ValidateHwidDbEditableSectionChangeRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.ValidateHwidDbEditableSectionChange(req)

    self.assertEqual(len(resp.validation_result.errors), 1)
    self.assertEqual(resp.validation_result.errors[0].code,
                     resp.validation_result.CONTENTS_ERROR)

  def testCreateHwidDbEditableSectionChangeClValidationExpired(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {})
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT

    req = hwid_api_messages_pb2.CreateHwidDbEditableSectionChangeClRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT,
        validation_token='this_is_an_invalid_verification_id')
    with self.assertRaises(protorpc_utils.ProtoRPCException) as ex:
      self.service.CreateHwidDbEditableSectionChangeCl(req)
    self.assertEqual(ex.exception.code,
                     protorpc_utils.RPCCanonicalErrorCode.ABORTED)

  def testCreateHwidDbEditableSectionChangeClSucceed(self):
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {})
    req = hwid_api_messages_pb2.ValidateHwidDbEditableSectionChangeRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.ValidateHwidDbEditableSectionChange(req)
    validation_token = resp.validation_token
    live_hwid_repo.CommitHWIDDB.return_value = 123

    req = hwid_api_messages_pb2.CreateHwidDbEditableSectionChangeClRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT,
        validation_token=validation_token)
    resp = self.service.CreateHwidDbEditableSectionChangeCl(req)
    self.assertEqual(resp.cl_number, 123)

  def testBatchGetHwidDbEditableSectionChangeClInfo(self):
    all_hwid_commit_infos = {
        1:
            hwid_repo.HWIDDBCLInfo(hwid_repo.HWIDDBCLStatus.NEW, []),
        2:
            hwid_repo.HWIDDBCLInfo(hwid_repo.HWIDDBCLStatus.MERGED, []),
        3:
            hwid_repo.HWIDDBCLInfo(hwid_repo.HWIDDBCLStatus.ABANDONED, []),
        4:
            hwid_repo.HWIDDBCLInfo(hwid_repo.HWIDDBCLStatus.NEW, [
                hwid_repo.HWIDDBCLComment('msg1', 'user1@email'),
                hwid_repo.HWIDDBCLComment('msg2', 'user2@email'),
            ])
    }

    def _MockGetHWIDDBCLInfo(cl_number):
      try:
        return all_hwid_commit_infos[cl_number]
      except KeyError:
        raise hwid_repo.HWIDRepoError from None

    self.patch_hwid_repo_manager.GetHWIDDBCLInfo.side_effect = (
        _MockGetHWIDDBCLInfo)

    req = (
        hwid_api_messages_pb2.BatchGetHwidDbEditableSectionChangeClInfoRequest(
            cl_numbers=[1, 2, 3, 4, 5, 6]))
    resp = self.service.BatchGetHwidDbEditableSectionChangeClInfo(req)
    expected_resp = (
        hwid_api_messages_pb2.BatchGetHwidDbEditableSectionChangeClInfoResponse(
        ))

    cl_status = expected_resp.cl_status.get_or_create(1)
    cl_status.status = cl_status.PENDING
    cl_status = expected_resp.cl_status.get_or_create(2)
    cl_status.status = cl_status.MERGED
    cl_status = expected_resp.cl_status.get_or_create(3)
    cl_status.status = cl_status.ABANDONED
    cl_status = expected_resp.cl_status.get_or_create(4)
    cl_status.status = cl_status.PENDING
    cl_status.comments.add(email='user1@email', message='msg1')
    cl_status.comments.add(email='user2@email', message='msg2')
    self.assertEqual(resp, expected_resp)

  def testBatchGenerateAvlComponentName_NoQid(self):
    req = hwid_api_messages_pb2.BatchGenerateAvlComponentNameRequest()
    req.component_name_materials.add(component_class='class1', avl_cid=123,
                                     avl_qid=0, seq_no=3)
    resp = self.service.BatchGenerateAvlComponentName(req)
    self.assertEqual(resp.component_names, ['class1_123#3'])

  def testBatchGenerateAvlComponentName_HasQid(self):
    req = hwid_api_messages_pb2.BatchGenerateAvlComponentNameRequest()
    req.component_name_materials.add(component_class='class1', avl_cid=123,
                                     avl_qid=456, seq_no=3)
    req.component_name_materials.add(component_class='class2', avl_cid=234,
                                     avl_qid=567, seq_no=4)
    resp = self.service.BatchGenerateAvlComponentName(req)
    self.assertEqual(resp.component_names,
                     ['class1_123_456#3', 'class2_234_567#4'])

  def CheckForLabelValue(self, response, label_to_check_for,
                         value_to_check_for=None):
    for label in response.labels:
      if label.name == label_to_check_for:
        if value_to_check_for and label.value != value_to_check_for:
          return False
        return True
    return False

  @mock.patch('cros.factory.hwid.v3.contents_analyzer.ContentsAnalyzer')
  def test_AnalyzeHwidDbEditableSection_PreconditionErrors(
      self, mock_contents_analyzer_constructor):
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT

    fake_contents_analyzer_inst = (
        mock_contents_analyzer_constructor.return_value)
    fake_contents_analyzer_inst.AnalyzeChange.return_value = (
        contents_analyzer.ChangeAnalysisReport([
            contents_analyzer.Error(contents_analyzer.ErrorCode.SCHEMA_ERROR,
                                    'some_schema_error')
        ], [], {}))

    req = hwid_api_messages_pb2.AnalyzeHwidDbEditableSectionRequest(
        project='test_project',
        hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.AnalyzeHwidDbEditableSection(req)
    ValidationResultMsg = (
        hwid_api_messages_pb2.HwidDbEditableSectionChangeValidationResult)
    self.assertCountEqual(
        list(resp.validation_result.errors), [
            ValidationResultMsg.Error(code=ValidationResultMsg.SCHEMA_ERROR,
                                      message='some_schema_error')
        ])

  @mock.patch('cros.factory.hwid.v3.contents_analyzer.ContentsAnalyzer')
  def test_AnalyzeHwidDbEditableSection_Pass(
      self, mock_contents_analyzer_constructor):
    live_hwid_repo = self.patch_hwid_repo_manager.GetLiveHWIDRepo.return_value
    live_hwid_repo.GetHWIDDBMetadataByName.return_value = (
        hwid_repo.HWIDDBMetadata('test_project', 'test_project', 3,
                                 'v3/test_project'))
    live_hwid_repo.LoadHWIDDBByName.return_value = TEST_PREV_HWID_DB_CONTENT

    ModificationStatus = (
        contents_analyzer.DBLineAnalysisResult.ModificationStatus)
    Part = contents_analyzer.DBLineAnalysisResult.Part
    fake_contents_analyzer_inst = (
        mock_contents_analyzer_constructor.return_value)
    fake_contents_analyzer_inst.AnalyzeChange.return_value = (
        contents_analyzer.ChangeAnalysisReport(
            [], [
                contents_analyzer.DBLineAnalysisResult(
                    ModificationStatus.NOT_MODIFIED,
                    [Part(Part.Type.TEXT, 'text1')]),
                contents_analyzer.DBLineAnalysisResult(
                    ModificationStatus.MODIFIED,
                    [Part(Part.Type.COMPONENT_NAME, 'comp1')]),
                contents_analyzer.DBLineAnalysisResult(
                    ModificationStatus.NEWLY_ADDED, [
                        Part(Part.Type.COMPONENT_NAME, 'comp2'),
                        Part(Part.Type.COMPONENT_STATUS, 'comp1')
                    ]),
            ], {
                'comp1':
                    contents_analyzer.HWIDComponentAnalysisResult(
                        'comp_cls1', 'comp_name1', 'unqualified', False, None,
                        2, None),
                'comp2':
                    contents_analyzer.HWIDComponentAnalysisResult(
                        'comp_cls2', 'comp_cls2_111_222#9', 'unqualified', True,
                        (111, 222), 1, 'comp_cls2_111_222#1'),
            }))

    req = hwid_api_messages_pb2.AnalyzeHwidDbEditableSectionRequest(
        project='test_project',
        hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.AnalyzeHwidDbEditableSection(req)

    AnalysisReportMsg = (
        hwid_api_messages_pb2.HwidDbEditableSectionAnalysisReport)
    LineMsg = AnalysisReportMsg.HwidDbLine
    LinePartMsg = AnalysisReportMsg.HwidDbLinePart
    ComponentInfoMsg = AnalysisReportMsg.ComponentInfo
    expected_resp = hwid_api_messages_pb2.AnalyzeHwidDbEditableSectionResponse(
        analysis_report=AnalysisReportMsg(
            unqualified_support_status=[
                'deprecated', 'unsupported', 'unqualified', 'duplicate'
            ], qualified_support_status=['supported'], hwid_config_lines=[
                LineMsg(
                    modification_status=LineMsg.NOT_MODIFIED,
                    parts=[LinePartMsg(fixed_text='text1')],
                ),
                LineMsg(
                    modification_status=LineMsg.MODIFIED,
                    parts=[LinePartMsg(component_name_field_id='comp1')],
                ),
                LineMsg(
                    modification_status=LineMsg.NEWLY_ADDED,
                    parts=[
                        LinePartMsg(component_name_field_id='comp2'),
                        LinePartMsg(support_status_field_id='comp1'),
                    ],
                ),
            ], component_infos={
                'comp1':
                    ComponentInfoMsg(
                        component_class='comp_cls1',
                        original_name='comp_name1',
                        original_status='unqualified',
                        is_newly_added=False,
                        has_avl=False,
                        seq_no=2,
                    ),
                'comp2':
                    ComponentInfoMsg(
                        component_class='comp_cls2',
                        original_name='comp_cls2_111_222#9',
                        original_status='unqualified',
                        is_newly_added=True,
                        has_avl=True,
                        avl_info=hwid_api_messages_pb2.AvlInfo(
                            cid=111, qid=222),
                        seq_no=1,
                        component_name_with_correct_seq_no=(
                            'comp_cls2_111_222#1'),
                    ),
            }))

    self.assertEqual(resp, expected_resp)


if __name__ == '__main__':
  unittest.main()
