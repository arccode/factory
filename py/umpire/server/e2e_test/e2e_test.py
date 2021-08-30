#!/usr/bin/env python3
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
import gzip
import json
import logging
import os
import re
import shutil
import subprocess
import time
import unittest
import xmlrpc.client

import requests  # pylint: disable=import-error

from cros.factory.umpire import common
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sync_utils


DOCKER_IMAGE_NAME = 'cros/factory_server'
# Add a timestamp to project name to avoid problem that sometimes container goes
# dead.
UMPIRE_PROJECT_NAME = 'test_' + time.strftime('%Y%m%d_%H%M%S')
UMPIRE_CONTAINER_NAME = 'umpire_' + UMPIRE_PROJECT_NAME
SECOND_UMPIRE_PROJECT_NAME = 'test2_' + time.strftime('%Y%m%d_%H%M%S')
SECOND_UMPIRE_CONTAINER_NAME = 'umpire_' + SECOND_UMPIRE_PROJECT_NAME

BASE_DIR = os.path.dirname(__file__)
SETUP_DIR = os.path.abspath(
    os.path.join(BASE_DIR, '..', '..', '..', '..', 'setup'))
SCRIPT_PATH = os.path.join(SETUP_DIR, 'cros_docker.sh')
PORT = net_utils.FindUnusedPort(tcp_only=True, length=5)
ADDR_BASE = 'http://localhost:%s' % PORT
RPC_ADDR_BASE = 'http://localhost:%s' % (PORT + 2)
SECOND_PORT = net_utils.FindUnusedPort(tcp_only=True, length=5)
SECOND_ADDR_BASE = 'http://localhost:%s' % SECOND_PORT
SECOND_RPC_ADDR_BASE = 'http://localhost:%s' % (SECOND_PORT + 2)

HOST_BASE_DIR = os.environ.get('TMPDIR', '/tmp')
HOST_SHARED_DIR = os.path.join(HOST_BASE_DIR, 'cros_docker')
HOST_UMPIRE_DIR = os.path.join(HOST_SHARED_DIR, 'umpire', UMPIRE_PROJECT_NAME)
HOST_RESOURCE_DIR = os.path.join(HOST_UMPIRE_DIR, 'resources')
SECOND_UMPIRE_DIR = os.path.join(HOST_SHARED_DIR, 'umpire',
                                 SECOND_UMPIRE_PROJECT_NAME)

DOCKER_BASE_DIR = '/var/db/factory/umpire/'
DOCKER_RESOURCE_DIR = os.path.join(DOCKER_BASE_DIR, 'resources')

TESTDATA_DIR = os.path.join(BASE_DIR, 'testdata')
SHARED_TESTDATA_DIR = os.path.join(TESTDATA_DIR, 'cros_docker')
UMPIRE_TESTDATA_DIR = os.path.join(TESTDATA_DIR, 'umpire')
CONFIG_TESTDATA_DIR = os.path.join(TESTDATA_DIR, 'config')


def _RunCrosDockerCommand(project_name, port, *args):
  """Run cros_docker.sh commands with environment variables for testing set."""
  subprocess.check_call(
      [SCRIPT_PATH] + list(args), env={
          'PROJECT': project_name,
          'UMPIRE_PORT': str(port),
          'HOST_SHARED_DIR': HOST_SHARED_DIR
      })


class _UmpireReady():

  def __init__(self, rpc_addr):
    self.proxy = xmlrpc.client.ServerProxy(rpc_addr)

  def IsReady(self):
    try:
      return not self.proxy.IsDeploying()
    except Exception:
      return False


def _CopyTestData(umpire_dir):
  logging.info('Copying test data...')
  if umpire_dir == HOST_UMPIRE_DIR:
    shutil.copytree(SHARED_TESTDATA_DIR, HOST_SHARED_DIR, symlinks=True)
  shutil.copytree(UMPIRE_TESTDATA_DIR, umpire_dir, symlinks=True)
  for sub_dir in ('conf', 'log', 'run', 'temp', 'umpire_data'):
    os.mkdir(os.path.join(umpire_dir, sub_dir))


def CleanUp(project_name, port):
  """Cleanup everything."""
  logging.info('Doing cleanup...')
  _RunCrosDockerCommand(project_name, port, 'umpire', 'destroy')
  shutil.rmtree(HOST_SHARED_DIR, ignore_errors=True)


def SetUpUmpire(project_name, port, umpire_dir, rpc_addr):
  try:
    logging.info('Starting umpire container %s on port %s', project_name, port)

    _CopyTestData(umpire_dir)

    logging.info('Starting umpire...')
    _RunCrosDockerCommand(project_name, port, 'umpire', 'run')

    logging.info('Waiting umpire to be started...')

    umpire = _UmpireReady(rpc_addr)
    sync_utils.WaitFor(umpire.IsReady, 10)
  except:
    CleanUp(project_name, port)
    raise


