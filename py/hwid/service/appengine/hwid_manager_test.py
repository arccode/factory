#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for HwidManager and related classes."""

import os
import unittest
import mock
from mock import patch

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import appengine_test_base
from cros.factory.hwid.service.appengine import filesystem_adapter
from cros.factory.hwid.service.appengine import hwid_manager

GOLDEN_HWIDV2_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata/v2-golden.yaml')
GOLDEN_HWIDV3_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'testdata/v3-golden.yaml')

GOLDEN_HWIDV2_DATA = open(GOLDEN_HWIDV2_FILE, 'r').read()
GOLDEN_HWIDV3_DATA = open(GOLDEN_HWIDV3_FILE, 'r').read()

TEST_V2_HWID = 'CHROMEBOOK BAKER A-A'
TEST_V2_HWID_NO_VAR = 'CHROMEBOOK BAKER'
TEST_V2_HWID_NO_VOL = 'CHROMEBOOK BAKER A'
TEST_V2_HWID_ONE_DASH = 'CHROMEBOOK BAKER-ALFA A-A'
TEST_V2_HWID_ONE_DASH_NO_VAR = 'CHROMEBOOK BAKER-ALFA'
TEST_V2_HWID_ONE_DASH_NO_VOL = 'CHROMEBOOK BAKER-ALFA A'
TEST_V2_HWID_TWO_DASH = 'CHROMEBOOK BAKER-ALFA-BETA A-A'
TEST_V2_HWID_TWO_DASH_NO_VAR = 'CHROMEBOOK BAKER-ALFA-BETA'
TEST_V2_HWID_TWO_DASH_NO_VOL = 'CHROMEBOOK BAKER-ALFA-BETA A'
TEST_V3_HWID = 'CHROMEBOOK AA5A-Y6L'
TEST_V3_HWID_WITH_CONFIGLESS = 'CHROMEBOOK-BRAND 0-8-74-180 AA5A-YZS'


