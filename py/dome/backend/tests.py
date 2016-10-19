# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import errno
import os

import mock
import rest_framework.status
import rest_framework.test

from backend import models


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

  Board APIs:
  - GET /boards/
      List boards.
  - POST /boards/
      Create a new board.
  - DELETE /boards/${BOARD_NAME}/
      Delete a specific board.
  - PUT /boards/${BOARD_NAME}/
      Add/create/delete Umpire container of the board.
  """

  @classmethod
  def setUpClass(cls):
    super(DomeAPITest, cls).setUpClass()

    cls.BOARD_WITHOUT_UMPIRE_NAME = 'board_without_umpire'
    cls.BOARD_WITH_UMPIRE_NAME = 'board_with_umpire'
    cls.BOARD_WITH_UMPIRE_HOST = 'localhost'
    cls.BOARD_WITH_UMPIRE_PORT = 8080

    models.Board.objects.create(name=cls.BOARD_WITHOUT_UMPIRE_NAME)
    models.Board.objects.create(name=cls.BOARD_WITH_UMPIRE_NAME,
                                umpire_enabled=True,
                                umpire_host=cls.BOARD_WITH_UMPIRE_HOST,
                                umpire_port=cls.BOARD_WITH_UMPIRE_PORT)

  def setUp(self):
    self.subprocess_call_patcher = mock.patch('subprocess.call')
    self.subprocess_call = self.subprocess_call_patcher.start()

    self.subprocess_check_call_patcher = mock.patch('subprocess.check_call')
    self.subprocess_check_call = self.subprocess_check_call_patcher.start()

    self.subprocess_check_output_patcher = mock.patch('subprocess.check_output')
    self.subprocess_check_output = self.subprocess_check_output_patcher.start()

  def tearDown(self):
    self.subprocess_call_patcher.stop()
    self.subprocess_check_call_patcher.stop()
    self.subprocess_check_output_patcher.stop()

  def testAddExistingUmpire(self):
    UMPIRE_HOST = 'localhost'
    UMPIRE_PORT = 8090

    # pretend we have the container
    self.subprocess_check_output.return_value = (
        models.Board.GetUmpireContainerName(self.BOARD_WITHOUT_UMPIRE_NAME))

    response = self._AddExistingUmpire(self.BOARD_WITHOUT_UMPIRE_NAME,
                                       UMPIRE_HOST,
                                       UMPIRE_PORT)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertTrue(response.content, {'name': self.BOARD_WITHOUT_UMPIRE_NAME,
                                       'umpireEnabled': True,
                                       'umpireHost': UMPIRE_HOST,
                                       'umpirePort': UMPIRE_PORT})

    # no docker commands should be called
    self.subprocess_call.assert_not_called()
    self.subprocess_check_call.assert_not_called()

  def testAddExistingUmpireButUmpireContainerDoesNotExist(self):
    # pretend we don't have the container
    self.subprocess_check_output.return_value = ''

    response = self._AddExistingUmpire(self.BOARD_WITHOUT_UMPIRE_NAME,
                                       'localhost',
                                       8090)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertTrue('does not exist' in response.json()['detail'])

    # no docker commands should be called
    self.subprocess_call.assert_not_called()
    self.subprocess_check_call.assert_not_called()

  def testCreateBoard(self):
    BOARD_NAME = 'testing_board'

    response = self._CreateBoard(BOARD_NAME)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_201_CREATED)
    self.assertJSONEqual(response.content, {'name': BOARD_NAME,
                                            'umpireEnabled': False,
                                            'umpireHost': None,
                                            'umpirePort': None})

    # no docker commands should be called
    self.subprocess_call.assert_not_called()
    self.subprocess_check_call.assert_not_called()
    self.subprocess_check_output.assert_not_called()

  def testCreateBoardThatAlreadyExists(self):
    response = self._CreateBoard(self.BOARD_WITH_UMPIRE_NAME)
    # TODO(littlecvr): should expect HTTP_409_CONFLICT
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    # TODO(littlecvr): should expect message like "Board OOO already exists"

  def testCreateBoardWithEmptyName(self):
    response = self._CreateBoard('')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)

  def testCreateBoardWithSlashesInName(self):
    response = self._CreateBoard('a/b')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)

  def testCreateBoardWithoutName(self):
    response = self.client.post('/boards/', data={}, format='json')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertTrue('is required' in response.json()['name'])

  def testDeleteAllBoards(self):
    response = self.client.delete('/boards/')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_405_METHOD_NOT_ALLOWED)

  def testDeleteBoard(self):
    response = self._DeleteBoard(self.BOARD_WITH_UMPIRE_NAME)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_204_NO_CONTENT)

    # make sure the container has also been removed
    self.subprocess_call.assert_called_with([
        'docker', 'rm',
        models.Board.GetUmpireContainerName(self.BOARD_WITH_UMPIRE_NAME)])

  def testDeleteNonExistingBoard(self):
    response = self._DeleteBoard('non_existing_board')
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_404_NOT_FOUND)

  def testDisableUmpire(self):
    response = self._DisableUmpire(self.BOARD_WITH_UMPIRE_NAME)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(response.content,
                         {'name': self.BOARD_WITH_UMPIRE_NAME,
                          'umpireEnabled': False,
                          'umpireHost': None,
                          'umpirePort': None})

    # make sure the container has also been removed
    self.subprocess_call.assert_called_with([
        'docker', 'rm',
        models.Board.GetUmpireContainerName(self.BOARD_WITH_UMPIRE_NAME)])

  def testDisableUmpireOnBoardWithoutUmpire(self):
    response = self._DisableUmpire(self.BOARD_WITHOUT_UMPIRE_NAME)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(response.content,
                         {'name': self.BOARD_WITHOUT_UMPIRE_NAME,
                          'umpireEnabled': False,
                          'umpireHost': None,
                          'umpirePort': None})

    # nothing should be changed and nothing should be called
    self.subprocess_call.assert_not_called()
    self.subprocess_check_call.assert_not_called()
    self.subprocess_check_output.assert_not_called()

  def testEnableUmpire(self):
    UMPIRE_PORT = 8090

    # pretend there is no containers
    self.subprocess_check_output.side_effect = [
        '',
        models.Board.GetUmpireContainerName(self.BOARD_WITHOUT_UMPIRE_NAME)]

    response = self._EnableUmpire(self.BOARD_WITHOUT_UMPIRE_NAME, UMPIRE_PORT)
    self.assertEqual(response.status_code, rest_framework.status.HTTP_200_OK)
    self.assertJSONEqual(response.content,
                         {'name': self.BOARD_WITHOUT_UMPIRE_NAME,
                          'umpireEnabled': True,
                          'umpireHost': 'localhost',
                          'umpirePort': UMPIRE_PORT})

    # make sure docker run has been called
    container_name = models.Board.GetUmpireContainerName(
        self.BOARD_WITHOUT_UMPIRE_NAME)
    docker_run_called = False
    for call in self.subprocess_check_call.call_args_list:
      args, unused_kwargs = call
      if 'run' in args[0] and container_name in args[0]:
        docker_run_called = True
        break
    self.assertTrue(docker_run_called)

  def testEnableUmpireButUmpireAlreadyEnabled(self):
    """Test enabling Umpire on a board with Umpire already enabled (and the
    Umpire container exists).

    Nothing should be changed, and no Docker commands except querying for
    container name should be called.
    """
    UMPIRE_PORT = 8090

    # pretend there is no container
    self.subprocess_check_output.return_value = ''

    self._EnableUmpire(self.BOARD_WITH_UMPIRE_NAME, UMPIRE_PORT)

    # make sure no docker commands (except querying for container name) are
    # called
    self.subprocess_call.assert_not_called()
    self.subprocess_check_call.assert_not_called()

  def testEnableUmpireButUmpireAlreadyExists(self):
    """Test enabling Umpire on a board with Umpire disabled but the Umpire
    container already exists.

    An exception should be raised since Dome will not create a new one with the
    same container name (it's also impossible to do that).
    """
    UMPIRE_PORT = 8090

    # pretend that we already have the container
    self.subprocess_check_output.return_value = (
        models.Board.GetUmpireContainerName(self.BOARD_WITHOUT_UMPIRE_NAME))

    response = self._EnableUmpire(self.BOARD_WITHOUT_UMPIRE_NAME, UMPIRE_PORT)
    self.assertEqual(response.status_code,
                     rest_framework.status.HTTP_400_BAD_REQUEST)
    self.assertTrue('already exists' in response.json()['detail'])

  def _AddExistingUmpire(self, board_name, umpire_host, umpire_port):
    return self.client.put('/boards/%s/' % board_name,
                           data={'umpireEnabled': True,
                                 'umpireAddExistingOne': True,
                                 'umpireHost': umpire_host,
                                 'umpirePort': umpire_port},
                           format='json')

  def _CreateBoard(self, board_name):
    return self.client.post('/boards/',
                            data={'name': board_name},
                            format='json')

  def _DeleteBoard(self, board_name):
    return self.client.delete('/boards/%s/' % board_name, format='json')

  def _DisableUmpire(self, board_name):
    return self.client.put('/boards/%s/' % board_name,
                           data={'umpireEnabled': False},
                           format='json')

  def _EnableUmpire(self, board_name, umpire_port):
    # simulate uploading factory toolkit -- of course we don't need a real one
    with open(__file__) as f:
      response = self.client.post('/files/', data={'file': f})
    file_id = response.json()['id']

    return self.client.put(
        '/boards/%s/' % board_name,
        data={'umpireEnabled': True,
              'umpirePort': umpire_port,
              'umpireFactoryToolkitFileId': file_id},
        format='json')
