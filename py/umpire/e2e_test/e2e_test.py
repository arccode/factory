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
PORT = net_utils.FindUnusedPort(tcp_only=True, length=5)
ADDR_BASE = 'http://localhost:%s' % PORT
RPC_ADDR_BASE = 'http://localhost:%s' % (PORT + 2)

HOST_BASE_DIR = os.environ.get('TMPDIR', '/tmp')
HOST_SHARED_DIR = os.path.join(HOST_BASE_DIR, 'cros_docker')
HOST_UMPIRE_DIR = os.path.join(HOST_SHARED_DIR, 'umpire', UMPIRE_BOARD_NAME)
HOST_RESOURCE_DIR = os.path.join(HOST_UMPIRE_DIR, 'resources')

DOCKER_BASE_DIR = '/var/db/factory/umpire/'
DOCKER_RESOURCE_DIR = os.path.join(DOCKER_BASE_DIR, 'resources')

TESTDATA_DIR = os.path.join(BASE_DIR, 'testdata')
SHARED_TESTDATA_DIR = os.path.join(TESTDATA_DIR, 'cros_docker')
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
    def UmpireReady():
      try:
        proxy = xmlrpclib.ServerProxy(RPC_ADDR_BASE)
        # Wait until the initial config is deployed.
        return not proxy.GetStatus()['deploying']
      except Exception:
        return False
    try:
      logging.info('Starting umpire container %s on port %s',
                   UMPIRE_BOARD_NAME, PORT)

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

      sync_utils.WaitFor(UmpireReady, 10)
    except:
      CleanUp()
      raise

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
    conf = self.proxy.AddConfigFromBlob(
        yaml.dump(self.default_config), 'umpire_config')
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

  def ReadConfigTestdata(self, name):
    return file_utils.ReadFile(os.path.join(CONFIG_TESTDATA_DIR, name))

  def testListMethods(self):
    self.assertIn('GetStatus', self.proxy.system.listMethods())

  def testEndingSlashInProxyAddress(self):
    proxy = xmlrpclib.ServerProxy(RPC_ADDR_BASE + '/')
    self.assertIn('GetStatus', proxy.system.listMethods())

  def testGetStatus(self):
    status = self.proxy.GetStatus()
    self.assertIn('active_config', status)
    self.assertEqual(self.default_config,
                     yaml.load(status['active_config']))

  def testAddConfigFromBlob(self):
    test_add_config_blob = 'test config blob'
    conf = self.proxy.AddConfigFromBlob(test_add_config_blob, 'umpire_config')
    self.assertEqual(test_add_config_blob, file_utils.ReadFile(
        os.path.join(HOST_RESOURCE_DIR, conf)))

  def testStageConfigFile(self):
    self.assertIsNone(self.proxy.GetStagingConfig())

    test_stage_config = 'test staging config'
    conf = self.proxy.AddConfigFromBlob(test_stage_config, 'umpire_config')
    self.proxy.StageConfigFile(conf)

    self.assertEqual(test_stage_config, self.proxy.GetStagingConfig())

    status = self.proxy.GetStatus()
    self.assertEqual(test_stage_config, status['staging_config'])
    staging_config_res = status['staging_config_res']
    self.assertEqual(test_stage_config, file_utils.ReadFile(
        os.path.join(HOST_RESOURCE_DIR, staging_config_res)))
    self.assertRegexpMatches(staging_config_res, r'^umpire\..*\.yaml$')

  def testStageConfigFileActive(self):
    self.proxy.StageConfigFile()
    self.assertEqual(self.default_config,
                     yaml.load(self.proxy.GetStagingConfig()))

    status = self.proxy.GetStatus()
    self.assertEqual(status['active_config'], status['staging_config'])
    self.assertEqual(status['active_config_res'], status['staging_config_res'])

  def testStageConfigFileRepeated(self):
    conf = self.proxy.AddConfigFromBlob('test staging config', 'umpire_config')
    self.proxy.StageConfigFile(conf)

    test_repeated_stage_config = 'test repeated staging config'
    conf_repeated = self.proxy.AddConfigFromBlob(test_repeated_stage_config,
                                                 'umpire_config')
    with self.assertRPCRaises('another config is already staged'):
      self.proxy.StageConfigFile(conf_repeated)

    self.proxy.StageConfigFile(conf_repeated, True)
    self.assertEqual(self.proxy.GetStagingConfig(), test_repeated_stage_config)

  def testUnstageConfigFile(self):
    with self.assertRPCRaises('no staging config file'):
      self.proxy.UnstageConfigFile()

    conf = self.proxy.AddConfigFromBlob('test unstage config', 'umpire_config')
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

    with self.assertRPCRaises('Missing resource'):
      self.proxy.ValidateConfig(
          self.ReadConfigTestdata('umpire_missing_resource.yaml'))

  def testDeployConfig(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy.yaml')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

    self.assertIsNone(self.proxy.GetStagingConfig())

    status = self.proxy.GetStatus()
    active_config = yaml.load(status['active_config'])
    self.assertEqual(yaml.load(to_deploy_config), active_config)

  def testDeployServiceConfigChanged(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy.yaml')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
    self.proxy.StageConfigFile(conf)
    self.proxy.Deploy(conf)

    to_deploy_config = self.ReadConfigTestdata(
        'umpire_deploy_service_config_changed.yaml')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
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
    # You need a config with "unable to start some service" for this fail.
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy_fail.yaml')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
    self.proxy.StageConfigFile(conf)
    with self.assertRPCRaises('Deploy failed'):
      self.proxy.Deploy(conf)

    staging_config = yaml.load(self.proxy.GetStagingConfig())
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

  def testAddPayload(self):
    payload = self.proxy.AddPayload('/mnt/hwid.gz', 'hwid')
    resource = payload['hwid']['file']
    resource_path = os.path.join(HOST_RESOURCE_DIR, resource)

    self.assertRegexpMatches(resource, r'hwid\..*\.gz')
    self.assertEqual(
        file_utils.ReadFile(os.path.join(SHARED_TESTDATA_DIR, 'hwid.gz')),
        file_utils.ReadFile(resource_path))

    os.unlink(resource_path)

  def testUpdate(self):
    payload = self.proxy.AddPayload('/mnt/hwid.gz', 'hwid')
    resource = payload['hwid']['file']
    self.proxy.Update([
        ('hwid', os.path.join(DOCKER_RESOURCE_DIR, resource))])

    staging_config = yaml.load(self.proxy.GetStagingConfig())
    payload = self.proxy.GetPayloadsDict(
        staging_config['bundles'][0]['payloads'])
    self.assertEqual(resource, payload['hwid']['file'])

    os.unlink(os.path.join(HOST_RESOURCE_DIR, resource))

  def testInResource(self):
    self.assertTrue(self.proxy.InResource(
        'toolkit.067f0398c038261d7f4ab9706850c280.gz'))
    self.assertTrue(self.proxy.InResource(
        os.path.join(DOCKER_RESOURCE_DIR,
                     'toolkit.067f0398c038261d7f4ab9706850c280.gz')))
    self.assertFalse(self.proxy.InResource(
        'toolkit.deadbeefdeadbeef0123456789abcdef.gz'))
    self.assertFalse(self.proxy.InResource(
        '/tmp/toolkit.067f0398c038261d7f4ab9706850c280.gz'))

  def testImportBundle(self):
    resources = {
        'complete': 'complete.d41d8cd98f00b204e9800998ecf8427e.gz',
        'toolkit': 'toolkit.1fa114f0d115285b6e89d6009062cc7f.gz',
        'firmware': 'firmware.8d5aeaea50362c09335a5fc2c1b62b23.gz',
        'hwid': 'hwid.b9af3f21fe717542b0a4da28f65267e6.gz'
    }
    # TODO(pihsun): Add test data for test_image and release_image.

    self.proxy.ImportBundle('/mnt/bundle_for_import.zip', 'umpire_test')

    staging_config = yaml.load(self.proxy.GetStagingConfig())
    new_bundle = next(bundle for bundle in staging_config['bundles']
                      if bundle['id'] == 'umpire_test')
    new_payload = self.proxy.GetPayloadsDict(new_bundle['payloads'])

    for resource_type, resource in resources.iteritems():
      self.assertTrue(self.proxy.InResource(resource))
      self.assertTrue(os.path.exists(
          os.path.join(HOST_RESOURCE_DIR, resource)))
      self.assertEqual(new_payload[resource_type]['file'], resource)

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
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
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

  def testEndingSlashInProxyAddress(self):
    proxy = xmlrpclib.ServerProxy(ADDR_BASE + '/')
    self.assertEqual({'version': 3}, proxy.Ping())

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
    conf = rpc_proxy.AddConfigFromBlob(
        file_utils.ReadFile(
            os.path.join(CONFIG_TESTDATA_DIR, 'umpire_with_resource.yaml')),
        'umpire_config')
    rpc_proxy.StageConfigFile(conf)
    rpc_proxy.Deploy(conf)

    device_info = {
        'x_umpire_dut': {
            'mac': 'aa:bb:cc:dd:ee:ff',
            'sn': '0C1234567890',
            'mlb_sn': 'SN001',
            'stage': 'SMT'},
        'components': {
            'device_factory_toolkit': 'deadbeefdeadbeef0123456789abcdef',
            'hwid': 'hwid_v2',
            'firmware_ec': 'firmware_v2',
            'firmware_pd': 'firmware_v2',
            'firmware_bios': 'firmware_v1'}}
    need_update = ['device_factory_toolkit', 'firmware_bios']
    update_info = self.proxy.GetUpdate(device_info)
    self.assertItemsEqual(device_info['components'].keys(), update_info.keys())
    for resource_type, info in update_info.iteritems():
      self.assertEqual(resource_type in need_update, info['needs_update'])
      logging.debug('Checking resource %s is available for download...',
                    info['url'])
      if info['scheme'] == 'http':
        self.assertTrue(requests.get(info['url']).ok)
      elif info['scheme'] == 'rsync':
        subprocess.check_output(['rsync', info['url']])

  def testGetFactoryLogPort(self):
    self.assertEqual(PORT + 4, self.proxy.GetFactoryLogPort())

  def testUploadReport(self):
    report = 'Stub report content for testing.'
    self.assertTrue(self.proxy.UploadReport('test_serial', report))
    # Report uses GMT time
    now = time.gmtime(time.time())
    report_pattern = os.path.join(HOST_UMPIRE_DIR,
                                  'umpire_data',
                                  'report',
                                  time.strftime('%Y%m%d', now),
                                  'FA-test_serial-*.rpt.xz')
    report_files = glob.glob(report_pattern)
    self.assertEqual(1, len(report_files))
    report_file = report_files[0]
    self.assertEqual(report, file_utils.ReadFile(report_file))


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

  def testDUTRPC(self):
    t = self.proxy.GetTime()
    self.assertAlmostEqual(t, time.time(), delta=1)

  def testRPCNotExist(self):
    with self.assertRPCRaises(fault_code=xmlrpclib.METHOD_NOT_FOUND):
      self.proxy.Magic()


if __name__ == '__main__':
  logging.getLogger().setLevel(int(os.environ.get('LOG_LEVEL') or logging.INFO))
  unittest.main()