# pylint: disable=protected-access
class HwidManagerTest(appengine_test_base.AppEngineTestBase):
  """Tests the HwidManager class."""

  def setUp(self):
    super(HwidManagerTest, self).setUp()

    self.filesystem_adapter = filesystem_adapter.CloudStorageAdapter(
        'test-bucket')

  def _LoadTestDataStore(self):
    """Loads up the datastore with metadata about one board."""
    metadata = hwid_manager.HwidMetadata(
        board='CHROMEBOOK', path='v2', version='2')
    metadata.put()

  def _LoadTestBlobStore(self):
    """Loads up the blobstore with two files, one for each version supported."""
    with open(GOLDEN_HWIDV2_FILE, 'r') as fh:
      self.filesystem_adapter.WriteFile('/live/v2', fh.read())
    with open(GOLDEN_HWIDV3_FILE, 'r') as fh:
      self.filesystem_adapter.WriteFile('/live/v3', fh.read())

  def _GetManager(self, adapter=None, load_blobstore=True, load_datastore=True):
    """Returns a HwidManager object, optionally loading mock data."""
    if load_blobstore:
      self._LoadTestBlobStore()

    if load_datastore:
      self._LoadTestDataStore()

    if adapter is None:
      adapter = self.filesystem_adapter

    return hwid_manager.HwidManager(adapter)

  def testGetBoardsWithoutExistingBoards(self):
    """Test that a if there are no existing boards, an empty set is returned."""
    manager = self._GetManager(load_blobstore=False, load_datastore=False)

    self.assertEqual(set(), manager.GetBoards())

  def testGetBoardsWithExistingBoards(self):
    """Test that a if there are existing boards, they are returned."""
    manager = self._GetManager()
    boards = set()
    boards.add('CHROMEBOOK')
    self.assertEqual(boards, manager.GetBoards())

  def testGetBoardsVersions(self):
    """Test that the correct boards are returned when versions are listed."""
    manager = self._GetManager()

    self.assertEqual(set(), manager.GetBoards(['3']))

    self.assertEqual({'CHROMEBOOK'}, manager.GetBoards(['2']))
    self.assertEqual({'CHROMEBOOK'}, manager.GetBoards(['2', '3']))

  def testGetBomInvalidFormat(self):
    """Test that an invalid HWID raises a InvalidHwidError."""
    manager = self._GetManager()

    self.assertRaises(hwid_manager.InvalidHwidError,
                      manager.GetBomAndConfigless, 'CHROMEBOOK')

  def testGetBomNonexistentBoard(self):
    """Test that a non-existent board raises a HwidNotFoundError."""
    manager = self._GetManager(load_blobstore=False, load_datastore=False)

    self.assertRaises(hwid_manager.BoardNotFoundError,
                      manager.GetBomAndConfigless, 'CHROMEBOOK FOO A-A')

  def testGetBomMissingHWIDFile(self):
    """Test that when the hwid file is missing we get a MetadataError."""
    manager = self._GetManager(load_blobstore=False)

    self.assertRaises(hwid_manager.MetadataError, manager.GetBomAndConfigless,
                      'CHROMEBOOK FOO A-A')

  def testGetBomInvalidBOM(self):
    """Test that an invalid BOM name raises a HwidNotFoundError."""
    manager = self._GetManager()

    self.assertRaises(hwid_manager.HwidNotFoundError,
                      manager.GetBomAndConfigless, 'CHROMEBOOK FOO A-A')

  def testGetBomExistingBoard(self):
    """Test that a valid HWID returns a result."""
    manager = self._GetManager()

    self.assertIsNotNone(manager.GetBomAndConfigless(TEST_V2_HWID)[0])

  def testGetBomMultipleFiles(self):
    """Test when fetching from multiple files, both are supported."""
    manager = self._GetManager()

    manager.RegisterBoard('CHROMEBOOK', 2, 'v2')
    manager.RegisterBoard('CHROMEBOOK', 3, 'v3')

    self.assertRaises(hwid_manager.TooManyBoardsFound,
                      manager.GetBomAndConfigless, TEST_V2_HWID)

  def testGetHwidsNonExistentBoard(self):
    """Test that a non-existent board raises a BoardNotFoundError."""
    manager = self._GetManager(load_blobstore=False, load_datastore=False)

    self.assertRaises(hwid_manager.BoardNotFoundError, manager.GetHwids,
                      'CHROMEBOOK', None, None, None, None)

  def testGetHwidsExistingBoard(self):
    """Test that a valid board returns a result."""
    manager = self._GetManager()
    hwids = {'BAKER', 'BAXTER', 'BLANCA', 'BRIDGE'}
    self.assertEqual(hwids,
                     set(
                         manager.GetHwids('CHROMEBOOK', None, None, None,
                                          None)))

  def testGetComponentClassesNonExistentBoard(self):
    """Test that a non-existent board raises a BoardNotFoundError."""
    manager = self._GetManager(load_blobstore=False, load_datastore=False)

    self.assertRaises(hwid_manager.BoardNotFoundError,
                      manager.GetComponentClasses, 'CHROMEBOOK')

  def testGetComponentClassesExistingBoard(self):
    """Test that a valid board returns a result."""
    manager = self._GetManager()

    self.assertIn('audio_codec', manager.GetComponentClasses('CHROMEBOOK'))
    self.assertIn('cellular', manager.GetComponentClasses('CHROMEBOOK'))
    self.assertIn('keyboard', manager.GetComponentClasses('CHROMEBOOK'))
    self.assertIn('volatile_a', manager.GetComponentClasses('CHROMEBOOK'))

  def testGetComponentsNonExistentBoard(self):
    """Test that a non-existent board raises a BoardNotFoundError."""
    manager = self._GetManager(load_blobstore=False, load_datastore=False)

    self.assertRaises(hwid_manager.BoardNotFoundError, manager.GetComponents,
                      'CHROMEBOOK', None)

  def testGetComponentsExistingBoard(self):
    """Test that a valid board returns a result."""
    manager = self._GetManager()

    self.assertIn(('audio_codec', {'max98095'}),
                  list(manager.GetComponents('CHROMEBOOK', None).items()))
    self.assertIn(('cellular', {'novatel_e396_3g'}),
                  list(manager.GetComponents('CHROMEBOOK', None).items()))
    self.assertIn(('keyboard', {'kbd_us', 'kbd_gb'}),
                  list(manager.GetComponents('CHROMEBOOK', None).items()))
    self.assertIn(('volatile_a', {'test_volatile'}),
                  list(manager.GetComponents('CHROMEBOOK', None).items()))
    self.assertIn(('ro_main_firmware_0', set(['mv2#volatile_hash#test_bios'])),
                  list(manager.GetComponents('CHROMEBOOK', None).items()))

  def testCache(self):
    """Test that caching limits the number of files read to one."""
    mock_storage = mock.Mock()
    mock_storage.ReadFile.return_value = GOLDEN_HWIDV2_DATA

    manager = self._GetManager(adapter=mock_storage)

    self.assertIsNone(manager.GetBoardDataFromCache('CHROMEBOOK'))
    self.assertIsNotNone(manager.GetBomAndConfigless(TEST_V2_HWID)[0])
    self.assertIsNotNone(manager.GetBoardDataFromCache('CHROMEBOOK'))
    self.assertIsNotNone(manager.GetBomAndConfigless(TEST_V2_HWID)[0])
    self.assertIsNotNone(manager.GetBoardDataFromCache('CHROMEBOOK'))
    mock_storage.ReadFile.assert_called_once_with('/live/v2')

  def testInvalidVersion(self):
    mock_storage = mock.Mock()
    mock_storage.ReadFile.return_value = 'junk data'

    manager = self._GetManager(adapter=mock_storage, load_datastore=False)

    manager.RegisterBoard('CHROMEBOOK', 10, 'v10')

    self.assertRaises(hwid_manager.MetadataError, manager.GetBomAndConfigless,
                      'CHROMEBOOK FOOBAR')
    mock_storage.ReadFile.assert_called_once_with('/live/v10')

  def testRegisterTwice(self):
    manager = self._GetManager()

    manager.RegisterBoard('CHROMEBOOK', 2, 'v2')
    manager.RegisterBoard('CHROMEBOOK', 2, 'v2')

    self.assertEqual(1, hwid_manager.HwidMetadata.all().count())

  def testReloadCache(self):
    """Test that reloading re-reads the data."""
    mock_storage = mock.Mock()
    mock_storage.ReadFile.return_value = GOLDEN_HWIDV2_DATA

    manager = self._GetManager(adapter=mock_storage)

    self.assertIsNone(manager.GetBoardDataFromCache('CHROMEBOOK'))

    manager.ReloadMemcacheCacheFromFiles()

    self.assertIsNotNone(manager.GetBoardDataFromCache('CHROMEBOOK'))
    mock_storage.ReadFile.assert_called_once_with('/live/v2')

  def testReloadCacheMultipleFiles(self):
    """When reloading and there are multiple files then both get read."""
    manager = self._GetManager()

    manager.RegisterBoard('CHROMEBOOK', 2, 'v2')
    manager.RegisterBoard('CHROMEBOOK', 3, 'v3')

    manager.ReloadMemcacheCacheFromFiles()

    # We no longer allow composite HWID objects that have v2 and v3 definitions
    # last RegisterBoard command wins, so check that a V3 HWID is available.
    self.assertIsNotNone(manager.GetBoardDataFromCache('CHROMEBOOK'))
    self.assertIsNotNone(manager.GetBomAndConfigless(TEST_V3_HWID)[0])

  def testUpdateBoards(self):
    """Test the board updater adds a board."""
    mock_storage = mock.Mock()
    mock_storage.ReadFile.return_value = 'junk data'

    manager = self._GetManager(adapter=mock_storage, load_datastore=False)

    hwid_manager.HwidMetadata(board='old_file', path='old', version='2').put()
    hwid_manager.HwidMetadata(
        board='update_file', path='update', version='2').put()

    manager.UpdateBoards({
        'update': {
            'board': 'update_file - updated',
            'version': 2,
            'path': 'v2',
        },
        'new': {
            'board': 'new_file',
            'version': 2,
            'path': 'v2',
        },
    })

    self.assertIsNone(hwid_manager.HwidMetadata.all().filter('path =',
                                                             'old').get())
    self.assertIsNotNone(hwid_manager.HwidMetadata.all().filter(
        'path =', 'update').get())
    self.assertIsNotNone(hwid_manager.HwidMetadata.all().filter(
        'path =', 'new').get())
    mock_storage.DeleteFile.assert_called_once_with('/live/old')
    mock_storage.WriteFile.assert_has_calls(
        [mock.call('/live/update', mock.ANY),
         mock.call('/live/new', mock.ANY)],
        any_order=True)
    self.assertEqual(mock_storage.WriteFile.call_count, 2)
    mock_storage.ReadFile.assert_has_calls(
        [mock.call('/staging/v2') for unused_i in range(2)])
    self.assertEqual(mock_storage.ReadFile.call_count, 2)

  def testUpdateBoardsWithManyBoards(self):
    """Tests that the updating logic can handle many boards.

    There is a limit on datastore that it can only handle IN queries with at
    most 30 options.
    """
    mock_storage = mock.Mock()
    mock_storage.ReadFile.return_value = 'junk data'
    BOARD_COUNT = 40

    for i in range(BOARD_COUNT):
      hwid_manager.HwidMetadata(
          board='old_file' + str(i), path='old' + str(i), version='2').put()

      hwid_manager.HwidMetadata(
          board='update_file' + str(i), path='update' + str(i),
          version='2').put()

    deletefile_calls = [mock.call('/live/old' + str(i)) for i in range(40)]
    writefile_calls = [
        mock.call('/live/update' + str(i), mock.ANY) for i in range(40)
    ]
    manager = self._GetManager(adapter=mock_storage, load_datastore=False)

    board_data = {}
    for i in range(BOARD_COUNT):
      board_data['update' + str(i)] = {
          'board': 'update_file' + str(i),
          'version': 2,
          'path': 'v2'
      }

    manager.UpdateBoards(board_data)

    for i in range(BOARD_COUNT):
      self.assertIsNone(hwid_manager.HwidMetadata.all().filter(
          'path =', 'old' + str(i)).get())
      self.assertIsNotNone(hwid_manager.HwidMetadata.all().filter(
          'path =', 'update' + str(i)).get())

    mock_storage.DeleteFile.assert_has_calls(deletefile_calls, any_order=True)
    self.assertEqual(BOARD_COUNT, mock_storage.DeleteFile.call_count)
    mock_storage.WriteFile.assert_has_calls(writefile_calls, any_order=True)
    self.assertEqual(BOARD_COUNT, mock_storage.WriteFile.call_count)
    mock_storage.ReadFile.assert_has_calls(
        [mock.call('/staging/v2') for unused_c in range(BOARD_COUNT)])
    self.assertEqual(BOARD_COUNT, mock_storage.ReadFile.call_count)

  def testUpdateBoardsWithBadData(self):
    manager = self._GetManager(load_blobstore=False, load_datastore=False)

    self.assertRaises(hwid_manager.MetadataError, manager.UpdateBoards, {
        'test': {}
    })


