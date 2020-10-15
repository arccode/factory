# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import errno
import json
import os
from unittest import mock
import xmlrpc.client

import rest_framework.status
import rest_framework.test

from backend import models


SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


@contextlib.contextmanager
def TestData(file_name, deserialize=True):
  """Load a JSON file under the testdata folder using the with statement."""
  with open(os.path.join(SCRIPT_DIR, 'testdata', file_name)) as f:
    if deserialize:
      yield json.load(f)
    else:
      yield f.read()


class UploadedFileTest(rest_framework.test.APITestCase):

  def setUp(self):
    with open(__file__) as f:
      response = self.client.post('/files/', data={'file': f})
    self.uploaded_file_id = response.json()['id']

  def testWithUploadedFile(self):
    """The normal use case of UploadedFile."""
    with models.UploadedFile(self.uploaded_file_id) as path:
      self.assertTrue(os.path.isfile(path))
    self.assertFalse(os.path.exists(path))

  @mock.patch('os.unlink')
  def testWithUploadedFileNoSuchFile(self, unlink):
    """The uploaded file will be removed after used, but it doesn't matter if it
    has already been removed."""
    unlink.side_effect = OSError(errno.ENOENT, 'No such file')

    with models.UploadedFile(self.uploaded_file_id) as path:
      unlink.assert_not_called()
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

    with models.UploadedFile(self.uploaded_file_id) as path:
      rmdir.assert_not_called()
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


