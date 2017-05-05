#!/usr/bin/env python
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Integration tests for umpire docker.

This test would take some time to finish. Ideally this should be run when
there's umpire / docker related changes.

This test is assumed to be run inside docker using `setup/cros_docker.sh
umpire test`, and should not be run directly.
"""

import contextlib
import glob
import logging
import os
import re
import shutil
import subprocess
import time
import unittest
import xmlrpclib

import requests  # pylint: disable=import-error
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.client import umpire_server_proxy
from cros.factory.utils import file_utils
from cros.factory.utils import net_utils
from cros.factory.utils import sync_utils


DOCKER_IMAGE_NAME = 'cros/factory_server'
# Add a timestamp to board name to avoid problem that sometimes container goes
# dead.
UMPIRE_BOARD_NAME = 'test_' + time.strftime('%Y%m%d_%H%M%S')
UMPIRE_CONTAINER_NAME = 'umpire_' + UMPIRE_BOARD_NAME

BASE_DIR = os.path.dirname(__file__)
SETUP_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', 'setup'))
SCRIPT_PATH = os.path.join(SETUP_DIR, 'cros_docker.sh')
# TODO(pihsun): Should use net_utils.FindConsecutiveUnusedPorts, but it use
# lsof to find which ports are used, which doesn't work inside docker with
# --net=host.
PORT = net_utils.FindUnusedTCPPort()
ADDR_BASE = 'http://localhost:%s' % PORT
RPC_ADDR_BASE = 'http://localhost:%s' % (PORT + 2)

HOST_BASE_DIR = os.environ.get('TMPDIR', '/tmp')
HOST_SHARED_DIR = os.path.join(HOST_BASE_DIR, 'docker_shared')
HOST_UMPIRE_DIR = os.path.join(HOST_SHARED_DIR, 'umpire', UMPIRE_BOARD_NAME)
HOST_RESOURCE_DIR = os.path.join(HOST_UMPIRE_DIR, 'resources')

DOCKER_BASE_DIR = '/var/db/factory/umpire/'
DOCKER_RESOURCE_DIR = os.path.join(DOCKER_BASE_DIR, 'resources')

TESTDATA_DIR = os.path.join(BASE_DIR, 'testdata')
SHARED_TESTDATA_DIR = os.path.join(TESTDATA_DIR, 'docker_shared')
UMPIRE_TESTDATA_DIR = os.path.join(TESTDATA_DIR, 'umpire')
CONFIG_TESTDATA_DIR = os.path.join(TESTDATA_DIR, 'config')


def _RunCrosDockerCommand(*args):
  """Run cros_docker.sh commands with environment variables for testing set."""
  subprocess.check_call(
      [SCRIPT_PATH] + list(args),
      env={
          'BOARD': UMPIRE_BOARD_NAME,
          'UMPIRE_PORT': str(PORT),
          'HOST_SHARED_DIR': HOST_SHARED_DIR
      }
  )


def CleanUp():
  """Cleanup everything."""
  logging.info('Doing cleanup...')
  _RunCrosDockerCommand('umpire', 'destroy')
  shutil.rmtree(HOST_SHARED_DIR, ignore_errors=True)


class UmpireDockerTestCase(unittest.TestCase):
  """Base class for integration tests for umpire docker.

  Since starting / stopping umpire docker takes some time, we group several
  tests together, and only do starting / stopping once for each group of tests.
  """
  @classmethod
  def setUpClass(cls):
    del cls  # Unused.
    logging.info('Starting umpire container %s on port %s',
                 UMPIRE_BOARD_NAME, PORT)
    # To ensure that there are no left over from last run.
    CleanUp()

    logging.info('Copying test data...')
    shutil.copytree(
        SHARED_TESTDATA_DIR,
        HOST_SHARED_DIR,
        symlinks=True)
    shutil.copytree(
        UMPIRE_TESTDATA_DIR,
        HOST_UMPIRE_DIR,
        symlinks=True)

    logging.info('Starting umpire...')
    _RunCrosDockerCommand('umpire', 'run')

    logging.info('Waiting umpire to be started...')
    def UmpireReady():
      try:
        proxy = xmlrpclib.ServerProxy(RPC_ADDR_BASE)
        # Wait until the initial config is deployed.
        return not proxy.GetStatus()['deploying']
      except:  # pylint: disable=bare-except
        return False

    sync_utils.WaitFor(UmpireReady, 10)

  @classmethod
  def tearDownClass(cls):
    del cls  # Unused.
    if logging.getLogger().isEnabledFor(logging.DEBUG):
      docker_logs = subprocess.check_output(
          ['docker', 'logs', UMPIRE_CONTAINER_NAME], stderr=subprocess.STDOUT)
      logging.debug(docker_logs)
    CleanUp()

  @contextlib.contextmanager
  def assertRPCRaises(self,
                      exception=None,
                      fault_code=xmlrpclib.APPLICATION_ERROR):
    """Assert that an RPC call raised exception.

    Args:
      exception: Substring that should be in returned exception string.
      fault_code: Expected faultCode for XML RPC.
    """
    with self.assertRaises(xmlrpclib.Fault) as cm:
      yield
    self.assertEqual(fault_code, cm.exception.faultCode)
    if exception:
      self.assertIn(exception, cm.exception.faultString)


class ResourceMapTest(UmpireDockerTestCase):
  """Tests for Umpire /resourcemap."""
  def testResourceMap(self):
    r = requests.get('%s/resourcemap' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'mac=00:11:22:33:44:55'})
    self.assertEqual(200, r.status_code)
    self.assertIn('shop_floor_handler: /shop_floor/', r.text)

  def testResourceMapNoShopFloor(self):
    r = requests.get('%s/resourcemap' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'mac=gg:gg:gg:gg:gg:gg'})
    self.assertEqual(400, r.status_code)


class PostTest(UmpireDockerTestCase):
  """Tests for Umpire /post."""
  def testPostEcho(self):
    r = requests.post('%s/post/Echo' % ADDR_BASE, data={'foo': 'bar'})
    self.assertEqual(200, r.status_code)
    self.assertEqual('{"foo": "[\'bar\']"}', r.text)

  def testPostException(self):
    r = requests.post('%s/post/Echo' % ADDR_BASE, data={'exception': 'bang!'})
    self.assertEqual(500, r.status_code)

  def testPostExternal(self):
    r = requests.post('%s/post/disk_space' % ADDR_BASE)
    self.assertEqual(200, r.status_code)
    self.assertIn('Disk space used (bytes%/inodes%)', r.text)

  def testPostEmpty(self):
    r = requests.post('%s/post' % ADDR_BASE)
    self.assertEqual(400, r.status_code)

  def testPostNotExist(self):
    r = requests.post('%s/post/i_do_not_exist' % ADDR_BASE)
    # TODO(pihsun): This should be 4xx, not 500.
    self.assertEqual(500, r.status_code)

  def testPostRunExternalHandler(self):
    r = requests.post('%s/post/RunExternalHandler' % ADDR_BASE,
                      data={'handler': 'disk_space'})
    self.assertEqual(200, r.status_code)
    self.assertIn('Disk space used (bytes%/inodes%)', r.text)


class UmpireRPCTest(UmpireDockerTestCase):
  """Tests for Umpire RPC."""
  def setUp(self):
    super(UmpireRPCTest, self).setUp()
    self.proxy = xmlrpclib.ServerProxy(RPC_ADDR_BASE)
    if self.proxy.GetStagingConfig() is not None:
      self.proxy.UnstageConfigFile()
    self.default_config = yaml.load(
        self.ReadConfigTestdata('umpire_default.yaml'))
    # Deploy an empty default config.
    conf = self.proxy.UploadConfig(
        'umpire.yaml', yaml.dump(self.default_config))
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

  def ReadConfigTestdata(self, name):
    return file_utils.ReadFile(os.path.join(CONFIG_TESTDATA_DIR, name))

  def RemoveDownloadConfFromConfig(self, config):
    # download_conf is generated by Umpire when activate config.
    for bundle in config['bundles']:
      del bundle['resources']['download_conf']

  def testListMethods(self):
    self.assertIn('GetStatus', self.proxy.system.listMethods())

  def testGetStatus(self):
    status = self.proxy.GetStatus()
    self.assertIn('active_config', status)
    self.assertEqual(self.default_config,
                     yaml.load(status['active_config']))

  def testUploadConfig(self):
    test_upload_config = 'test upload config'
    conf = self.proxy.UploadConfig('umpire.yaml', test_upload_config)
    self.assertEqual(test_upload_config, file_utils.ReadFile(
        os.path.join(HOST_RESOURCE_DIR, conf)))

  def testStageConfigFile(self):
    self.assertIsNone(self.proxy.GetStagingConfig())

    test_stage_config = 'test staging config'
    conf = self.proxy.UploadConfig('umpire.yaml', test_stage_config)
    self.proxy.StageConfigFile(conf)

    self.assertEqual(test_stage_config, self.proxy.GetStagingConfig())

    status = self.proxy.GetStatus()
    self.assertEqual(test_stage_config, status['staging_config'])
    staging_config_res = status['staging_config_res']
    self.assertEqual(test_stage_config, file_utils.ReadFile(
        os.path.join(HOST_RESOURCE_DIR, staging_config_res)))
    self.assertTrue(staging_config_res.startswith('umpire.yaml##'))

  def testStageConfigFileActive(self):
    self.proxy.StageConfigFile()
    self.assertEqual(self.default_config,
                     yaml.load(self.proxy.GetStagingConfig()))

    status = self.proxy.GetStatus()
    self.assertEqual(status['active_config'], status['staging_config'])
    self.assertEqual(status['active_config_res'], status['staging_config_res'])

  def testStageConfigFileRepeated(self):
    conf = self.proxy.UploadConfig('umpire.yaml', 'test staging config')
    self.proxy.StageConfigFile(conf)

    test_repeated_stage_config = 'test repeated staging config'
    conf_repeated = self.proxy.UploadConfig('umpire.yaml',
                                            test_repeated_stage_config)
    with self.assertRPCRaises('another config is already staged'):
      self.proxy.StageConfigFile(conf_repeated)

    self.proxy.StageConfigFile(conf_repeated, True)
    self.assertEqual(self.proxy.GetStagingConfig(), test_repeated_stage_config)

  def testUnstageConfigFile(self):
    with self.assertRPCRaises('no staging config file'):
      self.proxy.UnstageConfigFile()

    conf = self.proxy.UploadConfig('umpire.yaml', 'test unstage config')
    self.proxy.StageConfigFile(conf)
    self.assertIsNotNone(self.proxy.GetStagingConfig())

    self.proxy.UnstageConfigFile()
    self.assertIsNone(self.proxy.GetStagingConfig())

  def testValidateConfig(self):
    with self.assertRPCRaises('ValueError'):
      self.proxy.ValidateConfig('not a\n valid config file.')

    with self.assertRPCRaises('KeyError'):
      self.proxy.ValidateConfig(
          self.ReadConfigTestdata('umpire_no_service.yaml'))

    with self.assertRPCRaises('SchemaException'):
      self.proxy.ValidateConfig(
          self.ReadConfigTestdata('umpire_wrong_schema.yaml'))

    with self.assertRPCRaises('UmpireError: [NOT FOUND]'):
      self.proxy.ValidateConfig(
          self.ReadConfigTestdata('umpire_missing_resource.yaml'))

  def testDeployConfig(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy.yaml')
    conf = self.proxy.UploadConfig('umpire.yaml', to_deploy_config)
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

    self.assertIsNone(self.proxy.GetStagingConfig())

    status = self.proxy.GetStatus()
    active_config = yaml.load(status['active_config'])
    self.RemoveDownloadConfFromConfig(active_config)
    self.assertEqual(yaml.load(to_deploy_config), active_config)
    self.assertIn(
        'shop_floor_handler:',
        requests.get(
            '%s/resourcemap' % ADDR_BASE, headers={'X-Umpire-DUT': 'x'}).text)

  def testDeployServiceConfigChanged(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy.yaml')
    conf = self.proxy.UploadConfig('umpire.yaml', to_deploy_config)
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

    to_deploy_config = self.ReadConfigTestdata(
        'umpire_deploy_service_config_changed.yaml')
    conf = self.proxy.UploadConfig('umpire.yaml', to_deploy_config)
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

    # TODO(pihsun): Figure out a better way to detect if services are restarted
    # without reading docker logs.
    docker_logs = subprocess.check_output(
        ['docker', 'logs', UMPIRE_CONTAINER_NAME],
        stderr=subprocess.STDOUT).splitlines()
    restarted_services = []
    for log_line in reversed(docker_logs):
      if re.search(r'Config .* validated\. Try deploying', log_line):
        # Read logs until last deploy.
        break
      m = re.search(r'Service (.*) started: \[(.*)\]', log_line)
      if m is None:
        continue
      service = m.group(1)
      restarted = len(m.group(2)) > 0
      logging.debug('%s: restarted=%s', service, restarted)
      if restarted:
        restarted_services.append(service)
    # Assert that the only restarted service is instalog.
    self.assertEqual(['instalog'], restarted_services)

  def testDeployConfigFail(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy_fail.yaml')
    conf = self.proxy.UploadConfig('umpire.yaml', to_deploy_config)
    self.proxy.StageConfigFile(conf)
    with self.assertRPCRaises('Deploy failed'):
      self.proxy.Deploy(conf)

    staging_config = yaml.load(self.proxy.GetStagingConfig())
    self.RemoveDownloadConfFromConfig(staging_config)
    self.assertEqual(yaml.load(to_deploy_config), staging_config)

    status = self.proxy.GetStatus()
    active_config = yaml.load(status['active_config'])
    self.assertEqual(self.default_config, active_config)

  def testStopStartService(self):
    test_rsync_cmd = (
        'rsync rsync://localhost:%d/toolkit >/dev/null 2>&1' % (PORT + 4))

    self.proxy.StopServices(['rsync'])
    self.assertNotEqual(0, subprocess.call(test_rsync_cmd, shell=True))

    self.proxy.StartServices(['rsync'])
    subprocess.check_call(test_rsync_cmd, shell=True)

  def testAddResource(self):
    resource = self.proxy.AddResource('/mnt/hwid.gz')
    resource_path = os.path.join(HOST_RESOURCE_DIR, resource)

    self.assertTrue(resource.startswith('hwid.gz##'))
    self.assertEqual(
        file_utils.ReadFile(os.path.join(SHARED_TESTDATA_DIR, 'hwid.gz')),
        file_utils.ReadFile(resource_path))

    os.unlink(resource_path)

  def testUpdate(self):
    resource = self.proxy.AddResource('/mnt/hwid.gz')
    self.proxy.Update([
        ('hwid', os.path.join(DOCKER_RESOURCE_DIR, resource))])

    staging_config = yaml.load(self.proxy.GetStagingConfig())
    self.assertEqual(
        resource,
        staging_config['bundles'][0]['resources']['hwid'])

    os.unlink(os.path.join(HOST_RESOURCE_DIR, resource))

  def testInResource(self):
    self.assertTrue(self.proxy.InResource(
        'install_factory_toolkit.run##94aa34ec'))
    self.assertTrue(self.proxy.InResource(
        os.path.join(DOCKER_RESOURCE_DIR,
                     'install_factory_toolkit.run##94aa34ec')))
    self.assertFalse(self.proxy.InResource(
        'install_factory_toolkit.run##deadbeef'))
    self.assertFalse(self.proxy.InResource(
        '/tmp/install_factory_toolkit.run##94aa34ec'))

  def testImportBundle(self):
    resources = {
        'complete_script': 'complete.gz##d41d8cd9',
        'device_factory_toolkit': 'install_factory_toolkit.run##7509337e',
        'efi_partition': 'efi.gz##d41d8cd9',
        'firmware': 'firmware.gz#bios_v0:ec_v0:pd_v0#8d5aeaea',
        'hwid': 'hwid.gz#01c395676eac950e44819dedd159f5f8137d6ead#b9af3f21',
        'netboot_kernel': 'vmlinuz##d41d8cd9',
        'oem_partition': 'oem.gz##d41d8cd9',
        'rootfs_release': 'rootfs-release.gz#umpire-test#b7e4fcc9',
        'rootfs_test': 'rootfs-test.gz#umpire-test#b7e4fcc9',
        'stateful_partition': 'state.gz##d41d8cd9',
    }

    self.proxy.ImportBundle('/mnt/bundle_for_import.zip')

    staging_config = yaml.load(self.proxy.GetStagingConfig())
    new_bundle = next(bundle for bundle in staging_config['bundles']
                      if bundle['id'] == 'umpire_test')

    for resource_type, resource in resources.iteritems():
      self.assertTrue(self.proxy.InResource(resource))
      self.assertTrue(os.path.exists(
          os.path.join(HOST_RESOURCE_DIR, resource)))
      self.assertEqual(new_bundle['resources'][resource_type], resource)

    for ruleset in staging_config['rulesets']:
      if ruleset['bundle_id'] == 'umpire_test':
        self.assertFalse(ruleset['active'])
        self.assertIn('update match rule in ruleset', ruleset['note'])


class UmpireHTTPTest(UmpireDockerTestCase):
  """Tests for Umpire http features."""
  def setUp(self):
    super(UmpireHTTPTest, self).setUp()
    self.proxy = xmlrpclib.ServerProxy(RPC_ADDR_BASE)

  def testReverseProxy(self):
    to_deploy_config = file_utils.ReadFile(
        os.path.join(CONFIG_TESTDATA_DIR, 'umpire_deploy_proxy.yaml'))
    conf = self.proxy.UploadConfig('umpire.yaml', to_deploy_config)
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

    response = requests.get(
        'http://localhost:%d/res/test' % PORT, allow_redirects=False)
    self.assertEqual(307, response.status_code)
    self.assertEqual('http://11.22.33.44/res/test',
                     response.headers['Location'])


class RPCDUTTest(UmpireDockerTestCase):
  """Tests for Umpire DUT RPC."""
  def setUp(self):
    super(RPCDUTTest, self).setUp()
    self.proxy = xmlrpclib.ServerProxy(ADDR_BASE)

  def testPing(self):
    version = self.proxy.Ping()
    self.assertEqual({'version': 3}, version)

  def testGetTime(self):
    t = self.proxy.GetTime()
    self.assertAlmostEqual(t, time.time(), delta=1)

  def testAlternateURL(self):
    proxy = xmlrpclib.ServerProxy('%s/umpire' % ADDR_BASE)
    version = proxy.Ping()
    self.assertEqual({'version': 3}, version)

  def testGetUpdate(self):
    # Deploy a config that have resources with proper versions for GetUpdate
    # to work.
    rpc_proxy = xmlrpclib.ServerProxy(RPC_ADDR_BASE)
    conf = rpc_proxy.UploadConfig('umpire.yaml', file_utils.ReadFile(
        os.path.join(CONFIG_TESTDATA_DIR, 'umpire_with_resource.yaml')))
    rpc_proxy.Deploy(conf)

    device_info = {
        'x_umpire_dut': {
            'mac': 'aa:bb:cc:dd:ee:ff',
            'sn': '0C1234567890',
            'mlb_sn': 'SN001',
            'stage': 'SMT'},
        'components': {
            'device_factory_toolkit': '94aa34ec',
            'rootfs_release': 'umpire-test',
            'rootfs_test': 'umpire-test-old',
            'firmware_ec': 'ec_v0',
            'firmware_pd': 'pd_v0',
            'firmware_bios': 'bios_old'}}
    need_update = ['rootfs_test', 'firmware_bios']
    update_info = self.proxy.GetUpdate(device_info)
    self.assertSetEqual(set(device_info['components'].keys()),
                        set(update_info.keys()))
    for resource_type, info in update_info.iteritems():
      self.assertEqual(resource_type in need_update, info['needs_update'])
      logging.debug('Checking resource %s is available for download...',
                    info['url'])
      if info['scheme'] == 'http':
        self.assertTrue(requests.get(info['url']).ok)
      elif info['scheme'] == 'rsync':
        subprocess.check_output(['rsync', info['url']])

  def testGetUpdateError(self):
    device_info = {
        'x_umpire_dut': {
            'mac': 'aa:bb:cc:dd:ee:ff',
            'sn': '0C1234567890',
            'mlb_sn': 'SN001',
            'stage': 'SMT'},
        'components': {
            'fake_component': 'test'}}
    with self.assertRPCRaises(
        'is not in update component list',
        fault_code=xmlrpclib.INVALID_METHOD_PARAMS):
      self.proxy.GetUpdate(device_info)

  def testGetFactoryLogPort(self):
    self.assertEqual(PORT + 4, self.proxy.GetFactoryLogPort())

  def testUploadReport(self):
    report = 'Stub report content for testing.'
    self.assertTrue(self.proxy.UploadReport('test_serial', report))
    report_pattern = os.path.join(HOST_UMPIRE_DIR,
                                  'umpire_data',
                                  'report',
                                  time.strftime('%Y%m%d'),
                                  'FA-test_serial-*.rpt.xz')
    report_files = glob.glob(report_pattern)
    self.assertEqual(1, len(report_files))
    report_file = report_files[0]
    self.assertEqual(report, file_utils.ReadFile(report_file))


class ShopFloorTest(UmpireDockerTestCase):
  """Tests for Umpire ShopFloor Proxy."""
  def _GetShopFloorURLToken(self):
    r = requests.get('%s/resourcemap' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'mac=00:11:22:33:44:55'})
    shop_floor_url = None
    token = None
    for line in r.text.splitlines():
      if line.startswith('shop_floor_handler:'):
        shop_floor_url = line.split(': ', 1)[1]
      if line.startswith('__token__:'):
        token = line.split(': ', 1)[1]
    self.assertIsNotNone(shop_floor_url)
    return (shop_floor_url, token)

  def _GetShopFloorProxy(self):
    shop_floor_url, token = self._GetShopFloorURLToken()
    return xmlrpclib.ServerProxy('%s%s/%s' % (ADDR_BASE, shop_floor_url, token))

  def testListMethods(self):
    proxy = self._GetShopFloorProxy()
    methods = proxy.system.listMethods()
    self.assertIn('GetDeviceInfo', methods)

  def testRPC(self):
    proxy = self._GetShopFloorProxy()
    info = proxy.GetDeviceInfo('sn')
    self.assertEqual({'component.has_touchscreen': True}, info)

  def testRPCException(self):
    proxy = self._GetShopFloorProxy()
    with self.assertRPCRaises(
        "ShopFloorHandlerException('exception granted.')"):
      proxy.GetDeviceInfo('exception')

  def testRPCNotExist(self):
    proxy = self._GetShopFloorProxy()
    with self.assertRPCRaises(fault_code=xmlrpclib.METHOD_NOT_FOUND):
      proxy.Magic()

  def testRPCWrongToken(self):
    shop_floor_url, token = self._GetShopFloorURLToken()
    # Change the token to some wrong one.
    token = token[:-1] + chr(ord(token[-1]) ^ 1)
    proxy = xmlrpclib.ServerProxy(
        '%s%s/%s' % (ADDR_BASE, shop_floor_url, token))
    with self.assertRaises(xmlrpclib.ProtocolError) as cm:
      proxy.GetDeviceInfo('sn')
    self.assertEqual(410, cm.exception.errcode)


class UmpireServerProxyTest(UmpireDockerTestCase):
  """Tests for using cros.factory.umpire.client.umpire_server_proxy to interact
  with Umpire."""
  def setUp(self):
    super(UmpireServerProxyTest, self).setUp()
    # Since UmpireServerProxy read this file to find out what board we're using,
    # write values for testing.
    file_utils.WriteFile('/etc/lsb-release',
                         'CHROMEOS_RELEASE_BOARD=%s' % UMPIRE_BOARD_NAME)
    self.proxy = umpire_server_proxy.UmpireServerProxy(ADDR_BASE)

  def tearDown(self):
    super(UmpireServerProxyTest, self).tearDown()
    file_utils.TryUnlink('/etc/lsb-release')

  def testUseUmpire(self):
    self.assertTrue(self.proxy.use_umpire)

  def testGetShopFloorHandlerUri(self):
    self.assertIn('/shop_floor/', self.proxy.GetShopFloorHandlerUri())

  def testDUTRPC(self):
    t = self.proxy.GetTime()
    self.assertAlmostEqual(t, time.time(), delta=1)

  def testShopFloorRPC(self):
    info = self.proxy.GetDeviceInfo('sn')
    self.assertEqual({'component.has_touchscreen': True}, info)

  def testRPCNotExist(self):
    with self.assertRPCRaises(fault_code=xmlrpclib.METHOD_NOT_FOUND):
      self.proxy.Magic()


if __name__ == '__main__':
  logging.getLogger().setLevel(int(os.environ.get('LOG_LEVEL') or logging.INFO))
  unittest.main()