class HwidDataTest(unittest.TestCase):
  """Tests the _HwidData class."""

  def setUp(self):
    super(HwidDataTest, self).setUp()
    self.data = hwid_manager._HwidData()

  def testNoConfig(self):
    self.assertRaises(hwid_manager.MetadataError, self.data._Seed)

  def testSeedWithFile(self):
    with patch.object(self.data, '_SeedFromRawYaml') as _mock:
      self.data._Seed(hwid_file=GOLDEN_HWIDV2_FILE)
    _mock.assert_called_once_with(mock.ANY)

  def testSeedWithBadFile(self):
    self.assertRaises(
        hwid_manager.MetadataError,
        self.data._Seed,
        hwid_file='/non/existent/file')

  def testSeedWithString(self):
    with patch.object(self.data, '_SeedFromRawYaml') as _mock:
      self.data._Seed(raw_hwid_yaml='{}')
    _mock.assert_called_once_with('{}')

  def testSeedWithData(self):
    with patch.object(self.data, '_SeedFromData') as _mock:
      self.data._Seed(hwid_data={'foo': 'bar'})
    _mock.assert_called_once_with({'foo': 'bar'})

  def testUnimplemented(self):
    self.assertRaises(NotImplementedError, self.data._SeedFromData, None)
    self.assertRaises(NotImplementedError, self.data.GetBomAndConfigless, None)
    self.assertRaises(NotImplementedError, self.data.GetHwids, None, None, None,
                      None, None)
    self.assertRaises(NotImplementedError, self.data.GetComponentClasses, None)
    self.assertRaises(NotImplementedError, self.data.GetComponents, None, None)


