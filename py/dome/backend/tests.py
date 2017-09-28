# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import errno
import json
import os
import xmlrpclib

import mock
import rest_framework.status
import rest_framework.test
import yaml

from backend import models

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import resource as umpire_resource


SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


@contextlib.contextmanager
def TestData(file_name):
  """Load a JSON file under the testdata folder using the with statement."""
  with open(os.path.join(SCRIPT_DIR, 'testdata', file_name)) as f:
    yield json.load(f)


class UploadedFileTest(rest_framework.test.APITestCase):

  def setUp(self):
    with open(__file__) as f:
      response = self.client.post('/files/', data={'file': f})
    self.uploaded_file_id = response.json()['id']

  def testWithUploadedFile(self):
    """The normal use case of UploadedFile."""
    with models.UploadedFile(self.uploaded_file_id) as f:
      path = models.UploadedFilePath(f)
      self.assertTrue(os.path.isfile(path))
    self.assertFalse(os.path.exists(path))

  @mock.patch('os.unlink')
  def testWithUploadedFileNoSuchFile(self, unlink):
    """The uploaded file will be removed after used, but it doesn't matter if it
    has already been removed."""
    unlink.side_effect = OSError(errno.ENOENT, 'No such file')

    with models.UploadedFile(self.uploaded_file_id) as f:
      unlink.assert_not_called()
      path = models.UploadedFilePath(f)
    unlink.assert_called_once_with(path)

  @mock.patch('os.unlink')
  def testWithUploadedFileUnlinkRaisesErrorOtherThanENOENT(self, unlink):
    """Test if os.unlink() raises error other than ENOENT."""
    unlink.side_effect = OSError(errno.EACCES, 'Permission denied')

    # This case should never happen actually, but if it happened, we'll just
    # raise.
    with self.assertRaises(OSError):
      with models.UploadedFile(self.uploaded_file_id):
        pass

  @mock.patch('os.rmdir')
  def testWithUploadedFileDirectoryNotEmpty(self, rmdir):
    """The code will try to remove the parent directory of the uploaded file,
    but will fail if it's not empty, which we don't care."""
    rmdir.side_effect = OSError(errno.ENOTEMPTY, 'Directory not empty')

    with models.UploadedFile(self.uploaded_file_id) as f:
      rmdir.assert_not_called()
      path = models.UploadedFilePath(f)
    rmdir.assert_called_once_with(os.path.dirname(path))

  @mock.patch('os.rmdir')
  def testWithUploadedFileRmdirRaisesErrorOtherThanENOTEMPTY(self, rmdir):
    """Test if os.rmdir() raises error other than ENOTEMPTY."""
    rmdir.side_effect = OSError(errno.EACCES, 'Permission denied')

    # This case should never happen actually, but if it happened, we'll just
    # raise.
    with self.assertRaises(OSError):
      with models.UploadedFile(self.uploaded_file_id):
        pass


