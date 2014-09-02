#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Unittest for get_update module."""


import logging
import mox
import os
import unittest
import urllib2

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.client import umpire_client
from cros.factory.umpire.client import get_update


MOCK_COMPONENT_KEYS = set(['comp1', 'comp2', 'comp3'])
umpire_client.COMPONENT_KEYS = MOCK_COMPONENT_KEYS

GET_UPDATE_RESULT = {
    'comp1': {
        'needs_update': True,
        'md5sum': 'md5sum1',
        'url': 'url1',
        'scheme': 'scheme1'},
    'comp2': {
        'needs_update': False,
        'md5sum': 'md5sum2',
        'url': 'url2',
        'scheme': 'scheme2'},
    'comp3': {
        'needs_update': False,
        'md5sum': 'md5sum3',
        'url': 'url3',
        'scheme': 'scheme3'}}

GET_UPDATE_FOR_COMPONENTS_RESULT = {
    'comp1': get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum1', url='url1', scheme='scheme1'),
    'comp2': get_update.UpdateInfo(
        needs_update=False, md5sum='md5sum2', url='url2', scheme='scheme2')}


FAKE_TOOLKIT_RESULT = {
    'device_factory_toolkit': (True, 'md5sum1', 'url1', 'scheme1')}

FAKE_TOOLKIT_UPDATE_RESULT = get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum1', url='url1', scheme='scheme1')