class HwidV2DataTest(unittest.TestCase):
  """Tests the HwidV2Data class."""

  def setUp(self):
    super(HwidV2DataTest, self).setUp()

    self.data = self._LoadFromGoldenFile()

  def _LoadFromGoldenFile(self):
    return hwid_manager._HwidV2Data('CHROMEBOOK', hwid_file=GOLDEN_HWIDV2_FILE)

  def testSplitHwid(self):
    """Tests HWIDv2 splitting."""

    # Test HWIDs with no dashes in the name
    self.assertEqual(('CHROMEBOOK', 'BAKER', None, None),
                     self.data._SplitHwid(TEST_V2_HWID_NO_VAR))
    self.assertEqual(('CHROMEBOOK', 'BAKER', 'A', None),
                     self.data._SplitHwid(TEST_V2_HWID_NO_VOL))
    self.assertEqual(('CHROMEBOOK', 'BAKER', 'A', 'A'),
                     self.data._SplitHwid(TEST_V2_HWID))

    self.assertRaises(hwid_manager.InvalidHwidError, self.data._SplitHwid, '')
    self.assertRaises(hwid_manager.InvalidHwidError, self.data._SplitHwid,
                      'FOO')

    # Test HWIDs with one dash in the name
    self.assertEqual(('CHROMEBOOK', 'BAKER-ALFA', None, None),
                     self.data._SplitHwid(TEST_V2_HWID_ONE_DASH_NO_VAR))
    self.assertEqual(('CHROMEBOOK', 'BAKER-ALFA', 'A', None),
                     self.data._SplitHwid(TEST_V2_HWID_ONE_DASH_NO_VOL))
    self.assertEqual(('CHROMEBOOK', 'BAKER-ALFA', 'A', 'A'),
                     self.data._SplitHwid(TEST_V2_HWID_ONE_DASH))

    # Test HWIDs with two dashes in the name
    self.assertEqual(('CHROMEBOOK', 'BAKER-ALFA-BETA', None, None),
                     self.data._SplitHwid(TEST_V2_HWID_TWO_DASH_NO_VAR))
    self.assertEqual(('CHROMEBOOK', 'BAKER-ALFA-BETA', 'A', None),
                     self.data._SplitHwid(TEST_V2_HWID_TWO_DASH_NO_VOL))
    self.assertEqual(('CHROMEBOOK', 'BAKER-ALFA-BETA', 'A', 'A'),
                     self.data._SplitHwid(TEST_V2_HWID_TWO_DASH))

  def testInvalidSeedData(self):
    """Tests that loading invalid data throws an error."""

    self.assertRaises(
        hwid_manager.MetadataError,
        hwid_manager._HwidV2Data,
        'CHROMEBOOK',
        raw_hwid_yaml='{}')

  def testGetBom(self):
    """Tests fetching a BOM."""
    bom, configless = self.data.GetBomAndConfigless(TEST_V2_HWID)

    self.assertTrue(bom.HasComponent(hwid_manager.Component('chipset', 'snow')))
    self.assertTrue(
        bom.HasComponent(hwid_manager.Component('keyboard', 'kbd_us')))
    self.assertTrue(
        bom.HasComponent(hwid_manager.Component('volatile_a', 'test_volatile')))

    bom, configless = self.data.GetBomAndConfigless(TEST_V2_HWID_NO_VAR)

    self.assertTrue(bom.HasComponent(hwid_manager.Component('chipset', 'snow')))
    self.assertEqual([], bom.GetComponents('keyboard'))
    self.assertNotIn([], bom.GetComponents('volatile_a'))
    self.assertEqual(None, configless)

    self.assertRaises(hwid_manager.BoardMismatchError,
                      self.data.GetBomAndConfigless, 'NOTCHROMEBOOK HWID')

    self.assertRaises(hwid_manager.HwidNotFoundError,
                      self.data.GetBomAndConfigless,
                      TEST_V2_HWID_NO_VAR + ' FOO')
    self.assertRaises(hwid_manager.HwidNotFoundError,
                      self.data.GetBomAndConfigless,
                      TEST_V2_HWID_NO_VAR + ' A-FOO')

    self.assertEqual('CHROMEBOOK', bom.board)

  def testGetHwids(self):
    """Tests fetching all HWIDS for a board."""
    hwids = self.data.GetHwids('CHROMEBOOK', None, None, None, None)

    self.assertIsNotNone(hwids)
    self.assertEqual(4, len(hwids))
    self.assertIn('BAKER', hwids)
    self.assertIn('BRIDGE', hwids)

    self.assertRaises(hwid_manager.BoardMismatchError, self.data.GetHwids,
                      'NOTCHROMEBOOK HWID', None, None, None, None)

    test_cases = [({'BAKER', 'BAXTER', 'BLANCA'}, {
        'with_classes': {'volatile_a'}
    }), ({'BLANCA', 'BRIDGE'}, {
        'with_classes': {'cellular'}
    }), ({'BRIDGE'}, {
        'without_classes': {'volatile_a'}
    }), ({'BAKER', 'BAXTER'}, {
        'without_classes': {'cellular'}
    }), ({'BAXTER', 'BRIDGE'}, {
        'with_components': {'winbond_w25q32dw'}
    }), ({'BAKER', 'BLANCA'}, {
        'without_components': {'winbond_w25q32dw'}
    }), ({'BRIDGE'}, {
        'with_classes': {'cellular'},
        'with_components': {'winbond_w25q32dw'}
    }), ({'BAKER'}, {
        'without_classes': {'cellular'},
        'without_components': {'winbond_w25q32dw'}
    }), ({'BLANCA'}, {
        'with_classes': {'cellular'},
        'without_components': {'winbond_w25q32dw'}
    }), ({'BAXTER'}, {
        'without_classes': {'cellular'},
        'with_components': {'winbond_w25q32dw'}
    }), (set(), {
        'with_classes': {'FAKE_CLASS'}
    }), ({'BAKER', 'BAXTER', 'BLANCA', 'BRIDGE'}, {
        'without_classes': {'FAKE_CLASS'}
    }), (set(), {
        'with_components': {'FAKE_COMPONENT'}
    }), ({'BAKER', 'BAXTER', 'BLANCA', 'BRIDGE'}, {
        'without_components': {'FAKE_COMPONENT'}
    }), ({'BAKER', 'BAXTER'}, {
        'with_components': {'exynos_snow0'}
    }), ({'BAKER', 'BLANCA'}, {
        'with_components': {'exynos_snow1'}
    }), ({'BAKER'}, {
        'with_components': {'exynos_snow0', 'exynos_snow1'}
    })]

    for hwids, filters in test_cases:
      self.assertEqual(hwids, self.data.GetHwids('CHROMEBOOK', **filters))

  def testGetComponentClasses(self):
    """Tests fetching all component classes for a board."""
    classes = self.data.GetComponentClasses('CHROMEBOOK')

    self.assertIsNotNone(classes)
    self.assertEqual(17, len(classes))
    self.assertIn('audio_codec', classes)
    self.assertIn('cellular', classes)
    self.assertIn('keyboard', classes)
    self.assertIn('volatile_a', classes)

    self.assertRaises(hwid_manager.BoardMismatchError,
                      self.data.GetComponentClasses, 'NOTCHROMEBOOK HWID')

  def testGetComponents(self):
    """Tests fetching all components for a board."""
    components = self.data.GetComponents('CHROMEBOOK')

    self.assertIn(('audio_codec', set(['max98095'])), list(components.items()))
    self.assertIn(('cellular', set(['novatel_e396_3g'])),
                  list(components.items()))
    self.assertIn(('keyboard', set(['kbd_us', 'kbd_gb'])),
                  list(components.items()))
    self.assertIn(('volatile_a', set(['test_volatile'])),
                  list(components.items()))
    self.assertIn(('ro_main_firmware_0', set(['mv2#volatile_hash#test_bios'])),
                  list(components.items()))

    self.assertRaises(hwid_manager.BoardMismatchError,
                      self.data.GetComponentClasses, 'NOTCHROMEBOOK HWID')

    # Test with_classes filter
    components = {'flash_chip': {'gigadevice_gd25lq32', 'winbond_w25q32dw'}}
    self.assertEqual(components,
                     self.data.GetComponents(
                         'CHROMEBOOK', with_classes={'flash_chip'}))
    components = {
        'flash_chip': {'gigadevice_gd25lq32', 'winbond_w25q32dw'},
        'keyboard': {'kbd_us', 'kbd_gb'}
    }
    self.assertEqual(components,
                     self.data.GetComponents(
                         'CHROMEBOOK', with_classes={'flash_chip', 'keyboard'}))

    # Test classes with multiple components
    components = {
        'usb_hosts': {
            'exynos_snow0', 'exynos_snow1', 'exynos_snow2', 'exynos_snow3'
        }
    }
    self.assertEqual(components,
                     self.data.GetComponents(
                         'CHROMEBOOK', with_classes={'usb_hosts'}))