def PrintDockerLogs(container_name):
  if logging.getLogger().isEnabledFor(logging.DEBUG):
    docker_logs = subprocess.check_output(['docker', 'logs', container_name],
                                          stderr=subprocess.STDOUT)
    logging.debug(docker_logs)


class UmpireDockerTestCase(unittest.TestCase):
  """Base class for integration tests for umpire docker.

  Since starting / stopping umpire docker takes some time, we group several
  tests together, and only do starting / stopping once for each group of tests.
  """
  @classmethod
  def setUpClass(cls):
    del cls  # Unused.
    SetUpUmpire(UMPIRE_PROJECT_NAME, PORT, HOST_UMPIRE_DIR, RPC_ADDR_BASE)

  @classmethod
  def tearDownClass(cls):
    del cls  # Unused.
    PrintDockerLogs(UMPIRE_CONTAINER_NAME)
    CleanUp(UMPIRE_PROJECT_NAME, PORT)

  @contextlib.contextmanager
  def assertRPCRaises(self,
                      exception=None,
                      fault_code=xmlrpc.client.APPLICATION_ERROR):
    """Assert that an RPC call raised exception.

    Args:
      exception: Substring that should be in returned exception string.
      fault_code: Expected faultCode for XML RPC.
    """
    with self.assertRaises(xmlrpc.client.Fault) as cm:
      yield
    self.assertEqual(fault_code, cm.exception.faultCode)
    if exception:
      self.assertIn(exception, cm.exception.faultString)


class TwoUmpireDockerTestCase(UmpireDockerTestCase):

  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    SetUpUmpire(SECOND_UMPIRE_PROJECT_NAME, SECOND_PORT, SECOND_UMPIRE_DIR,
                SECOND_RPC_ADDR_BASE)

  @classmethod
  def tearDownClass(cls):
    super().tearDownClass()
    PrintDockerLogs(SECOND_UMPIRE_CONTAINER_NAME)
    CleanUp(SECOND_UMPIRE_PROJECT_NAME, SECOND_PORT)


class ResourceMapTest(UmpireDockerTestCase):
  """Tests for Umpire /webapps/resourcemap and legacy /resourcemap."""
  def testResourceMap(self):
    r = requests.get('%s/webapps/resourcemap' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'mac=00:11:22:33:44:55'})
    self.assertEqual(200, r.status_code)
    self.assertIsNotNone(
        re.search(r'^payloads: .*\.json$', r.text, re.MULTILINE))

  def testLegacyResourceMap(self):
    r = requests.get('%s/resourcemap' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'mac=00:11:22:33:44:55'})
    self.assertEqual(200, r.status_code)
    self.assertIsNotNone(
        re.search(r'^payloads: .*\.json$', r.text, re.MULTILINE))


class DownloadSlotsManagerTest(UmpireDockerTestCase):
  """Tests for Umpire /webapps/download_slots."""
  def testCanRequestSlot(self):
    r = requests.get('%s/webapps/download_slots' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'uuid='})
    self.assertEqual(200, r.status_code)
    self.assertIsNotNone(
        re.search(r'^UUID: [\w-]+',
                  r.text, re.MULTILINE))
    self.assertIsNotNone(
        re.search(r'^N_PLACE: 0$', r.text, re.MULTILINE))

  def testExtendAliveTimeSlot(self):
    r = requests.get('%s/webapps/download_slots' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'uuid='})
    self.assertEqual(200, r.status_code)
    res = re.search(r'^UUID: ([\w-]+)$',
                    r.text, re.MULTILINE)
    self.assertIsNotNone(res)

    r = requests.get('%s/webapps/download_slots' % ADDR_BASE,
                     headers={'X-Umpire-DUT': 'uuid=%s' % res.group(1)})
    self.assertEqual(200, r.status_code)
    self.assertIsNotNone(
        re.search(r'^UUID: (%s)$' % res.group(1), r.text, re.MULTILINE))