# TODO(pihsun): Check if testdata still makes sense after there's no match, and
# there's only one active bundle.


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
      Update bundle resources

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
    cls.PROJECT_WITH_UMPIRE_PORT = 8080
    cls.MOCK_UMPIRE_VERSION = 5

    models.Project.objects.create(name=cls.PROJECT_WITHOUT_UMPIRE_NAME)
    models.Project.objects.create(name=cls.PROJECT_WITH_UMPIRE_NAME,
                                  umpire_enabled=True,
                                  umpire_port=cls.PROJECT_WITH_UMPIRE_PORT)

    os.makedirs(os.path.join(
        models.UMPIRE_BASE_DIR, cls.PROJECT_WITH_UMPIRE_NAME))

  def setUp(self):
    self.maxDiff = None  # developer friendly setting

    ENTITIES_TO_MOCK = ['subprocess.call',
                        'subprocess.check_call',
                        'subprocess.check_output',
                        'shutil.copy',
                        'shutil.rmtree',
                        'os.chmod',
                        'xmlrpc.client.ServerProxy']

    self.patchers = []
    self.mocks = {}
    for entity in ENTITIES_TO_MOCK:
      self.patchers.append(mock.patch(entity))
      self.mocks[entity] = self.patchers[-1].start()

    self.patchers.append(mock.patch.object(
        models.Project, 'GetExistingUmpirePort'))
    self.mocks['GetExistingUmpirePort'] = self.patchers[-1].start()
    self.mocks['GetExistingUmpirePort'].return_value = None

    def MockUmpireGetActiveConfig():
      """Mock the GetActiveConfig() call because it's used so often."""
      add_config_from_blob_mock = (
          self.mocks['xmlrpc.client.ServerProxy']().AddConfigFromBlob)

      # Emulate Umpire to some extend: if new config has been uploaded, return
      # it; otherwise, return the default config.
      if add_config_from_blob_mock.called:
        args, unused_kwargs = add_config_from_blob_mock.call_args
        return args[0]

      with TestData('umpire_config.json', deserialize=False) as config_str:
        return config_str

    def MockUmpireGetPayloadsDict(file_name):
      """Mock the GetPayloadsDict() RPC call in Umpire."""
      with TestData(file_name) as c:
        return c

    self.mocks['xmlrpc.client.ServerProxy']().GetActiveConfig = (
        mock.MagicMock(side_effect=MockUmpireGetActiveConfig))
    self.mocks['xmlrpc.client.ServerProxy']().GetPayloadsDict = (
        mock.MagicMock(side_effect=MockUmpireGetPayloadsDict))
    self.mocks['xmlrpc.client.ServerProxy']().GetVersion = (
        mock.MagicMock(return_value=self.MOCK_UMPIRE_VERSION))

  def tearDown(self):
    for patcher in self.patchers:
      patcher.stop()

  def testAddExistingUmpire(self):
    UMPIRE_PORT = 8090

    # pretend we have the container
    self.mocks['subprocess.check_output'].return_value = (
        models.Project.GetUmpireContainerName(self.PROJECT_WITHOUT_UMPIRE_NAME))

    self.mocks['GetExistingUmpirePort'].return_value = UMPIRE_PORT
    response = self._AddExistingUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertTrue(
        response.content, {
            'name': self.PROJECT_WITHOUT_UMPIRE_NAME,
            'umpireEnabled': True,
            'umpirePort': UMPIRE_PORT,
            'hasExistingUmpire': True
        })

    # no docker commands should be called
    self.mocks['subprocess.call'].assert_not_called()
    self.mocks['subprocess.check_call'].assert_not_called()

  def testCreateProject(self):
    PROJECT_NAME = 'testing_project'

    response = self._CreateProject(PROJECT_NAME)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_201_CREATED)
    self.assertJSONEqual(
        response.content, {
            'name': PROJECT_NAME,
            'umpireEnabled': False,
            'umpirePort': None,
            'netbootBundle': None,
            'hasExistingUmpire': False
        })

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
    self.assertJSONEqual(
        response.content, {
            'name': self.PROJECT_WITH_UMPIRE_NAME,
            'umpireEnabled': False,
            'umpirePort': 8080,
            'netbootBundle': None,
            'hasExistingUmpire': False
        })

    # make sure the container has also been removed
    self.mocks['subprocess.call'].assert_called_with([
        'docker', 'rm',
        models.Project.GetUmpireContainerName(self.PROJECT_WITH_UMPIRE_NAME)])

  def testDisableUmpireOnProjectWithoutUmpire(self):
    response = self._DisableUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(
        response.content, {
            'name': self.PROJECT_WITHOUT_UMPIRE_NAME,
            'umpireEnabled': False,
            'umpirePort': None,
            'netbootBundle': None,
            'hasExistingUmpire': False
        })

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
    self.mocks['GetExistingUmpirePort'].return_value = UMPIRE_PORT

    response = self._EnableUmpire(self.PROJECT_WITHOUT_UMPIRE_NAME, UMPIRE_PORT)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(
        response.content, {
            'name': self.PROJECT_WITHOUT_UMPIRE_NAME,
            'umpireEnabled': True,
            'umpirePort': UMPIRE_PORT,
            'netbootBundle': None,
            'hasExistingUmpire': True
        })

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

  def testUploadResource(self):
    RESOURCE_TYPE = 'toolkit'
    RESOURCE_VERSION = '1234.5678'
    EXPECTED_RETURN_VALUE = {'type': RESOURCE_TYPE,
                             'version': RESOURCE_VERSION}

    # mock Umpire AddResource() call
    self.mocks['xmlrpc.client.ServerProxy']().AddPayload = mock.MagicMock(
        return_value={RESOURCE_TYPE: EXPECTED_RETURN_VALUE})

    response = self._CreateResource(self.PROJECT_WITH_UMPIRE_NAME,
                                    RESOURCE_TYPE)

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_201_CREATED)
    self.assertJSONEqual(response.content, EXPECTED_RETURN_VALUE)

    # make sure AddResource() is called
    self.mocks['xmlrpc.client.ServerProxy']().AddPayload.assert_called_with(
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

  def testActivateBundleUnicode(self):
    response = self._ActivateBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                    u'testing_bundle_04_with_\u4e2d\u6587')

    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    with TestData('umpire_config-activated_unicode.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())
    with TestData('expected_response-activated_bundle_unicode.json') as r:
      self.assertEqual(r, response.json(encoding='UTF-8'))

  def testDeleteBundle(self):
    response = self.client.delete(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_02'),
        format='json')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_204_NO_CONTENT)
    with TestData('umpire_config-deleted.json') as c:
      self.assertEqual(c, self._GetLastestUploadedConfig())

  def testDeleteActiveBundle(self):
    response = self.client.delete(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'testing_bundle_01'),
        format='json')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_422_UNPROCESSABLE_ENTITY)

  def testDeleteNonExistingBundle(self):
    response = self.client.delete(
        '/projects/%s/bundles/%s/' % (self.PROJECT_WITH_UMPIRE_NAME,
                                      'non_existing_bundle'),
        format='json')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_404_NOT_FOUND)
    self.assertIn('not found', response.json()['detail'])

  def testListBundles(self):
    response = self.client.get(
        '/projects/%s/bundles/' % self.PROJECT_WITH_UMPIRE_NAME,
        format='json')
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)

    bundle_list = response.json()
    with TestData('expected_response-get_bundle_list.json') as r:
      self.assertEqual(r, bundle_list)

  def testReorderBundles(self):
    response = self._ReorderBundles(self.PROJECT_WITH_UMPIRE_NAME,
                                    ['testing_bundle_02',
                                     'testing_bundle_01',
                                     'testing_bundle_03',
                                     'empty_init_bundle',
                                     u'testing_bundle_04_with_\u4e2d\u6587'])

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
    with TestData(
        'umpire_config-uploaded.json', deserialize=False) as config_str:
      self.mocks['xmlrpc.client.ServerProxy']().GetActiveConfig =\
          mock.MagicMock(return_value=config_str)

    with TestData('new_bundle.json') as b:
      bundle = b
    response = self._UploadNewBundle(self.PROJECT_WITH_UMPIRE_NAME,
                                     bundle['id'], bundle['note'])

    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_201_CREATED)
    self.mocks['xmlrpc.client.ServerProxy']().ImportBundle.assert_called_once()

  def testUploadBundleThatAlreadyExists(self):
    BUNDLE_NAME = 'existing_bundle'
    BUNDLE_NOTE = 'existing_bundle_note'

    self.mocks['xmlrpc.client.ServerProxy']().ImportBundle = mock.MagicMock(
        side_effect=xmlrpc.client.Fault(
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

    self.mocks['xmlrpc.client.ServerProxy']().ImportBundle = mock.MagicMock(
        side_effect=xmlrpc.client.Fault(
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
    self.mocks['xmlrpc.client.ServerProxy']().Update.assert_called_once()

  def _ActivateBundle(self, project_name, bundle_name):
    return self.client.put('/projects/%s/bundles/%s/' % (project_name,
                                                         bundle_name),
                           data={'active': True},
                           format='json')

  def _AddExistingUmpire(self, project_name):
    return self.client.put('/projects/%s/' % project_name,
                           data={'umpireEnabled': True},
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
        self.mocks['xmlrpc.client.ServerProxy']().AddConfigFromBlob\
            .call_args_list)
    args, unused_kwargs = call_args_list[index]
    config_str = args[0]  # the 1st argument of AddConfigFromBlob()
    return json.loads(config_str)

  def _GetLastestUploadedConfig(self):
    return self._GetUploadedConfig(-1)