class HwidV3DataTest(unittest.TestCase):
  """Tests the HwidV3Data class."""

  def setUp(self):
    super(HwidV3DataTest, self).setUp()
    self.data = self._LoadFromGoldenFile()

  def _LoadFromGoldenFile(self):
    return hwid_manager._HwidV3Data('CHROMEBOOK', hwid_file=GOLDEN_HWIDV3_FILE)

  def testGetBom(self):
    """Tests fetching a BOM."""
    bom, configless = self.data.GetBomAndConfigless(TEST_V3_HWID)

    self.assertIn(
        hwid_manager.Component('chipset', 'chipset_0'),
        bom.GetComponents('chipset'))
    self.assertIn(
        hwid_manager.Component('keyboard', 'keyboard_us'),
        bom.GetComponents('keyboard'))
    self.assertIn(
        hwid_manager.Component('dram', 'dram_0'), bom.GetComponents('dram'))
    self.assertEqual('EVT', bom.phase)
    self.assertEqual('CHROMEBOOK', bom.board)
    self.assertEqual(None, configless)

    self.assertRaises(hwid_manager.HwidNotFoundError,
                      self.data.GetBomAndConfigless, 'NOTCHROMEBOOK HWID')

  def testGetBomWithConfigless(self):
    """Tests fetching a BOM."""
    bom, configless = self.data.GetBomAndConfigless(
        TEST_V3_HWID_WITH_CONFIGLESS)

    self.assertIn(
        hwid_manager.Component('chipset', 'chipset_0'),
        bom.GetComponents('chipset'))
    self.assertIn(
        hwid_manager.Component('keyboard', 'keyboard_us'),
        bom.GetComponents('keyboard'))
    self.assertIn(
        hwid_manager.Component('dram', 'dram_0'), bom.GetComponents('dram'))
    self.assertEqual('EVT', bom.phase)
    self.assertEqual('CHROMEBOOK', bom.board)
    self.assertEqual(
        {
            'version': 0,
            'memory': 8,
            'storage': 116,
            'feature_list': {
                'has_fingerprint': 0,
                'has_front_camera': 0,
                'has_rear_camera': 0,
                'has_stylus': 0,
                'has_touchpad': 0,
                'has_touchscreen': 1,
                'is_convertible': 0,
                'is_rma_device': 0
            }
        }, configless)

    self.assertRaises(hwid_manager.HwidNotFoundError,
                      self.data.GetBomAndConfigless, 'NOTCHROMEBOOK HWID')

  def testGetHwids(self):
    self.assertRaises(NotImplementedError, self.data.GetHwids,
                      'NOTCHROMEBOOK HWID', None, None, None, None)

  def testGetComponentClasses(self):
    self.assertRaises(NotImplementedError, self.data.GetComponentClasses,
                      'NOTCHROMEBOOK HWID')

  def testGetComponents(self):
    self.assertRaises(NotImplementedError, self.data.GetComponents,
                      'NOTCHROMEBOOK HWID', None)