class UmpireRPCTest(UmpireDockerTestCase):
  """Tests for Umpire RPC."""
  def setUp(self):
    super(UmpireRPCTest, self).setUp()
    self.proxy = xmlrpc.client.ServerProxy(RPC_ADDR_BASE)
    self.default_config = json.loads(
        self.ReadConfigTestdata('umpire_default.json'))
    # Deploy an empty default config.
    conf = self.proxy.AddConfigFromBlob(
        json.dumps(self.default_config), 'umpire_config')
    self.proxy.Deploy(conf)

  def ReadConfigTestdata(self, name):
    return file_utils.ReadFile(os.path.join(CONFIG_TESTDATA_DIR, name))

  def testVersion(self):
    self.assertEqual(common.UMPIRE_VERSION, self.proxy.GetVersion())

  def testListMethods(self):
    self.assertIn('IsDeploying', self.proxy.system.listMethods())

  def testEndingSlashInProxyAddress(self):
    proxy = xmlrpc.client.ServerProxy(RPC_ADDR_BASE + '/')
    self.assertIn('IsDeploying', proxy.system.listMethods())

  def testGetActiveConfig(self):
    self.assertEqual(self.default_config,
                     json.loads(self.proxy.GetActiveConfig()))

  def testAddConfigFromBlob(self):
    test_add_config_blob = 'test config blob'
    conf = self.proxy.AddConfigFromBlob(test_add_config_blob, 'umpire_config')
    self.assertEqual(test_add_config_blob, file_utils.ReadFile(
        os.path.join(HOST_RESOURCE_DIR, conf)))

  def testValidateConfig(self):
    with self.assertRPCRaises('json.decoder.JSONDecodeError'):
      self.proxy.ValidateConfig('not a valid config.')

    with self.assertRPCRaises('KeyError'):
      self.proxy.ValidateConfig(
          self.ReadConfigTestdata('umpire_no_service.json'))

    with self.assertRPCRaises('SchemaException'):
      self.proxy.ValidateConfig(
          self.ReadConfigTestdata('umpire_wrong_schema.json'))

    with self.assertRPCRaises('Missing resource'):
      self.proxy.ValidateConfig(
          self.ReadConfigTestdata('umpire_missing_resource.json'))

  def testDeployConfig(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy.json')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
    self.proxy.Deploy(conf)

    active_config = json.loads(self.proxy.GetActiveConfig())
    self.assertEqual(json.loads(to_deploy_config), active_config)

  def testDeployServiceConfigChanged(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy.json')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
    self.proxy.Deploy(conf)

    to_deploy_config = self.ReadConfigTestdata(
        'umpire_deploy_service_config_changed.json')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
    self.proxy.Deploy(conf)

    # TODO(pihsun): Figure out a better way to detect if services are restarted
    # without reading docker logs.
    docker_logs = process_utils.CheckOutput(
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
    to_deploy_config = self.ReadConfigTestdata('umpire_deploy_fail.json')
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
    with self.assertRPCRaises('Deploy failed'):
      self.proxy.Deploy(conf)

    active_config = json.loads(self.proxy.GetActiveConfig())
    self.assertEqual(self.default_config, active_config)

  def testStopStartService(self):
    test_rsync_cmd = (
        'rsync rsync://localhost:%d/system_logs >/dev/null 2>&1' % (PORT + 4))

    self.proxy.StopServices(['rsync'])
    self.assertNotEqual(0, subprocess.call(test_rsync_cmd, shell=True))

    self.proxy.StartServices(['rsync'])
    subprocess.check_call(test_rsync_cmd, shell=True)

  def testAddPayload(self):
    payload = self.proxy.AddPayload('/mnt/hwid.gz', 'hwid')
    resource = payload['hwid']['file']
    resource_path = os.path.join(HOST_RESOURCE_DIR, resource)

    self.assertRegex(resource, r'hwid\..*\.gz')
    with gzip.open(os.path.join(SHARED_TESTDATA_DIR, 'hwid.gz')) as f1:
      with gzip.open(resource_path) as f2:
        self.assertEqual(f1.read(), f2.read())

    os.unlink(resource_path)

  def testUpdate(self):
    payload = self.proxy.AddPayload('/mnt/hwid.gz', 'hwid')
    resource = payload['hwid']['file']
    self.proxy.Update([('hwid', os.path.join(DOCKER_RESOURCE_DIR, resource))])

    active_config = json.loads(self.proxy.GetActiveConfig())
    payload = self.proxy.GetPayloadsDict(
        active_config['bundles'][0]['payloads'])
    self.assertEqual(resource, payload['hwid']['file'])

    os.unlink(os.path.join(HOST_RESOURCE_DIR, resource))

  def testImportBundle(self):
    resources = {
        'complete': 'complete.d41d8cd98f00b204e9800998ecf8427e.gz',
        'toolkit': 'toolkit.26a11b67b5abda74b4292cb84cedef26.gz',
        'firmware': 'firmware.7c5f73ab48d570fac54057ccf50eb28a.gz',
        'hwid': 'hwid.d173cfd28e47a0bf7f2760784f55580e.gz'
    }
    # TODO(pihsun): Add test data for test_image and release_image.

    self.proxy.ImportBundle('/mnt/bundle_for_import.zip', 'umpire_test')

    active_config = json.loads(self.proxy.GetActiveConfig())
    new_bundle = next(bundle for bundle in active_config['bundles']
                      if bundle['id'] == 'umpire_test')
    new_payload = self.proxy.GetPayloadsDict(new_bundle['payloads'])

    for resource_type, resource in resources.items():
      self.assertTrue(
          os.path.exists(os.path.join(HOST_RESOURCE_DIR, resource)))
      self.assertEqual(new_payload[resource_type]['file'], resource)

    self.assertEqual('umpire_test', active_config['active_bundle_id'])
    for bundle in active_config['bundles']:
      if bundle['id'] == 'umpire_test':
        self.assertEqual('', bundle['note'])


class UmpireHTTPTest(UmpireDockerTestCase):
  """Tests for Umpire http features."""
  def setUp(self):
    super(UmpireHTTPTest, self).setUp()
    self.proxy = xmlrpc.client.ServerProxy(RPC_ADDR_BASE)

  def testReverseProxy(self):
    to_deploy_config = file_utils.ReadFile(
        os.path.join(CONFIG_TESTDATA_DIR, 'umpire_deploy_proxy.json'))
    conf = self.proxy.AddConfigFromBlob(to_deploy_config, 'umpire_config')
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
    self.proxy = xmlrpc.client.ServerProxy(ADDR_BASE)

  def testPing(self):
    version = self.proxy.Ping()
    self.assertEqual({'version': 3, 'project': UMPIRE_PROJECT_NAME}, version)

  def testEndingSlashInProxyAddress(self):
    proxy = xmlrpc.client.ServerProxy(ADDR_BASE + '/')
    self.assertEqual({'version': 3, 'project': UMPIRE_PROJECT_NAME},
                     proxy.Ping())

  def testGetTime(self):
    t = self.proxy.GetTime()
    self.assertAlmostEqual(t, time.time(), delta=1)

  def testAlternateURL(self):
    proxy = xmlrpc.client.ServerProxy('%s/umpire' % ADDR_BASE)
    version = proxy.Ping()
    self.assertEqual({'version': 3, 'project': UMPIRE_PROJECT_NAME}, version)

  def testGetFactoryLogPort(self):
    self.assertEqual(PORT + 4, self.proxy.GetFactoryLogPort())

  def testUploadReport(self):
    report = b'Stub report content for testing.'
    self.assertTrue(self.proxy.UploadReport('test_serial', report))
    # Report uses GMT time
    now = time.gmtime(time.time())
    report_pattern = os.path.join(HOST_UMPIRE_DIR,
                                  'umpire_data',
                                  'report',
                                  time.strftime('%Y%m%d', now),
                                  'Unknown-test_serial-*.rpt.xz')
    report_files = glob.glob(report_pattern)
    self.assertEqual(1, len(report_files))
    report_file = report_files[0]
    self.assertEqual(report, file_utils.ReadFile(report_file, encoding=None))


class ServiceTest(TwoUmpireDockerTestCase):

  def setUp(self):
    super(ServiceTest, self).setUp()
    self.proxy = xmlrpc.client.ServerProxy(RPC_ADDR_BASE)
    self.second_proxy = xmlrpc.client.ServerProxy(SECOND_RPC_ADDR_BASE)

  def ReadConfigTestdata(self, name):
    return json_utils.LoadFile(os.path.join(CONFIG_TESTDATA_DIR, name))

  def StartService(self, config, wait_time=0):
    conf = self.proxy.AddConfigFromBlob(
        json_utils.DumpStr(config), 'umpire_config')
    self.proxy.Deploy(conf)
    time.sleep(wait_time)

  def testVersion(self):
    self.assertEqual(common.UMPIRE_VERSION, self.proxy.GetVersion())
    self.assertEqual(common.UMPIRE_VERSION, self.second_proxy.GetVersion())

  def testSyncService(self):
    to_deploy_config = self.ReadConfigTestdata('umpire_sync_service.json')
    to_deploy_config['services']['umpire_sync']['primary_information'][
        'port'] = str(PORT)
    to_deploy_config['services']['umpire_sync']['secondary_information'][0][
        'port'] = str(SECOND_PORT)
    self.StartService(to_deploy_config, wait_time=2)

    self.assertEqual(self.proxy.GetActivePayload(),
                     self.second_proxy.GetActivePayload())
    # The secondary ip is set in testdata/config/umpire_sync_service.json, which
    # is the default ip of docker0
    second_url = 'http://172.17.0.1:%d' % SECOND_PORT
    self.assertEqual(self.proxy.GetUmpireSyncStatus()[second_url]['status'],
                     'Success')


if __name__ == '__main__':
  logging.getLogger().setLevel(int(os.environ.get('LOG_LEVEL') or logging.INFO))
  unittest.main()
