# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Classes for managing and querying HWID information.

This module should provide a unified interface for querying HWID information
regardless of the source of that information or the version.
"""

import collections
import copy
import logging
import re

from google.cloud import ndb  # pylint: disable=no-name-in-module, import-error

from cros.factory.hwid.service.appengine import memcache_adapter
from cros.factory.hwid.service.appengine import \
    verification_payload_generator as vpg_module
from cros.factory.hwid.v3 import common
from cros.factory.hwid.v3 import database
from cros.factory.hwid.v3 import hwid_utils
from cros.factory.hwid.v3 import yaml_wrapper as yaml
from cros.factory.utils import type_utils


class BoardNotFoundError(KeyError):
  """Indicates that the specified board was not found."""


class TooManyBoardsFound(Exception):
  """There is more than one entry for a particular board in datastore."""


class HwidNotFoundError(KeyError):
  """Indicates a HWID does not map to a valid value.

  The HWID is still in a valid format.
  """


class InvalidHwidError(ValueError):
  """Indicates a HWID is malformed."""


class BoardMismatchError(ValueError):
  """Indicates that a HWID does does not match the expected board."""

  def __init__(self, expected, actual):
    super(BoardMismatchError, self).__init__('HWID %r does not match board %r.',
                                             (actual, expected))


class MetadataError(ValueError):
  """Indicates an error occurred while loading or parsing HWID metadata."""


class HwidMetadata(ndb.Model):  # pylint: disable=no-init
  """Metadata about HWID boards and information.

  This tracks the information about HWID file for a given board.  It is unique
  per path, as each file is assumed to apply to only one board (the same file
  can be uploaded multiple times, but will be uploaded as separate files).  The
  path thus acts as the unique key.
  """

  board = ndb.StringProperty()
  path = ndb.StringProperty()
  version = ndb.StringProperty()


class CLNotification(ndb.Model):  # pylint: disable=no-init
  """Emails of CL notification recipients."""

  notification_type = ndb.StringProperty()
  email = ndb.StringProperty()


class LatestHWIDMasterCommit(ndb.Model):  # pylint: disable=no-init
  """Latest master commit of private overlay repo with generated payloads."""

  commit = ndb.StringProperty()


class LatestPayloadHash(ndb.Model):  # pylint: disable=no-init
  """Latest hash of payload generated from verification_payload_generator."""

  payload_hash = ndb.StringProperty()


class AVLNameMapping(ndb.Model):

  category = ndb.StringProperty()
  component_id = ndb.IntegerProperty()
  name = ndb.StringProperty()


class Component(
    collections.namedtuple(
        'Component',
        ['cls', 'name', 'information', 'is_vp_related', 'fields'])):
  """A single BOM component.

  Attributes:
    cls string The component-class.
    name string The canonical name.
    information dict (optional) The extra information bound with the component.
    is_vp_related bool Whether this component is a source of the verification
        payload.
    fields dict (optional) The detail fields of the component.
  """

  def __new__(cls, cls_, name, information=None, is_vp_related=False,
              fields=None):
    if fields is None:
      fields = {}
    return super(Component, cls).__new__(cls, cls_, name, information,
                                         is_vp_related, fields)


class Label(collections.namedtuple('Label', ['cls', 'name', 'value'])):
  """A BOM label.

  Attributes:
    cls string The component-class.
    name string The label name.
    value string The value for this label, if any.
  """


class Bom:
  """An abstraction of a BOM with both components and labels."""

  def __init__(self):
    self._components = {}
    self._labels = {}
    self.phase = ''
    self.board = None

  def HasComponent(self, component):
    """Tests whether the bom has a component."""
    return (component.cls in self._components and
            any(component.name == comp.name for comp in
                self._components[component.cls]))

  def GetComponents(self, cls=None):
    """Gets the components of this bom, optionally filtered by class."""
    if cls:
      if cls not in self._components:
        return []
      if not self._components[cls]:
        return [Component(cls, None, None)]
      return copy.deepcopy(self._components[cls])

    components = []
    for comp_class, comps in self._components.items():
      if comps == list():
        components.append(Component(comp_class, None, None))
      else:
        components.extend(copy.deepcopy(comps))

    return components

  def AddComponent(self, cls, name=None, information=None, is_vp_related=False,
                   fields=None):
    """Adds a component to this bom.

    The method must be supplied at least a component class.  If no name is
    specified then the component class will be present but empty.

    Args:
      cls: The component class.
      name: The name of the bom.
      information: (optional) The extra information bound with the
                   component.
      fields dict (optional) The detail fields of the component.
    """
    if cls not in self._components:
      self._components[cls] = []

    if name:
      self._components[cls].append(
          Component(cls, name, information, is_vp_related, fields))

  def AddAllComponents(self, component_dict, comp_db=None, verbose=False,
                       waived_comp_categories=None):
    """Adds a dict of components to this bom.

    This dict should be of the form class -> name and can take either a single
    name or list of names in each entry.  This makes it easy to add all
    components as extract from a YAML file or similar.

    Args:
      component_dict: A dictionary of components to add.
      comp_db: The database for additional component information retrieval.
      verbose: Adds all fields of the component detail if set to True.
      waived_comp_categories: List of waived component categories which means
      they are not verification-payload-related.
    Returns:
      self
    Raises:
      ValueError: if any of the classes are None.
    """
    if waived_comp_categories is None:
      waived_comp_categories = []
    if comp_db:
      vp_related_comps = set(
          vpg_module.GetAllComponentVerificationPayloadPieces(
              comp_db, waived_comp_categories))
    else:
      vp_related_comps = set()

    for component_class, component_val in component_dict.items():
      db_components = comp_db and comp_db.GetComponents(component_class)
      if isinstance(component_val, str):
        comp_info = db_components and db_components.get(component_val)
        fields = comp_info.values if verbose and comp_info else None
        self.AddComponent(component_class, component_dict[component_class],
                          comp_info and comp_info.information,
                          (component_class, component_val) in vp_related_comps,
                          fields)
      else:
        for component_name in component_val:
          if isinstance(component_name, str):
            comp_info = db_components and db_components.get(component_name)
            fields = comp_info.values if verbose and comp_info else None
            self.AddComponent(component_class, component_name, comp_info and
                              comp_info.information,
                              (component_class, component_name)
                              in vp_related_comps, fields)

  def HasLabel(self, label):
    """Test whether the BOM has a label."""
    return label.cls in self._labels and label.name in self._labels[label.cls]

  def GetLabels(self, cls=None):
    """Gets the labels of this bom, optionally filtered by class."""
    if cls:
      if cls in self._labels:
        return [
            Label(cls, name, value)
            for name, values in self._labels[cls].items()
            for value in values
        ]
      return []
    return [
        Label(cls, name, value) for cls in self._labels
        for name, values in self._labels[cls].items() for value in values
    ]

  def AddLabel(self, cls, name, value=None):
    """Adds a label to this bom.

    The method must be supplied at least a label name.  If no class is
    specified then the label is assumed to be on the BOM as a whole.

    Args:
      cls: The component class.
      name: The name of the label.
      value: (optional) The label value or True for a valueless label.
    Returns:
      self
    Raises:
      ValueError: when no name is specified.
    """
    if not cls or not name:
      raise ValueError('Labels must have a class and name.')

    if cls not in self._labels:
      self._labels[cls] = {}

    if name in self._labels[cls]:
      self._labels[cls][name].append(value)
    else:
      self._labels[cls][name] = [value]

  def AddAllLabels(self, label_dict):
    """Adds a dict of labels to this bom.

    Args:
      label_dict: A dictionary with {class: {name: value}} mappings.
    Returns:
      self
    Raises:
      ValueError: if any of the values are None.
    """

    for cls in label_dict:
      for name in label_dict[cls]:
        value = label_dict[cls][name]
        self.AddLabel(cls, name, value)


class HwidManager:
  """The HWID Manager class itself.

  This is the class that should be instantiated elsewhere to query HWID
  information.
  """

  def __init__(self, fs_adapter, vpg_targets):
    self._fs_adapter = fs_adapter
    self._vpg_targets = vpg_targets
    self._memcache_adapter = memcache_adapter.MemcacheAdapter(
        namespace='HWIDObject')

  @type_utils.LazyProperty
  def _ndb_client(self):
    return ndb.Client()

  @type_utils.LazyProperty
  def _global_cache(self):
    return ndb.RedisCache.from_environment()

  @staticmethod
  def GetVerificationPayloadSettings(board):
    """Get repo settings for specific board.

    Args:
      board: The board name

    Returns:
      A dictionary with corresponding settings
    """
    return {
        'review_host':
            'https://chrome-internal-review.googlesource.com',
        'repo_host':
            'https://chrome-internal.googlesource.com',
        'repo_path':
            '/chromeos/overlays/overlay-{board}-private'.format(board=board),
        'project': ('chromeos/overlays/'
                    'overlay-{board}-private').format(board=board),
        'prefix': ('chromeos-base/'
                   'racc-config-{board}/files/').format(board=board),
        'branch':
            'master'
    }

  def GetBoards(self, versions=None):
    """Get a list of supported boards.

    Args:
      versions: List of BOM file versions to include.

    Returns:
      A list of boards.
    """
    logging.debug('Getting boards for versions: {0}'.format(versions)
                  if versions else 'Getting boards')
    with self._ndb_client.context(global_cache=self._global_cache):
      if versions:
        return set(metadata.board
                   for metadata in HwidMetadata.query()
                   if metadata.version in versions)
      return set(metadata.board for metadata in HwidMetadata.query())

  def GetBomAndConfigless(self, hwid_string, verbose=False):
    """Get the BOM and configless for a given HWID.

    Args:
      hwid_string: The HWID.
      verbose: Requires all fields of components in bom if set to True.

    Returns:
      A bom dict and configless field dict.
      If there is no configless field in given HWID, return Bom dict and None.

    Raises:
      HwidNotFoundError: If a portion of the HWID is not found.
      InvalidHwidError: If the HWID is invalid.
    """
    logging.debug('Getting BOM for %r.', hwid_string)
    board_and_brand, unusedi, unusedj = hwid_string.partition(' ')
    board, unusedi, unusedj = board_and_brand.partition('-')
    del unusedi  # unused
    del unusedj  # unused

    model_info = self._vpg_targets.get(board)
    waived_comp_categories = model_info and model_info.waived_comp_categories

    hwid_data = self._LoadHwidData(board)

    return hwid_data.GetBomAndConfigless(hwid_string, verbose,
                                         waived_comp_categories)

  def GetHwids(self,
               board,
               with_classes=None,
               without_classes=None,
               with_components=None,
               without_components=None):
    """Get a filtered list of HWIDs for the given board.

    Args:
      board: The board that you want the HWIDs of.
      with_classes: Filter for component classes that the HWIDs include.
      without_classes: Filter for component classes that the HWIDs don't
        include.
      with_components: Filter for components that the HWIDs include.
      without_components: Filter for components that the HWIDs don't include.

    Returns:
      A list of HWIDs.

    Raises:
      InvalidHwidError: If the board is invalid.
    """
    logging.debug('Getting filtered list of HWIDs for %r.', board)
    hwid_data = self._LoadHwidData(board)

    return list(
        hwid_data.GetHwids(board, with_classes, without_classes,
                           with_components, without_components))

  def GetComponentClasses(self, board):
    """Get a list of all component classes for the given board.

    Args:
      board: The board that you want the component classes of.

    Returns:
      A list of component classes.

    Raises:
      InvalidHwidError: If the board is invalid.
    """
    logging.debug('Getting list of component classes for %r.', board)
    hwid_data = self._LoadHwidData(board)

    return list(hwid_data.GetComponentClasses(board))

  def GetComponents(self, board, with_classes=None):
    """Get a filtered dict of components for the given board.

    Args:
      board: The board that you want the components of.
      with_classes: Filter for component classes that the dict include.

    Returns:
      A dict of components.

    Raises:
      InvalidHwidError: If the board is invalid.
    """
    logging.debug('Getting list of components for %r.', board)
    hwid_data = self._LoadHwidData(board)

    return hwid_data.GetComponents(board, with_classes)

  def GetCLReviewers(self):
    with self._ndb_client.context(global_cache=self._global_cache):
      q = CLNotification.query(CLNotification.notification_type == "reviewer")
      reviewers = []
      for notification in list(q):
        reviewers.append(notification.email.encode('utf-8'))
      return reviewers

  def GetCLCCs(self):
    with self._ndb_client.context(global_cache=self._global_cache):
      q = CLNotification.query(CLNotification.notification_type == "cc")
      ccs = []
      for notification in list(q):
        ccs.append(notification.email.encode('utf-8'))
      return ccs

  def GetLatestHWIDMasterCommit(self):
    with self._ndb_client.context(global_cache=self._global_cache):
      key = ndb.Key(LatestHWIDMasterCommit, 'commit')
      entry = LatestHWIDMasterCommit.query(
          LatestHWIDMasterCommit.key == key).get()
      return entry.commit

  def SetLatestHWIDMasterCommit(self, commit):
    with self._ndb_client.context(global_cache=self._global_cache):
      key = ndb.Key(LatestHWIDMasterCommit, 'commit')
      entity = LatestHWIDMasterCommit.query(
          LatestHWIDMasterCommit.key == key).get()
      entity.commit = commit
      entity.put()

  def GetLatestPayloadHash(self, board):
    with self._ndb_client.context(global_cache=self._global_cache):
      key = ndb.Key(LatestPayloadHash, board)
      entity = LatestPayloadHash.query(LatestPayloadHash.key == key).get()
      if entity is not None:
        return entity.payload_hash
      return None

  def SetLatestPayloadHash(self, board, payload_hash):
    with self._ndb_client.context(global_cache=self._global_cache):
      latest_hash = LatestPayloadHash.get_or_insert(board)
      latest_hash.payload_hash = payload_hash
      latest_hash.put()

  def _LoadHwidData(self, board):
    """Retrieves the HWID data for a given board, caching as necessary.

    Args:
      board: The board to get data for.

    Returns:
      A HwidData object for the board.

    Raises:
      BoardNotFoundError: If no metadata is found for the given board.
      TooManyBoardsFound: If we have more than one metadata entry for the given
        board.
    """

    logging.debug('Loading data for %r.', board)

    board = _NormalizeString(board)

    hwid_data = self.GetBoardDataFromCache(board)

    if hwid_data:
      logging.debug('Found cached data for %r.', board)
      return hwid_data

    with self._ndb_client.context(global_cache=self._global_cache):
      q = HwidMetadata.query(HwidMetadata.board == board)

      if q.count() == 0:
        raise BoardNotFoundError(
            'No metadata present for the requested board: %r' % board)

      if q.count() != 1:
        raise TooManyBoardsFound('Too many boards present for : %r' % board)

      hwid_data = self._LoadHwidFile(q.get())

    self.SaveBoardDataToCache(board, hwid_data)

    return hwid_data

  def _LoadHwidFile(self, metadata):
    """Load hwid data from a file.

    Args:
      metadata: A HwidMetadata object.

    Returns:
      The HwidData object loaded based on the metadata.

    Raises:
      MetadataError: If the metadata references an invalid path or invalid
      version.
    """

    try:
      logging.debug('Reading file %s from live path.', metadata.path)
      raw_hwid_yaml = self._fs_adapter.ReadFile(self._LivePath(metadata.path))
    except Exception as e:
      logging.exception('Missing HWID file: %r', metadata.path)
      raise MetadataError('HWID file missing for the requested board: %r' % e)

    if metadata.version == "2":
      logging.debug("Processing as version 2 file.")
      hwid_data = _HwidV2Data(metadata.board, raw_hwid_yaml=raw_hwid_yaml)
    elif metadata.version == "3":
      logging.debug("Processing as version 3 file.")
      hwid_data = _HwidV3Data(metadata.board, raw_hwid_yaml=raw_hwid_yaml)
    else:
      raise MetadataError('Board %r has invalid version %r.' %
                          (metadata.board, metadata.version))

    return hwid_data

  def RegisterBoard(self, board, version, path):
    """Registers a board with the system.

    This method only registers the metadata.  The hwid data is not loaded until
    requested.

    Args:
      board: The board name
      version: version, e.g. '2'
      path: Path to the file within the filesystem adapter.
    """
    logging.info('Registering board %r at version %r with file %r.', board,
                 version, path)

    board = _NormalizeString(board)

    with self._ndb_client.context(global_cache=self._global_cache):
      q = HwidMetadata.query(HwidMetadata.path == path)
      metadata = q.get()

      if metadata:
        metadata.board = board
        metadata.version = str(version)
      else:
        metadata = HwidMetadata(board=board, version=str(version), path=path)

      metadata.put()

  def SyncAVLNameMapping(self, category, mapping):
    """Sync the set of AVL name mapping to be exactly the mapping provided.

    Args:
      category: The component category
      mapping: The {cid: avl_name} dictionary for updating datastore.
    """

    with self._ndb_client.context(global_cache=self._global_cache):
      cids_to_create = set(mapping)

      q = AVLNameMapping.query(AVLNameMapping.category == category)
      for entry in list(q):
        # Discard the entries indexed by cid.
        if entry.component_id not in mapping:
          entry.key.delete()
        else:
          entry.name = mapping[entry.component_id]
          entry.put()
          cids_to_create.discard(entry.component_id)

      for cid in cids_to_create:
        name = mapping[cid]
        entry = AVLNameMapping(component_id=cid, name=name, category=category)
        entry.put()
    logging.info('AVL name mapping of category "%s" is synced.', category)

  def ListExistingAVLCategories(self):
    with self._ndb_client.context(global_cache=self._global_cache):
      category_set = set()
      for entry in AVLNameMapping.query(
          projection=['category'], distinct_on=['category']):
        category_set.add(entry.category)
      logging.debug('category_set: %s', category_set)
      return category_set

  def RemoveAVLNameMappingCategories(self, category_set):
    with self._ndb_client.context(global_cache=self._global_cache):
      keys_to_delete = []
      for category in category_set:
        logging.info('Add category "%s" to remove', category)
        keys_to_delete += AVLNameMapping.query(
            AVLNameMapping.category == category).fetch(keys_only=True)
      logging.debug('keys_to_delete: %s', keys_to_delete)
      ndb.delete_multi(keys_to_delete)
      logging.info('Extra categories are Removed')

  def UpdateBoards(self, git_fs, board_metadata, delete_missing=True):
    """Updates the set of supported boards to be exactly the list provided.

    Args:
      git_fs: A GitFilesystemAdapter instance to provide filesystem_adapter
          interface of chromeos-hwid repo.
      board_metadata: A list of metadata dictionaries containing path, version
          and board name.
      delete_missing: bool to indicate whether missing metadata should be
          deleted.
    Raises:
      MetadataError: If the metadata is malformed.
    """

    _VerifyBoardMetadata(board_metadata)

    # Discard the names for the entries, indexing only by path.
    with self._ndb_client.context(global_cache=self._global_cache):
      # Note that the term `board` used in HWID Service is not related to the
      # `board` in board_metadata from projects.yaml which means the reference
      # board.  Therefore we will not use the `board` field in board_metadata.
      q = HwidMetadata.query()
      existing_metadata = list(q)
      old_files = set(m.board for m in existing_metadata)
      new_files = set(board_metadata)

      files_to_delete = old_files - new_files
      files_to_create = new_files - old_files

      for hwid_metadata in existing_metadata:
        if hwid_metadata.board in files_to_delete:
          if delete_missing:
            hwid_metadata.key.delete()
            self._fs_adapter.DeleteFile(self._LivePath(hwid_metadata.path))
        else:
          new_data = board_metadata[hwid_metadata.board]
          hwid_metadata.version = str(new_data['version'])
          self._ActivateFile(git_fs, new_data['path'], hwid_metadata.path)
          hwid_metadata.put()

    for board in files_to_create:
      path = board  # Use the board name as the file path.
      new_data = board_metadata[board]
      version = str(new_data['version'])
      with self._ndb_client.context(global_cache=self._global_cache):
        metadata = HwidMetadata(board=board, version=version, path=path)
        self._ActivateFile(git_fs, new_data['path'], path)
        metadata.put()

  def ReloadMemcacheCacheFromFiles(self, limit_models=None):
    """For every known board, load its info into the cache.

    Args:
      limit_models: List of names of models which will be updated.
    """

    with self._ndb_client.context(global_cache=self._global_cache):
      q = HwidMetadata.query()
      if limit_models:
        q = q.filter(HwidMetadata.board.IN(limit_models))

      for metadata in list(q):
        try:
          self._memcache_adapter.Put(metadata.board,
                                     self._LoadHwidFile(metadata))
        except Exception:  # pylint: disable=broad-except
          # Catch any exception and continue with other files.  The reason for
          # the broad exception is that the various exceptions we could catch
          # are large and from libraries out of our control.  For example, the
          # HWIDv3 library can throw various unknown errors.  We could have IO
          # errors, errors with Google Cloud Storage, or YAML parsing errors.
          #
          # This may catch some exceptions we do not wish it to, such as SIGINT,
          # but we expect that to be unlikely in this context and not adversely
          # affect the system.
          logging.exception('Exception encountered while reloading cache.')

  def _LivePath(self, file_id):
    return 'live/%s' % file_id

  def _ActivateFile(self, git_fs, stage_file_path, live_file_id):
    board_data = git_fs.ReadFile(stage_file_path)
    self._fs_adapter.WriteFile(self._LivePath(live_file_id), board_data)

  def _ClearMemcache(self):
    """Clear all cache items via memcache_adapter.

    This method is for testing purpose since each integration test should have
    empty cache in the beginning.
    """
    self._memcache_adapter.ClearAll()

  def GetBoardDataFromCache(self, board):
    """Get the HWID file data from cache.

    There is a two level caching strategy for hwid_data object, first check is
    to the in memory cache.  If the data is not found in memory then we
    attempt to retrieve from memcache.  On memcache success we expand the
    in memory cache with the value retrieved from memcache.

    This allows fast startup of new instances, that slowly get a better and
    better in memory caching.

    Args:
      board: String, the name of the board to retrieve from cache.

    Returns:
       HWIDData object that was cached or null if not found in memory or in the
       memcache.
    """
    hwid_data = self._memcache_adapter.Get(board)
    if not hwid_data:
      logging.info('Memcache read miss %s', board)
    return hwid_data

  def SaveBoardDataToCache(self, board, hwid_data):
    self._memcache_adapter.Put(board, hwid_data)

  def GetAVLName(self, category, comp_name):
    """Get AVL Name from hourly updated mapping data.

    Args:
      category: Component category.
      comp_name: Component name defined in HWID DB.

    Returns:
      comp_name if the name does not follow the <category>_<cid>_<qid>#<comment>
      rule, or the mapped name defined in datastore.
    """
    # Trim the comment part after '#' if any
    comp_name_wo_comment = comp_name.split('#')[0]
    sp = comp_name_wo_comment.split('_')
    if len(sp) != 3:  # <category>, <cid>, <qid>
      return comp_name
    category_in_name, cid, qid = sp
    if category != category_in_name or not cid.isdigit() or not qid.isdigit():
      # does not match naming rule
      return comp_name

    with self._ndb_client.context(global_cache=self._global_cache):
      entry = AVLNameMapping.query(
          AVLNameMapping.category == category,
          AVLNameMapping.component_id == int(cid)).get()
    if entry is None:
      logging.error(
          'mapping not found for category "%s" and component name"%s"',
          category, comp_name)
      return comp_name
    return entry.name


class _HwidData:
  """Superclass for HWID data classes."""

  def _Seed(self, hwid_file=None, raw_hwid_yaml=None, hwid_data=None):
    if hwid_file:
      self._SeedFromYamlFile(hwid_file)
    elif raw_hwid_yaml:
      self._SeedFromRawYaml(raw_hwid_yaml)
    elif hwid_data:
      self._SeedFromData(hwid_data)
    else:
      raise MetadataError('No HWID configuration supplied.')

  def _SeedFromYamlFile(self, hwid_file):
    """Seeds the object from a path to a file containing hwid definitions."""
    try:
      with open(hwid_file, 'r') as fh:
        return self._SeedFromRawYaml(fh.read())
    except IOError as ioe:
      raise MetadataError('Error loading YAML file.', ioe)

  def _SeedFromRawYaml(self, raw_hwid_yaml):
    """Seeds the object from a yaml string of hwid definitions."""
    raise NotImplementedError()

  def _SeedFromData(self, hwid_data):
    """Seeds the object from a dict of hwid definitions."""
    raise NotImplementedError()

  def GetBomAndConfigless(self, hwid_string, verbose=False,
                          waived_comp_categories=None):
    """Get the BOM and configless field for a given HWID.

    Args:
      hwid_string: The HWID.
      verbose: Returns all fields in component detail if set to True.
      waived_comp_categories: List of waived component categories which means
      they are not verification-payload-related.

    Returns:
      A bom dict and configless field dict.
      If there is no configless field in given HWID, return Bom dict and None.

    Raises:
      HwidNotFoundError: If a portion of the HWID is not found.
      InvalidHwidError: If the HWID is invalid.
    """
    raise NotImplementedError()

  def GetHwids(self,
               board,
               with_classes=None,
               without_classes=None,
               with_components=None,
               without_components=None):
    """Get a filtered set of HWIDs for the given board.

    Args:
      board: The board that you want the HWIDs of.
      with_classes: Filter for component classes that the HWIDs include.
      without_classes: Filter for component classes that the HWIDs don't
        include.
      with_components: Filter for components that the HWIDs include.
      without_components: Filter for components that the HWIDs don't include.

    Returns:
      A set of HWIDs.

    Raises:
      InvalidHwidError: If the board is invalid.
    """
    raise NotImplementedError()

  def GetComponentClasses(self, board):
    """Get a set of all component classes for the given board.

    Args:
      board: The board that you want the component classes of.

    Returns:
      A set of component classes.

    Raises:
      InvalidHwidError: If the board is invalid.
    """
    raise NotImplementedError()

  def GetComponents(self, board, with_classes=None):
    """Get a filtered dict of all components for the given board.

    Args:
      board: The board that you want the components of.
      with_classes: Filter for component classes that the dict include.

    Returns:
      A dict of components.

    Raises:
      InvalidHwidError: If the board is invalid.
    """
    raise NotImplementedError()


class _HwidV2Data(_HwidData):
  """Wrapper for HWIDv2 data."""

  def __init__(self, board, hwid_file=None, raw_hwid_yaml=None, hwid_data=None):
    """Constructor.

    Requires one of hwid_file, hwid_yaml or hwid_data.

    Args:
      board: The board name
      hwid_file: the path to a file containing the HWID data.
      hwid_yaml: the raw YAML string of HWID data.
      hwid_data: parsed HWID data from a HWID file.
    """
    self.board = board
    self._bom_map = {}
    self._variant_map = {}
    self._volatile_map = {}
    self._hwid_status_map = {}
    self._volatile_value_map = {}

    self._Seed(hwid_file, raw_hwid_yaml, hwid_data)

  def _SeedFromRawYaml(self, raw_hwid_yaml):
    from cros.factory.hwid.v2 import yaml_datastore
    return self._SeedFromData(yaml_datastore.YamlRead(
        raw_hwid_yaml, yaml.SafeLoader))

  def _SeedFromData(self, hwid_data):
    for field in [
        'boms', 'variants', 'volatiles', 'hwid_status', 'volatile_values'
    ]:
      if field not in hwid_data:
        raise MetadataError('Invalid HWIDv2 file supplied, missing required ' +
                            'field %r' % field)

    for (local_map, data) in [(self._bom_map, hwid_data['boms']),
                              (self._variant_map, hwid_data['variants']),
                              (self._volatile_map, hwid_data['volatiles'])]:
      for name in data:
        normalized_name = _NormalizeString(name)
        local_map[normalized_name] = data[name]
    for (local_map, data) in [(self._hwid_status_map, hwid_data['hwid_status']),
                              (self._volatile_value_map,
                               hwid_data['volatile_values'])]:
      for name in data:
        local_map[name] = data[name]

  def _SplitHwid(self, hwid_string):
    """Splits a HWIDv2 string into component parts.

    Examples matched (board, bom, variant, volatile):
      FOO BAR -> ('FOO', 'BAR', None, None)
      FOO BAR BAZ-QUX -> ('FOO', 'BAR', 'BAZ', 'QUX')
      FOO BAR BAZ-QUX 1234 -> ('FOO', 'BAR', 'BAZ', 'QUX')
      FOO BAR-BAZ -> ('FOO', 'BAR-BAZ', None, None)
      FOO BAR-BAZ QUX -> ('FOO', 'BAR-BAZ', 'QUX', None)
      FOO BAR-BAZ-QUX -> ('FOO', 'BAR-BAZ-QUX', None, None)

    Args:
      hwid_string: The HWIDv2 string in question

    Returns:
      A tuple of the BOM name, variant and volatile.

    Raises:
      InvalidHwidError: if the string is in an invalid format.
    """

    match = re.match(r'\s*(?P<board>\w+)\s+(?P<name>\w+\S+)'
                     r'(\s+(?P<variant>\w+)(-(?P<volatile>\w+))?)?.*',
                     hwid_string)

    if match:
      groups = match.groupdict()
      board = _NormalizeString(groups['board'])
      name = _NormalizeString(groups['name'])
      variant = _NormalizeString(groups['variant'])
      volatile = _NormalizeString(groups['volatile'])

      return (board, name, variant, volatile)

    raise InvalidHwidError('Invalid HWIDv2 format: %r' % hwid_string)

  def GetBomAndConfigless(self, hwid_string, verbose=False,
                          waived_comp_categories=None):
    """Get the BOM and configless field for a given HWID.

    Overrides superclass method.

    Args:
      hwid_string: The HWID string
      verbose: Returns all fields in component detail if set to True.
      waived_comp_categories: List of waived component categories which means
      they are not verification-payload-related.

    Returns:
      A Bom object and None since HWID v2 doesn't support configless field.

    Raises:
      HwidNotFoundError: If a portion of the HWID is not found.
      InvalidHwidError: If the HWID is invalid.
      BoardMismatchError: If the board is invalid.
    """
    board, name, variant, volatile = self._SplitHwid(hwid_string)

    if board != self.board:
      raise BoardMismatchError(hwid_string, board)

    bom = Bom()
    bom.board = self.board

    if name in self._bom_map:
      bom.AddAllComponents(self._bom_map[name]['primary']['components'],
                           verbose=verbose)
    else:
      raise HwidNotFoundError('BOM %r not found for board %r.' % (bom,
                                                                  self.board))

    if variant:
      if variant in self._variant_map:
        bom.AddAllComponents(self._variant_map[variant]['components'],
                             verbose=verbose)
      else:
        raise HwidNotFoundError('variant %r not found for board %r.' %
                                (variant, self.board))

    if volatile:
      if volatile in self._volatile_map:
        bom.AddAllComponents(self._volatile_map[volatile], verbose=verbose)
      else:
        raise HwidNotFoundError('volatile %r not found for board %r.' %
                                (volatile, self.board))

    return bom, None

  def GetHwids(self,
               board,
               with_classes=None,
               without_classes=None,
               with_components=None,
               without_components=None):
    """Get a filtered set of HWIDs for the given board.

    Overrides superclass method.

    Args:
      board: The board that you want the HWIDs of.
      with_classes: Filter for component classes that the HWIDs include.
      without_classes: Filter for component classes that the HWIDs don't
        include.
      with_components: Filter for components that the HWIDs include.
      without_components: Filter for components that the HWIDs don't include.

    Returns:
      A set of HWIDs.

    Raises:
      InvalidHwidError: If the board is invalid.
      BoardMismatchError: If the board is invalid.
    """
    board_string = _NormalizeString(board)

    if board_string != self.board:
      raise BoardMismatchError(board, board_string)

    hwids_set = set()
    for hw in self._bom_map:
      miss_list = self._bom_map[hw]['primary']['classes_missing']
      vol_ltrs = set()
      status_fields = ['deprecated', 'eol', 'qualified', 'supported']
      for field in status_fields:
        for hw_vol in self._hwid_status_map[field]:
          if hw in hw_vol:
            if hw_vol[-1] == '*':
              vol_ltrs.update(self._volatile_map)
            else:
              vol_ltrs.add(hw_vol.rpartition('-')[2])
      items = list(self._bom_map[hw]['primary']['components'].items())
      for var in self._bom_map[hw]['variants']:
        items += list(self._variant_map[var]['components'].items())
      for vol in vol_ltrs:
        for cls, comp in self._volatile_map[vol].items():
          items.append((cls, comp))
          items.append((comp, self._volatile_value_map[comp]))

      # Populate the class set and component set with data from items
      all_classes = set()
      all_components = set()
      for cls, comp in items:
        all_classes.add(cls)
        if isinstance(comp, list):
          all_components.update(comp)
        else:
          all_components.add(comp)

      valid = True
      if with_classes:
        for cls in with_classes:
          if cls in miss_list or cls not in all_classes:
            valid = False
      if without_classes:
        for cls in without_classes:
          if cls not in miss_list and cls in all_classes:
            valid = False
      if with_components:
        for comp in with_components:
          if comp not in all_components:
            valid = False
      if without_components:
        for comp in without_components:
          if comp in all_components:
            valid = False
      if valid:
        hwids_set.add(hw)
    return hwids_set

  def GetComponentClasses(self, board):
    """Get a set of all component classes for the given board.

    Overrides superclass method.

    Args:
      board: The board that you want the component classes of.

    Returns:
      A set of component classes.

    Raises:
      BoardMismatchError: If the board is invalid.
    """
    board_string = _NormalizeString(board)

    if board_string != self.board:
      raise BoardMismatchError(board, board_string)

    classes_set = set()
    for hw in self._bom_map:
      classes_set.update(self._bom_map[hw]['primary']['components'].keys())
    for var in self._variant_map:
      classes_set.update(self._variant_map[var]['components'].keys())
    for vol in self._volatile_map:
      classes_set.update(self._volatile_map[vol].keys())
    classes_set.update(self._volatile_value_map.keys())
    return classes_set

  def GetComponents(self, board, with_classes=None):
    """Get a filtered dict of all components for the given board.

    Overrides superclass method.

    Args:
      board: The board that you want the components of.
      with_classes: Filter for component classes that the dict include.

    Returns:
      A dict of components.

    Raises:
      BoardMismatchError: If the board is invalid.
    """
    board_string = _NormalizeString(board)

    if board_string != self.board:
      raise BoardMismatchError(board, board_string)

    components = {}
    all_comps = list()
    for bom in self._bom_map.values():
      if bom['primary']['components']:
        all_comps.extend(bom['primary']['components'].items())
    for var in self._variant_map.values():
      if var['components']:
        all_comps.extend(var['components'].items())
    for vol in self._volatile_map.values():
      if vol:
        for cls, comp in vol.items():
          all_comps.append((cls, comp))
          all_comps.append((comp, self._volatile_value_map[comp]))

    for cls, comp in all_comps:
      if with_classes and cls not in with_classes:
        continue
      if cls not in components:
        components[cls] = set()
      if isinstance(comp, list):
        components[cls].update(comp)
      else:
        components[cls].add(comp)

    return components


class _HwidV3Data(_HwidData):
  """Wrapper for HWIDv3 data."""

  def __init__(self, board, hwid_file=None, raw_hwid_yaml=None, hwid_data=None):
    """Constructor.

    Requires one of hwid_file, hwid_yaml or hwid_data.

    Args:
      board: The board name
      hwid_file: the path to a file containing the HWID data.
      raw_hwid_yaml: the raw YAML string of HWID data.
      hwid_data: parsed HWID data from a HWID file.
    """
    self.board = board
    self.database = None

    self._Seed(hwid_file, raw_hwid_yaml, hwid_data)

  def _SeedFromRawYaml(self, raw_hwid_yaml):
    """Seeds the object from a yaml string of hwid definitions."""
    return self._SeedFromData(raw_hwid_yaml)

  def _SeedFromData(self, hwid_data):
    self.database = database.Database.LoadData(
        hwid_data, expected_checksum=None)

  def GetBomAndConfigless(self, hwid_string, verbose=False,
                          waived_comp_categories=None):
    """Get the BOM and configless field for a given HWID.

    Overrides superclass method.

    Args:
      hwid_string: The HWID.
      verbose: Returns all fields in component detail if set to True.
      waived_comp_categories: List of waived component categories which means
      they are not verification-payload-related.

    Returns:
      A bom dict and configless field dict.
      If there is no configless field in given HWID, return Bom dict and None.

    Raises:
      HwidNotFoundError: If a portion of the HWID is not found or the HWID is
      invalid.  Note that the V3 library does not distinguish between the two.
    """

    try:
      hwid, _bom, configless = hwid_utils.DecodeHWID(
          self.database, _NormalizeString(hwid_string))
    except common.HWIDException as e:
      logging.info('Unable to decode a valid HWID. %s', hwid_string)
      raise HwidNotFoundError('HWID not found %s' % hwid_string, e)

    bom = Bom()

    bom.AddAllComponents(_bom.components, self.database, verbose=verbose,
                         waived_comp_categories=waived_comp_categories)
    bom.phase = self.database.GetImageName(hwid.image_id)
    bom.board = hwid.project

    return bom, configless

  def GetHwids(self,
               board,
               with_classes=None,
               without_classes=None,
               with_components=None,
               without_components=None):
    """Get a filtered set of HWIDs for the given board.

    Overrides superclass method.

    Args:
      board: The board that you want the HWIDs of.
      with_classes: Filter for component classes that the HWIDs include.
      without_classes: Filter for component classes that the HWIDs don't
        include.
      with_components: Filter for components that the HWIDs include.
      without_components: Filter for components that the HWIDs don't include.

    Returns:
      A set of HWIDs.

    Raises:
      BoardMismatchError: If the board is invalid.
    """
    raise NotImplementedError('This method is not supported for v3')

  def GetComponentClasses(self, board):
    """Get a set of all component classes for the given board.

    This function is supported, but has not yet been implemented.

    Overrides superclass method.

    Args:
      board: The board that you want the component classes of.

    Returns:
      A set of component classes.

    Raises:
      BoardMismatchError: If the board is invalid.
    """
    raise NotImplementedError('This method is not implemented for v3')

  def GetComponents(self, board, with_classes=None):
    """Get a filtered dict of all components for the given board.

    This function is supported, but has not yet been implemented.

    Overrides superclass method.

    Args:
      board: The board that you want the components of.
      with_classes: Filter for component classes that the dict include.

    Returns:
      A dict of components.

    Raises:
      BoardMismatchError: If the board is invalid.
    """
    raise NotImplementedError('This method is not implemented for v3')


def _NormalizeString(string):
  """Normalizes a string to account for things like case."""
  return string.strip().upper() if string else None


def _VerifyBoardMetadata(board_metadata):
  for metadata in board_metadata.values():
    for field in ['board', 'path', 'version']:
      if field not in metadata:
        raise MetadataError(
            'Board Metadata is missing required field %r.' % field)
