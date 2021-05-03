#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for cros.hwid.service.appengine.hwid_api"""

import os.path
import textwrap
import unittest
from unittest import mock

import yaml

from cros.chromeoshwid import update_checksum
from cros.factory.hwid.service.appengine import hwid_api
from cros.factory.hwid.service.appengine import hwid_manager
from cros.factory.hwid.service.appengine import hwid_repo
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import validator as v3_validator
from cros.factory.hwid.v3 import verify_db_pattern
# pylint: disable=import-error, no-name-in-module
from cros.factory.hwid.service.appengine.proto import hwid_api_messages_pb2
# pylint: enable=import-error, no-name-in-module
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.utils import file_utils
from cros.factory.utils import schema


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
            error='No metadata present for the requested project: %s' %
            bad_hwid), msg)

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

  def testGetDutLabelsCheckIsVPRelated(self):
    bom = hwid_manager.Bom()
    bom.AddAllComponents(
        {
            'battery': 'battery_small',
            'camera': 'camera_0',
            'cpu': ['cpu_0', 'cpu_1'],
        }, comp_db=database.Database.LoadFile(GOLDEN_HWIDV3_FILE,
                                              verify_checksum=False))
    bom.project = 'foo'
    bom.phase = 'bar'
    configless = None
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
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
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
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
                    ]),
                hwid_api_messages_pb2.Component(
                    name='cpu_0', component_class='cpu', fields=[
                        hwid_api_messages_pb2.Field(name='cores', value='4'),
                        hwid_api_messages_pb2.Field(name='name',
                                                    value='CPU @ 1.80GHz')
                    ]),
                hwid_api_messages_pb2.Component(
                    name='cpu_1', component_class='cpu', fields=[
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
                hwid_api_messages_pb2.Label(component_class='foo', name='bar'),
                hwid_api_messages_pb2.Label(component_class='baz', name='qux',
                                            value='1'),
                hwid_api_messages_pb2.Label(component_class='baz', name='rox',
                                            value='2'),
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
        v3_validator.ValidationError('msg'))

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
            verify_db_pattern.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            verify_db_pattern.NameChangedComponentInfo(
                'wireless_1111_2222', 1111, 2222,
                common.COMPONENT_STATUS.unqualified, True),
            verify_db_pattern.NameChangedComponentInfo(
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
        v3_validator.ValidationError('msg'))

    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwid_config_contents=TEST_HWID_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.BAD_REQUEST,
            error_message='msg'), msg)

  def testValidateConfigAndUpdateChecksumSyntaxError(self):
    yaml_error = yaml.error.YAMLError('msg')
    validation_error = v3_validator.ValidationError(str(yaml_error))
    validation_error.__cause__ = yaml_error
    self.patch_hwid_validator.ValidateChange.side_effect = validation_error
    req = hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumRequest(
        hwid_config_contents=HWIDV3_CONTENT_SYNTAX_ERROR_CHANGE,
        prev_hwid_config_contents=GOLDEN_HWIDV3_CONTENT)
    msg = self.service.ValidateConfigAndUpdateChecksum(req)

    self.assertEqual(
        hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
            status=hwid_api_messages_pb2.Status.YAML_ERROR,
            error_message='msg'), msg)

  def testValidateConfigAndUpdateChecksumSchemaError(self):
    schema_error = schema.SchemaException('msg')
    validation_error = v3_validator.ValidationError(str(schema_error))
    validation_error.__cause__ = schema_error
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
            verify_db_pattern.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            verify_db_pattern.NameChangedComponentInfo(
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
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

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
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

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
    bom.project = 'foo'
    configless = None

    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

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

    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)
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
    self.patch_hwid_manager.GetBomAndConfigless.return_value = (bom, configless)

    mock_get_sku_from_bom.return_value = {
        'sku': 'TestSku',
        'project': None,
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
    schema_error = schema.SchemaException('msg')
    validation_error = v3_validator.ValidationError(str(schema_error))
    validation_error.__cause__ = schema_error
    self.patch_hwid_validator.ValidateChange.side_effect = validation_error

    req = hwid_api_messages_pb2.ValidateHwidDbEditableSectionChangeRequest(
        project='test_project',
        new_hwid_db_editable_section=TEST_HWID_DB_EDITABLE_SECTION_CONTENT)
    resp = self.service.ValidateHwidDbEditableSectionChange(req)

    self.assertEqual(
        resp.validation_result,
        hwid_api_messages_pb2.HwidDbEditableSectionChangeValidationResult(
            result_code=resp.validation_result.SCHEMA_ERROR,
            error_message='msg'))

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
    self.assertEqual(
        resp.validation_result,
        hwid_api_messages_pb2.HwidDbEditableSectionChangeValidationResult(
            result_code=resp.validation_result.PASSED))

  def testValidateHwidDbEditableSectionChangeReturnUpdatedComponents(self):
    self.patch_hwid_validator.ValidateChange.return_value = (TEST_MODEL, {
        'wireless': [
            verify_db_pattern.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            verify_db_pattern.NameChangedComponentInfo(
                'wireless_1111_2222', 1111, 2222,
                common.COMPONENT_STATUS.unqualified, True),
            verify_db_pattern.NameChangedComponentInfo(
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
            result_code=ValidationResultMsg.PASSED,
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
            verify_db_pattern.NameChangedComponentInfo(
                'wireless_1234_5678', 1234, 5678,
                common.COMPONENT_STATUS.supported, True),
            verify_db_pattern.NameChangedComponentInfo(
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

    self.assertEqual(resp.validation_result.result_code,
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