class ComponentTest(unittest.TestCase):
  """Tests the Component class."""

  def testEquality(self):
    self.assertEqual(
        hwid_manager.Component('foo', 'bar'),
        hwid_manager.Component('foo', 'bar'))

  def testHash(self):
    """Tests that two equal objects have the same hash."""
    self.assertEqual(
        hash(hwid_manager.Component('foo', 'bar')),
        hash(hwid_manager.Component('foo', 'bar')))
    self.assertEqual(
        hash(hwid_manager.Component('foo', None)),
        hash(hwid_manager.Component('foo', None)))


class BomTest(unittest.TestCase):
  """Tests the Bom class."""

  def setUp(self):
    super(BomTest, self).setUp()
    self.bom = hwid_manager.Bom()

  def testComponentsAddNoneClass(self):
    self.bom.AddComponent(None, 'foo')
    self._AssertHasComponent(None, 'foo')

  def testComponentsAddNone(self):
    self.bom.AddComponent('foo', None)
    self.bom.AddComponent('foo', None)
    self.bom.AddComponent('foo', None)
    self._AssertHasComponent('foo', None)

  def testComponentsOverrideNone(self):
    self.bom.AddComponent('foo', None)
    self.bom.AddComponent('foo', 'bar')
    self.bom.AddComponent('foo', None)

    self._AssertHasComponent('foo', 'bar')

  def testComponentsAppend(self):
    self.bom.AddComponent('foo', 'bar')
    self.bom.AddComponent('foo', 'baz')

    self._AssertHasComponent('foo', 'bar')
    self._AssertHasComponent('foo', 'baz')

  def testMultipleComponents(self):
    self.bom.AddComponent('foo', 'bar')
    self.bom.AddComponent('baz', 'qux')

    self._AssertHasComponent('foo', 'bar')
    self._AssertHasComponent('baz', 'qux')

  def testAddAllComponents(self):
    self.bom.AddAllComponents({'foo': 'bar', 'baz': ['qux', 'rox']})

    self._AssertHasComponent('foo', 'bar')
    self._AssertHasComponent('baz', 'qux')
    self._AssertHasComponent('baz', 'rox')

  def testGetComponents(self):
    self.bom.AddComponent('foo', 'bar')
    self.bom.AddComponent('baz', 'qux')
    self.bom.AddComponent('baz', 'rox')
    self.bom.AddComponent('zib', None)

    components = self.bom.GetComponents()

    self.assertEqual(4, len(components))
    self.assertIn(hwid_manager.Component('foo', 'bar'), components)
    self.assertIn(hwid_manager.Component('baz', 'qux'), components)
    self.assertIn(hwid_manager.Component('baz', 'rox'), components)
    self.assertIn(hwid_manager.Component('zib', None), components)

    self.assertEqual([hwid_manager.Component('foo', 'bar')],
                     self.bom.GetComponents('foo'))
    self.assertEqual([], self.bom.GetComponents('empty-class'))

  def _AssertHasComponent(self, cls, name):
    self.assertIn(cls, self.bom._components)
    if name:
      self.assertIn(name, self.bom._components[cls])
    else:
      self.assertEqual([], self.bom._components[cls])