class DomeAPITest(rest_framework.test.APITestCase):
  """Test Dome APIs.

  This class is somewhere between unit test and integration test. All layers
  below Dome back-end are mocked (such as docker commands, Umpire, etc.), but
  models, serializers, views, and urls modules are not tested separately.

  TODO(littlecvr): we probably need real unit tests and integration tests.

  Project APIs:
  - GET projects/
      List projects.
  - POST /projects/
      Create a new project.
  - DELETE /projects/${PROJECT_NAME}/
      Delete a specific project.
  - PUT /projects/${PROJECT_NAME}/
      Add/create/delete Umpire container of the project.

  Bundle APIs:
  - GET /projects/${PROJECT_NAME}/bundles/
      List bundles.
  - POST /projects/${PROJECT_NAME/bundles/
      Upload a new bundle.
  - PUT /projects/${PROJECT_NAME}/bundles/
      Reorder the bundles.
  - DELETE /projects/${PROJECT_NAME}/bundles/${BUNDLE_NAME}/
      Delete bundle.
  - PUT /projects/${PROJECT_NAME/bundles/${BUNDLE_NAME}/
      Update bundle resources or rules

  Resource APIs:
  - POST /projects/${PROJECT_NAME}/resources/
     Add a resource to Umpire.
  """

  # TODO(littlecvr): separate tests into different groups (project, bundle,
  #                  resource).

  @classmethod
  def setUpClass(cls):
    super(DomeAPITest, cls).setUpClass()

    cls.PROJECT_WITHOUT_UMPIRE_NAME = 'project_without_umpire'
    cls.PROJECT_WITH_UMPIRE_NAME = 'project_with_umpire'
    cls.PROJECT_WITH_UMPIRE_HOST = 'localhost'
    cls.PROJECT_WITH_UMPIRE_PORT = 8080

    models.Project.objects.create(name=cls.PROJECT_WITHOUT_UMPIRE_NAME)
    models.Project.objects.create(name=cls.PROJECT_WITH_UMPIRE_NAME,
                                  umpire_enabled=True,
                                  umpire_host=cls.PROJECT_WITH_UMPIRE_HOST,
                                  umpire_port=cls.PROJECT_WITH_UMPIRE_PORT)

    # We need the Umpire folder, and we need the temp folder to upload either
    # bundle or resource files. Taking advantage of makedirs() here to create
    # both of them at once.
    os.makedirs(os.path.join(
        models.UMPIRE_BASE_DIR, cls.PROJECT_WITH_UMPIRE_NAME, 'temp'))

  def setUp(self):
    self.maxDiff = None  # developer friendly setting

    ENTITIES_TO_MOCK = ['subprocess.call',
                        'subprocess.check_call',
                        'subprocess.check_output',
                        'shutil.copy',
                        'shutil.rmtree',
                        'os.chmod',
                        'xmlrpclib.ServerProxy']

    self.patchers = []
    self.mocks = {}
    for entity in ENTITIES_TO_MOCK:
      self.patchers.append(mock.patch(entity))
      self.mocks[entity] = self.patchers[-1].start()

    def MockUmpireGetStatus():
      """Mock the GetStatus() call because it's used so often."""
      add_config_from_blob_mock = (
          self.mocks['xmlrpclib.ServerProxy']().AddConfigFromBlob)

      config = {}
      # Emulate Umpire to some extend: if new config has been uploaded, return
      # it; otherwise, return the default config.
      if add_config_from_blob_mock.called:
        args, unused_kwargs = add_config_from_blob_mock.call_args
        config_str = args[0]
        if umpire_resource.ConfigTypes.umpire_config.fn_suffix == 'yaml':
          config = yaml.load(config_str)
        else:
          config = json.loads(config_str)
      else:
        with TestData('umpire_config.json') as c:
          config = c
      config_str = json.dumps(config)
      return {'active_config': config_str,
              'active_config_res': '.json',
              'staging_config': config_str,
              'staging_config_res': '.json'}

    def MockUmpireGetPayloadsDict(file_name):
      """Mock the GetPayloadsDict() RPC call in Umpire."""
      with TestData(file_name) as c:
        return c

    self.mocks['xmlrpclib.ServerProxy']().GetStatus = (
        mock.MagicMock(side_effect=MockUmpireGetStatus))
    self.mocks['xmlrpclib.ServerProxy']().GetPayloadsDict = (
        mock.MagicMock(side_effect=MockUmpireGetPayloadsDict))

  def tearDown(self):
    for patcher in self.patchers:
      patcher.stop()

  def testAddExistingUmpire(self):
    UMPIRE_HOST = 'localhost'
    UMPIRE_PORT = 8090

    # pretend we have the container
    self.mocks['subprocess.check_output'].return_value = (
        models.Project.GetUmpireContainerName(self.PROJECT_WITHOUT_UMPIRE_NAME))

    response = self._AddExistingUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME,
                                       UMPIRE_HOST,
                                       UMPIRE_PORT)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertTrue(response.content, {'name': self.PROJECT_WITHOUT_UMPIRE_NAME,
                                       'umpireEnabled': True,
                                       'umpireHost': UMPIRE_HOST,
                                       'umpirePort': UMPIRE_PORT})

    # no docker commands should be called
    self.mocks['subprocess.call'].assert_not_called()
    self.mocks['subprocess.check_call'].assert_not_called()

  def testAddExistingUmpireButUmpireContainerDoesNotExist(self):
    # pretend we don't have the container
    self.mocks['subprocess.check_output'].return_value = ''

    response = self._AddExistingUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME,
                                       'localhost',
                                       8090)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertTrue('does not exist' in response.json()['detail'])

    # no docker commands should be called
    self.mocks['subprocess.call'].assert_not_called()
    self.mocks['subprocess.check_call'].assert_not_called()

  def testCreateProject(self):
    PROJECT_NAME = 'testing_project'

    response = self._CreateProject(PROJECT_NAME)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_201_CREATED)
    self.assertJSONEqual(response.content, {'name': PROJECT_NAME,
                                            'umpireEnabled': False,
                                            'umpireHost': None,
                                            'umpirePort': None,
                                            'netbootBundle': None})

    # no docker commands should be called
    self.mocks['subprocess.call'].assert_not_called()
    self.mocks['subprocess.check_call'].assert_not_called()
    self.mocks['subprocess.check_output'].assert_not_called()

  def testCreateProjectThatAlreadyExists(self):
    response = self._CreateProject(self.PROJECT_WITH_UMPIRE_NAME)
    # TODO(littlecvr): should expect HTTP_409_CONFLICT
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    # TODO(littlecvr): should expect message like "Project OOO already exists"

  def testCreateProjectWithEmptyName(self):
    response = self._CreateProject('')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)

  def testCreateProjectWithSlashesInName(self):
    response = self._CreateProject('a/b')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)

  def testCreateProjectWithoutName(self):
    response = self.client.post('/projects/', data={}, format='json')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertTrue('is required' in response.json()['name'])

  def testDeleteAllProjects(self):
    response = self.client.delete('/projects/')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_405_METHOD_NOT_ALLOWED)

  def testDeleteProject(self):
    response = self._DeleteProject(self.PROJECT_WITH_UMPIRE_NAME)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_204_NO_CONTENT)

    # make sure the container has also been removed
    self.mocks['subprocess.call'].assert_called_with([
        'docker', 'rm',
        models.Project.GetUmpireContainerName(self.PROJECT_WITH_UMPIRE_NAME)])

  def testDeleteNonExistingProject(self):
    response = self._DeleteProject('non_existing_project')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_404_NOT_FOUND)

  def testDisableUmpire(self):
    response = self._DisableUmpire(self.PROJECT_WITH_UMPIRE_NAME)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(response.content,
                         {'name': self.PROJECT_WITH_UMPIRE_NAME,
                          'umpireEnabled': False,
                          'umpireHost': None,
                          'umpirePort': None,
                          'netbootBundle': None})

    # make sure the container has also been removed
    self.mocks['subprocess.call'].assert_called_with([
        'docker', 'rm',
        models.Project.GetUmpireContainerName(self.PROJECT_WITH_UMPIRE_NAME)])

  def testDisableUmpireOnProjectWithoutUmpire(self):
    response = self._DisableUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(response.content,
                         {'name': self.PROJECT_WITHOUT_UMPIRE_NAME,
                          'umpireEnabled': False,
                          'umpireHost': None,
                          'umpirePort': None,
                          'netbootBundle': None})

    # nothing should be changed and nothing should be called
    self.mocks['subprocess.call'].assert_not_called()
    self.mocks['subprocess.check_call'].assert_not_called()
    self.mocks['subprocess.check_output'].assert_not_called()

  def testEnableUmpire(self):
    UMPIRE_PORT = 8090

    # pretend there is no containers
    self.mocks['subprocess.check_output'].side_effect = [
        '',
        models.Project.GetUmpireContainerName(self.PROJECT_WITHOUT_UMPIRE_NAME)]

    response = self._EnableUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME, UMPIRE_PORT)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(response.content,
                         {'name': self.PROJECT_WITHOUT_UMPIRE_NAME,
                          'umpireEnabled': True,
                          'umpireHost': 'localhost',
                          'umpirePort': UMPIRE_PORT,
                          'netbootBundle': None})

    # make sure docker run has been called
    container_name = models.Project.GetUmpireContainerName(
        self.PROJECT_WITHOUT_UMPIRE_NAME)
    docker_run_called = False
    for call in self.mocks['subprocess.check_call'].call_args_list:
      args, unused_kwargs = call
      if 'run' in args[0] and container_name in args[0]:
        docker_run_called = True
        break
    self.assertTrue(docker_run_called)

  def testEnableUmpireButUmpireAlreadyEnabled(self):
    """Test enabling Umpire on a project with Umpire already enabled (and the
    Umpire container exists).

    Nothing should be changed, and no Docker commands except querying for
    container name should be called.
    """
    UMPIRE_PORT = 8090

    # pretend there is no container
    self.mocks['subprocess.check_output'].return_value = ''

    self._EnableUmpire(self.PROJECT_WITH_UMPIRE_NAME, UMPIRE_PORT)

    # make sure no docker commands (except querying for container name) are
    # called
    self.mocks['subprocess.call'].assert_not_called()
    self.mocks['subprocess.check_call'].assert_not_called()

  def testEnableUmpireButUmpireAlreadyExists(self):
    """Test enabling Umpire on a project with Umpire disabled but the Umpire
    container already exists.

    An exception should be raised since Dome will not create a new one with the
    same container name (it's also impossible to do that).
    """
    UMPIRE_PORT = 8090

    # pretend that we already have the container
    self.mocks['subprocess.check_output'].return_value = (
        models.Project.GetUmpireContainerName(self.PROJECT_WITHOUT_UMPIRE_NAME))

    response = self._EnableUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME, UMPIRE_PORT)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertTrue('already exists' in response.json()['detail'])

  def testUploadResource(self):
    RESOURCE_TYPE = 'toolkit'
    RESOURCE_VERSION = '1234.5678'
    EXPECTED_RETURN_VALUE = {'type': RESOURCE_TYPE,
                             'version': RESOURCE_VERSION}

    # mock Umpire AddResource() call
    self.mocks['xmlrpclib.ServerProxy']().AddPayload = mock.MagicMock(
        return_value={RESOURCE_TYPE: EXPECTED_RETURN_VALUE})

    response = self._CreateResource(self.PROJECT_WITH_UMPIRE_NAME,
                                    RESOURCE_TYPE)

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_201_CREATED)
    self.assertJSONEqual(response.content, EXPECTED_RETURN_VALUE)

    # make sure AddResource() is called
    self.mocks['xmlrpclib.ServerProxy']().AddPayload.assert_called_with(
        mock.ANY, RESOURCE_TYPE)

  def testUploadResourceToNonExistingProject(self):
    RESOURCE_TYPE = 'device_factory_toolkit'

    response = self._CreateResource('non_existing_project', RESOURCE_TYPE)

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)

  def testActivateBundle(self):
    response = self._ActivateBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                    'testing_bundle_02')

    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    with TestData('umpire_config-activated.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())
    with TestData('expected_response-activated_bundle.json') as r:
      self.assertEqual(r, response.json())

  def testActivateNonExistingBundle(self):
    response = self._ActivateBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                    'non_existing_bundle')

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertIn('does not exist', response.json()['detail'])

  def testClearBundleRules(self):
    response = self.client.put(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_01'),
        data={'rules': {}},
        format='json')

    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    with TestData('umpire_config-rules_cleared.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())
    with TestData('expected_response-rules_cleared_bundle.json') as r:
      self.assertEqual(r, response.json())

  def testDeactivateBundle(self):
    response = self._DeactivateBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_01')
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    with TestData('umpire_config-deactivated.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())
    with TestData('expected_response-deactivated_bundle.json') as r:
      self.assertEqual(r, response.json())

  def testDeactivateDefaultBundle(self):
    # Umpire does not allow deactivating the default bundle and will raise
    # exception, mock this behavior
    self.mocks['xmlrpclib.ServerProxy']().Deploy = mock.MagicMock(
        side_effect=xmlrpclib.Fault(
            -32500,  # application error, doesn't matter actually
            'UmpireError: Missing default bundle'))

    response = self.client.put(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_03'),
        data={'active': False},
        format='json')

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertIn('Cannot remove or deactivate', response.json()['detail'])

  def testDeleteBundle(self):
    response = self.client.delete(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_02'),
        format='json')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_204_NO_CONTENT)
    with TestData('umpire_config-deleted.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())

  def testDeleteNonExistingBundle(self):
    response = self.client.delete(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'non_existing_bundle'),
        format='json')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_404_NOT_FOUND)
    self.assertIn('not found', response.json()['detail'])

  def testListBundlesAndNormalizeUmpireConfig(self):
    response = self.client.get(
        '/projects/%s/bundles/' % self.PROJECT_WITH_UMPIRE_NAME,
        format='json')
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)

    bundle_list = response.json()
    # See testdata/umpire.yaml and testdata/get_bundle_list_expected.json, we
    # enforce a one-to-one mapping between 'rulesets' and 'bundles' sections,
    # after normalization:
    # - 'testing_bundle_01' appears twice in the rulesets sections, so it should
    #   be duplicated, becoming 'testing_bundle_01_copy'
    # - 'testing_bundle_03' appears in the 'bundles' section but not in the
    #   'rulesets' section, so it should be appended at the end of the
    #   'rulesets' section (but set to inactive)
    with TestData('expected_response-get_bundle_list.json') as r:
      self.assertEqual(r, bundle_list)

  def testModifyBundleRules(self):
    response = self.client.put(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_02'),
        data={'rules': {'mlbSerialNumbers': ['foofoo123', 'barbar456']}},
        format='json')

    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    with TestData('umpire_config-rules_changed.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())
    with TestData('expected_response-rules_changed_bundle.json') as r:
      self.assertEqual(r, response.json())

  def testReorderBundles(self):
    response = self._ReorderBundles(self.PROJECT_WITH_UMPIRE_NAME,
                                    ['testing_bundle_02',
                                     'testing_bundle_01',
                                     'testing_bundle_01_copy',
                                     'testing_bundle_03',
                                     'empty_init_bundle'])

    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    with TestData('umpire_config-reordered.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())
    with TestData('expected_response-reorder_bundles.json') as r:
      self.assertEqual(r, response.json())

  def testReorderBundlesWithoutListingAllBundleNames(self):
    response = self._ReorderBundles(self.PROJECT_WITH_UMPIRE_NAME,
                                    ['testing_bundle_02',
                                     'testing_bundle_01',
                                     'testing_bundle_03',
                                     'empty_init_bundle'])

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertTrue('All bundles must be listed' in response.json()['detail'])

  def testUploadBundle(self):
    # Cannot use the default mock because UploadNew() probes the staging config.
    # We'll have to mock ourselves here.
    with TestData('umpire_config-uploaded.json') as c:
      config_str = json.dumps(c)
      self.mocks['xmlrpclib.ServerProxy']().GetStatus = mock.MagicMock(
          return_value={'active_config': config_str,
                        'active_config_res': '.json',
                        'staging_config': config_str,
                        'staging_config_res': '.json'})

    with TestData('new_bundle.json') as b:
      bundle = b
    response = self._UploadNewBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                     bundle['id'], bundle['note'])

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_201_CREATED)
    with TestData('umpire_config-uploaded.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())
    with TestData('expected_response-upload_new_bundle.json') as r:
      self.assertEqual(r, response.json())

  def testUploadBundleThatAlreadyExists(self):
    BUNDLE_NAME = 'existing_bundle'
    BUNDLE_NOTE = 'existing_bundle_note'

    self.mocks['xmlrpclib.ServerProxy']().ImportBundle = mock.MagicMock(
        side_effect=xmlrpclib.Fault(
            -32500,  # application error, doesn't matter actually
            "UmpireError: bundle_id: '%s' already in use" % BUNDLE_NAME))

    response = self._UploadNewBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                     BUNDLE_NAME, BUNDLE_NOTE)

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_409_CONFLICT)
    self.assertTrue('already exists' in response.json()['detail'])

  def testUploadBundleUnknownUmpireError(self):
    BUNDLE_NAME = 'doomed_bundle'
    BUNDLE_NOTE = 'doomed bundle'

    self.mocks['xmlrpclib.ServerProxy']().ImportBundle = mock.MagicMock(
        side_effect=xmlrpclib.Fault(
            -32500,  # application error, doesn't matter actually
            'UmpireError: Unknown error'))

    response = self._UploadNewBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                     BUNDLE_NAME, BUNDLE_NOTE)

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_500_INTERNAL_SERVER_ERROR)
    self.assertIn('Unknown error', response.json()['detail'])

  def testUpdateBundleResource(self):
    response = self.client.put(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_01'),
        data={
            'newName': 'testing_bundle_01_new',
            'note': 'climbing like a monkey',
            'resources': {
                'device_factory_toolkit': {
                    'type': 'device_factory_toolkit',
                    'file_id': self._UploadFile()['id']
                }
            }
        },
        format='json'
    )

    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)

    # the first call to UploadConfig() should duplicate the source bundle with
    # the new name
    with TestData('umpire_config-resource_updated.json') as c:
      self.assertEqual(c, self._GetUploadedConfig(0))

    # just make sure Update() is called
    self.assertTrue(self.mocks['xmlrpclib.ServerProxy']().Update.called)

  def testUpdateBundleResourceInPlace(self):
    response = self.client.put(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_01'),
        data={
            'resources': {
                'device_factory_toolkit': {
                    'type': 'device_factory_toolkit',
                    'file_id': self._UploadFile()['id']
                }
            }
        },
        format='json'
    )

    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)

    with TestData('umpire_config.json') as c:
      # since we don't mock the Update() call, nothing should be changed
      self.assertEqual(c, self._GetLastestUploadedConfig())

    # just make sure Update() is called
    self.assertTrue(self.mocks['xmlrpclib.ServerProxy']().Update.called)

  def _ActivateBundle(self, project_name, bundle_name):
    return self.client.put('/projects/%s/bundles/%s/' % (project_name,
                                                         bundle_name),
                           data={'active': True},
                           format='json')

  def _AddExistingUmpire(self, project_name, umpire_host, umpire_port):
    return self.client.put('/projects/%s/' % project_name,
                           data={'umpireEnabled': True,
                                 'umpireAddExistingOne': True,
                                 'umpireHost': umpire_host,
                                 'umpirePort': umpire_port},
                           format='json')

  def _CreateProject(self, project_name):
    return self.client.post('/projects/',
                            data={'name': project_name},
                            format='json')

  def _CreateResource(self, project_name, resource_type):
    return self.client.post('/projects/%s/resources/' % project_name,
                            {'file_id': self._UploadFile()['id'],
                             'type': resource_type},
                            format='json')

  def _DeactivateBundle(self, project_name, bundle_name):
    return self.client.put('/projects/%s/bundles/%s/' % (project_name,
                                                         bundle_name),
                           data={'active': False},
                           format='json')

  def _DeleteProject(self, project_name):
    return self.client.delete('/projects/%s/' % project_name, format='json')

  def _DisableUmpire(self, project_name):
    return self.client.put('/projects/%s/' % project_name,
                           data={'umpireEnabled': False},
                           format='json')

  def _EnableUmpire(self, project_name, umpire_port):
    return self.client.put(
        '/projects/%s/' % project_name,
        data={'umpireEnabled': True,
              'umpirePort': umpire_port,
              'umpireFactoryToolkitFileId': self._UploadFile()['id']},
        format='json')

  def _ReorderBundles(self, project_name, bundle_name_list):
    return self.client.put('/projects/%s/bundles/' % project_name,
                           data=bundle_name_list, format='json')

  def _UploadFile(self):
    with open(__file__) as f:
      response = self.client.post('/files/', data={'file': f})
    return response.json()

  def _UploadNewBundle(self, project_name, bundle_name, bundle_note):
    return self.client.post('/projects/%s/bundles/' % project_name,
                            data={'name': bundle_name,
                                  'note': bundle_note,
                                  'bundle_file_id': self._UploadFile()['id']},
                            format='json')

  def _GetUploadedConfig(self, index):
    call_args_list = (
        self.mocks['xmlrpclib.ServerProxy']().AddConfigFromBlob.call_args_list)
    args, unused_kwargs = call_args_list[index]
    config_str = args[0]  # the 1st argument of AddConfigFromBlob()

    if umpire_resource.ConfigTypes.umpire_config.fn_suffix == 'yaml':
      config = yaml.load(config_str)
    else:
      config = json.loads(config_str)

    return config

  def _GetLastestUploadedConfig(self):
    return self._GetUploadedConfig(-1)