FAKE_HWID_RESULT = {
    'hwid': get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum1', url='hwid_url', scheme='http')}

FAKE_HWID_INVALID_RESULT = {
    'hwid': get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum1', url='hwid_url', scheme='zsync')}

FAKE_HWID_NO_UPDATE_RESULT = {
    'hwid': get_update.UpdateInfo(
        needs_update=False, md5sum='md5sum1', url='hwid_url', scheme='http')}

FAKE_HWID_UPDATE_RESULT = 'hwid.sh content'

FAKE_IMAGE_RESULT_1 = {
    'rootfs_test': get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum1', url='test_url', scheme='http'),
    'rootfs_release': get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum2', url='release_url', scheme='http')}

FAKE_IMAGE_RESULT_2 = {
    'rootfs_test': get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum1', url='test_url', scheme='http'),
    'rootfs_release': get_update.UpdateInfo(
        needs_update=False, md5sum='md5sum2', url='release_url', scheme='http')}

FAKE_IMAGE_RESULT_3 = {
    'rootfs_test': get_update.UpdateInfo(
        needs_update=False, md5sum='md5sum1', url='test_url', scheme='http'),
    'rootfs_release': get_update.UpdateInfo(
        needs_update=True, md5sum='md5sum2', url='release_url', scheme='http')}

FAKE_IMAGE_RESULT_4 = {
    'rootfs_test': get_update.UpdateInfo(
        needs_update=False, md5sum='md5sum1', url='test_url', scheme='http'),
    'rootfs_release': get_update.UpdateInfo(
        needs_update=False, md5sum='md5sum2', url='release_url', scheme='http')}

TESTDATA_DIRECTORY = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), 'testdata')

class GetUpdateForComponentsTest(unittest.TestCase):
  """Tests GetUpdateForComponents."""
  def setUp(self):
    """Setups mox and mock umpire_client_info used in tests."""
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(umpire_client, 'UmpireClientInfo')
    self.proxy = self.mox.CreateMockAnything()
    self.fake_client_info = self.mox.CreateMockAnything()
    self.fake_dut_info_components = self.mox.CreateMockAnything()

  def tearDown(self):
    """Cleans up for each test."""
    self.mox.UnsetStubs()

  def testGetUpdateForComponents(self):
    """Tests GetUpdateForComponents."""
    umpire_client.UmpireClientInfo().AndReturn(
        self.fake_client_info)
    self.fake_client_info.GetDUTInfoComponents().AndReturn(
        self.fake_dut_info_components)
    self.proxy.GetUpdate(self.fake_dut_info_components).AndReturn(
        GET_UPDATE_RESULT)

    self.mox.ReplayAll()

    result = get_update.GetUpdateForComponents(
        self.proxy, ['comp1', 'comp2'])
    self.assertEqual(result, GET_UPDATE_FOR_COMPONENTS_RESULT)

    self.mox.VerifyAll()

  def testGetUpdateForInvalidComponents(self):
    """Tests GetUpdateForComponents for invalid components."""
    with self.assertRaises(get_update.UmpireClientGetUpdateException):
      get_update.GetUpdateForComponents(
          self.proxy, ['comp1', 'compX'])


class GetUpdateTests(unittest.TestCase):
  """Tests other utilities in get_update that use GetUpdateForComponents."""
  def setUp(self):
    """Setups mox and mock umpire_client_info used in tests."""
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(get_update, 'GetUpdateForComponents')
    self.proxy = self.mox.CreateMockAnything()

  def tearDown(self):
    """Cleans up for each test."""
    self.mox.UnsetStubs()

  def testGetUpdateForDeviceFactoryToolkit(self):
    """Tests GetUpdateForDeviceFactoryToolkit."""
    get_update.GetUpdateForComponents(
        self.proxy, ['device_factory_toolkit']).AndReturn(FAKE_TOOLKIT_RESULT)

    self.mox.ReplayAll()

    result = get_update.GetUpdateForDeviceFactoryToolkit(self.proxy)
    self.assertTrue(result, FAKE_TOOLKIT_UPDATE_RESULT)

    self.mox.VerifyAll()

  def testGetUpdateForHWID(self):
    """Tests GetUpdateForHWID."""
    self.mox.StubOutWithMock(urllib2, 'urlopen')
    fake_urlopen = self.mox.CreateMockAnything()
    gzip_content = None
    with open(os.path.join(TESTDATA_DIRECTORY , 'hwid.sh.gz')) as f:
      gzip_content = f.read()
    get_update.GetUpdateForComponents(
        self.proxy, ['hwid']).AndReturn(FAKE_HWID_RESULT)
    urllib2.urlopen('hwid_url').AndReturn(fake_urlopen)
    fake_urlopen.read().AndReturn(gzip_content)

    self.mox.ReplayAll()

    result = get_update.GetUpdateForHWID(self.proxy)
    self.assertTrue(result, FAKE_HWID_UPDATE_RESULT)

    self.mox.VerifyAll()

  def testGetUpdateForHWIDInvalidMethod(self):
    """Tests GetUpdateForHWID with invalid scheme."""
    get_update.GetUpdateForComponents(
        self.proxy, ['hwid']).AndReturn(FAKE_HWID_INVALID_RESULT)

    self.mox.ReplayAll()

    with self.assertRaises(get_update.UmpireClientGetUpdateException):
      get_update.GetUpdateForHWID(self.proxy)

    self.mox.VerifyAll()

  def testGetUpdateForHWIDNoUpdate(self):
    """Tests GetUpdateForHWID when no need to update."""
    get_update.GetUpdateForComponents(
        self.proxy, ['hwid']).AndReturn(FAKE_HWID_NO_UPDATE_RESULT)

    self.mox.ReplayAll()

    self.assertEqual(None, get_update.GetUpdateForHWID(self.proxy))

    self.mox.VerifyAll()

  def testNeedImageUpdate(self):
    """Tests NeedImageUpdate."""
    get_update.GetUpdateForComponents(
        self.proxy, ['rootfs_test', 'rootfs_release']).AndReturn(
            FAKE_IMAGE_RESULT_1)
    get_update.GetUpdateForComponents(
        self.proxy, ['rootfs_test', 'rootfs_release']).AndReturn(
            FAKE_IMAGE_RESULT_2)
    get_update.GetUpdateForComponents(
        self.proxy, ['rootfs_test', 'rootfs_release']).AndReturn(
            FAKE_IMAGE_RESULT_3)
    get_update.GetUpdateForComponents(
        self.proxy, ['rootfs_test', 'rootfs_release']).AndReturn(
            FAKE_IMAGE_RESULT_4)

    self.mox.ReplayAll()

    self.assertEqual(True, get_update.NeedImageUpdate(self.proxy))
    self.assertEqual(True, get_update.NeedImageUpdate(self.proxy))
    self.assertEqual(True, get_update.NeedImageUpdate(self.proxy))
    self.assertEqual(False, get_update.NeedImageUpdate(self.proxy))

    self.mox.VerifyAll()


if __name__ == '__main__':
  logging.basicConfig(
      format='%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s',
      level=logging.DEBUG)
  unittest.main()