class NormalizationTest(unittest.TestCase):
  """Tests the _NormalizeString function."""

  def testNormalization(self):
    self.assertEqual('ALPHA', hwid_manager._NormalizeString('alpha'))
    self.assertEqual('ALPHA', hwid_manager._NormalizeString('aLpHa'))
    self.assertEqual('ALPHA', hwid_manager._NormalizeString('ALPHA'))
    self.assertEqual('ALPHA', hwid_manager._NormalizeString('  alpha  '))
    self.assertEqual('BETA', hwid_manager._NormalizeString('beta'))


class VerifyBoardMetadataTest(unittest.TestCase):
  """Tests the _VerifyBoardMetadata function."""

  def testVerifyBoardMetadata(self):
    hwid_manager._VerifyBoardMetadata({})
    hwid_manager._VerifyBoardMetadata({
        'test': {
            'path': 'file',
            'version': 3,
            'board': 'CHROMEBOOK'
        }
    })
    self.assertRaises(hwid_manager.MetadataError,
                      hwid_manager._VerifyBoardMetadata, {
                          'test': {
                              'version': 3,
                              'board': 'CHROMEBOOK'
                          }
                      })
    self.assertRaises(hwid_manager.MetadataError,
                      hwid_manager._VerifyBoardMetadata, {
                          'test': {
                              'path': 'file',
                              'board': 'CHROMEBOOK'
                          }
                      })
    self.assertRaises(hwid_manager.MetadataError,
                      hwid_manager._VerifyBoardMetadata, {
                          'test': {
                              'path': 'file',
                              'version': 3
                          }
                      })


if __name__ == '__main__':
  unittest.main()
