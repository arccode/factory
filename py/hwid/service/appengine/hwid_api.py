# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID Api definition.  Defines all the exposed API methods.

This file is also the place that all the binding is done for various components.
"""

import logging
import re
import urllib

# pylint: disable=import-error, no-name-in-module
import endpoints
from google.appengine.api import users
from protorpc import message_types
from protorpc import messages
from protorpc import remote

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import goldeneye_ingestion
from cros.factory.hwid.service.appengine import hwid_api_messages
from cros.factory.hwid.service.appengine import hwid_updater
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.service.appengine import hwid_validator
from cros.factory.hwid.service.appengine import memcache_adaptor


@endpoints.api(
    name='chromeoshwid',
    version='v1',
    description='Chrome OS Hardware ID API',
    hostname='localhost:8080',  # To make the API explorer work
    audiences=[endpoints.API_EXPLORER_CLIENT_ID])
class HwidApi(remote.Service):
  """Class that has all the exposed HWID API methods.

  IMPORTANT NOTE: Every method in this class that is exposed as part of the API
  should call self._auth_check() before doing anything else to ensure that the
  API user is in fact allowed to access the API (also see comment below).
  """

  APIARY_USER_LIST = ['apiserving@google.com', 'apiserving@prod.google.com']
  KNOWN_BAD_HWIDS = ['DUMMY_HWID', 'dummy_hwid']
  KNOWN_BAD_SUBSTR = [
      '.*TEST.*', '.*CHEETS.*', '^SAMS .*', '.* DEV$', '.*DOGFOOD.*'
  ]

  def __init__(self):
    self._hwid_manager = CONFIG.hwid_manager
    self._hwid_validator = hwid_validator.HwidValidator()
    self._hwid_updater = hwid_updater.HwidUpdater()
    self._goldeneye_memcache_adaptor = memcache_adaptor.MemcacheAdaptor(
        namespace=goldeneye_ingestion.MEMCACHE_NAMESPACE)

  def _AuthCheck(self):
    """Ensures that the user is able to access the API.

    This is should be called to ensure that our app can only be accessed via
    www.googleapis.com/..., and not chromeoshwid.googleplex.com/_ah/api/...
    The latter does not enforce any frontend quota and will therefore allow
    unregistered users (even external ones!) to access the app. We need to stop
    them.

    In app.yaml we have disabled the /_ah/api endpoint using a hack. If this
    hack ever stops working in the future, this code is the second line of
    defense. Note that discovery information would be exposed in that case, this
    method only covers access to the API methods.

    Full discussion: https://goo.gl/PgEhUz
    """

    # Be extra paranoid and only allow skip auth if skip_auth_check is set to
    # True (as opposed to truthy).
    if CONFIG.skip_auth_check == True:
      logging.info('Skipping auth check (this should only happen in dev mode).')
      return

    # Users that access our API via www.googleapis.com will show up here as
    # 'apiserving@google.com', so this is what we use to distinguish legitimate
    # and not legitimate access.
    current_user = users.get_current_user()
    logging.debug('Current user: %r', current_user)
    if ((current_user is None) or
        (current_user.email() not in HwidApi.APIARY_USER_LIST)):
      raise endpoints.UnauthorizedException('Not authorized')

  def _FastFailKnownBadHwid(self, hwid):
    if hwid in HwidApi.KNOWN_BAD_HWIDS:
      return 'No metadata present for the requested board: %s' % hwid

    for regexp in HwidApi.KNOWN_BAD_SUBSTR:
      if re.search(regexp, hwid):
        return 'No metadata present for the requested board: %s' % hwid

  @endpoints.method(
      hwid_api_messages.BoardsRequest,
      hwid_api_messages.BoardsResponse,
      path='boards',
      http_method='GET',
      name='boards')
  def GetBoards(self, request):
    """Return all of the supported boards."""
    self._AuthCheck()

    versions = set(request.versions)
    boards = self._hwid_manager.GetBoards(versions)

    logging.debug('Found boards: %r', boards)

    return hwid_api_messages.BoardsResponse(boards=list(boards))

  def _GetBom(self, raw_hwid):
    try:
      hwid = urllib.unquote(raw_hwid)
      bom = self._hwid_manager.GetBom(hwid)

      if bom is None:
        raise endpoints.NotFoundException('HWID not found.')
    except KeyError as e:
      logging.exception('KeyError -> not found')
      return None, str(e)
    except ValueError as e:
      logging.exception('ValueError -> bad input')
      return None, str(e)

    return bom, None

  GET_BOM_REQUEST = endpoints.ResourceContainer(
      message_types.VoidMessage, hwid=messages.StringField(1, required=True))

  @endpoints.method(
      GET_BOM_REQUEST,
      hwid_api_messages.BomResponse,
      path='bom/{hwid}',
      http_method='GET',
      name='bom')
  def GetBom(self, request):
    """Return the components of the BOM identified by the HWID."""
    self._AuthCheck()

    error = self._FastFailKnownBadHwid(request.hwid)
    if error:
      return hwid_api_messages.BomResponse(error=error)

    logging.debug('Retrieving HWID %s', request.hwid)
    bom, error = self._GetBom(request.hwid)
    if error:
      return hwid_api_messages.BomResponse(error=error)

    components = list()
    for component in bom.GetComponents():
      c = hwid_api_messages.Component(
          name=component.name, componentClass=component.cls)
      components.append(c)

    labels = list()
    for label in bom.GetLabels():
      l = hwid_api_messages.Label(
          name=label.name, componentClass=label.cls, value=label.value)
      labels.append(l)

    phase = bom.phase

    return hwid_api_messages.BomResponse(
        components=components, labels=labels, phase=phase)

  GET_SKU_REQUEST = endpoints.ResourceContainer(
      message_types.VoidMessage, hwid=messages.StringField(1, required=True))

  @endpoints.method(
      GET_SKU_REQUEST,
      hwid_api_messages.SKUResponse,
      path='sku/{hwid}',
      http_method='GET',
      name='sku')
  def GetSKU(self, request):
    """Return the components of the SKU identified by the HWID."""
    self._AuthCheck()
    error = self._FastFailKnownBadHwid(request.hwid)
    if error:
      return hwid_api_messages.SKUResponse(error=error)

    bom, error = self._GetBom(request.hwid)
    if error:
      return hwid_api_messages.SKUResponse(error=error)

    try:
      sku = hwid_util.GetSkuFromBom(bom)
    except hwid_util.HWIDUtilException as e:
      return hwid_api_messages.SKUResponse(error=str(e))

    return hwid_api_messages.SKUResponse(
        board=sku['board'],
        cpu=sku['cpu'],
        memoryInBytes=sku['total_bytes'],
        memory=sku['memory_str'],
        sku=sku['sku'])

  # A request for all HWIDs for a board with the specified criteria.
  #
  # Fields:
  #   board: The board that we want the HWIDs of.
  #   withClasses: Filter for component classes that the HWIDs include.
  #   withoutClasses: Filter for component classes that the HWIDs don't include.
  #   withComponents: Filter for components that the HWIDs include.
  #   withoutComponents: Filter for components that the HWIDs don't include.
  GET_HWIDS_REQUEST = endpoints.ResourceContainer(
      message_types.VoidMessage,
      board=messages.StringField(1, required=True),
      withClasses=messages.StringField(2, repeated=True),
      withoutClasses=messages.StringField(3, repeated=True),
      withComponents=messages.StringField(4, repeated=True),
      withoutComponents=messages.StringField(5, repeated=True))

  @endpoints.method(
      GET_HWIDS_REQUEST,
      hwid_api_messages.HwidsResponse,
      path='hwids/{board}',
      http_method='GET',
      name='hwids')
  def GetHwids(self, request):
    """Return a filtered list of HWIDs for the given board."""
    self._AuthCheck()

    board = urllib.unquote(request.board)

    def IsNotNoneOrEmpty(x):
      return x and len(x)

    with_classes = set(filter(IsNotNoneOrEmpty, request.withClasses))
    without_classes = set(filter(IsNotNoneOrEmpty, request.withoutClasses))
    with_components = set(filter(IsNotNoneOrEmpty, request.withComponents))
    without_components = set(
        filter(IsNotNoneOrEmpty, request.withoutComponents))

    if (with_classes and without_classes and
        with_classes.intersection(without_classes)):
      raise endpoints.BadRequestException('One or more component classes '
                                          'specified for both with and '
                                          'without')

    if (with_components and without_components and
        with_components.intersection(without_components)):
      raise endpoints.BadRequestException('One or more components specified '
                                          'for both with and without')

    try:
      hwids = self._hwid_manager.GetHwids(board, with_classes, without_classes,
                                          with_components, without_components)
    except ValueError:
      logging.exception('ValueError -> bad input')
      raise endpoints.BadRequestException('Invalid input: %s' % board)

    logging.debug('Found HWIDs: %r', hwids)

    return hwid_api_messages.HwidsResponse(hwids=hwids)

  GET_COMPONENT_CLASSES_REQUEST = endpoints.ResourceContainer(
      message_types.VoidMessage, board=messages.StringField(1, required=True))

  @endpoints.method(
      GET_COMPONENT_CLASSES_REQUEST,
      hwid_api_messages.ComponentClassesResponse,
      path='classes/{board}',
      http_method='GET',
      name='classes')
  def GetComponentClasses(self, request):
    """Return a list of all component classes for the given board."""
    self._AuthCheck()

    try:
      board = urllib.unquote(request.board)
      classes = self._hwid_manager.GetComponentClasses(board)
    except ValueError:
      logging.exception('ValueError -> bad input')
      raise endpoints.BadRequestException('Invalid input: %s' % board)

    logging.debug('Found component classes: %r', classes)

    return hwid_api_messages.ComponentClassesResponse(componentClasses=classes)

  # A request for all components for a board with the specified criteria.
  #
  # Fields:
  # board: The board that we want the components of.
  # withClasses: Filter for components of the specified component classes.

  GET_COMPONENTS_REQUEST = endpoints.ResourceContainer(
      message_types.VoidMessage,
      board=messages.StringField(1, required=True),
      withClasses=messages.StringField(2, repeated=True))

  @endpoints.method(
      GET_COMPONENTS_REQUEST,
      hwid_api_messages.ComponentsResponse,
      path='components/{board}',
      http_method='GET',
      name='components')
  def GetComponents(self, request):
    """Return a filtered list of components for the given board."""
    self._AuthCheck()

    try:
      board = urllib.unquote(request.board)
      with_classes = set(request.withClasses)
      components = self._hwid_manager.GetComponents(board, with_classes)
    except ValueError:
      logging.exception('ValueError -> bad input')
      raise endpoints.BadRequestException('Invalid input: %s' % board)

    logging.debug('Found component classes: %r', components)

    components_list = list()
    for cls, comps in components.items():
      for comp in comps:
        components_list.append(
            hwid_api_messages.Component(componentClass=cls, name=comp))

    return hwid_api_messages.ComponentsResponse(components=components_list)

  @endpoints.method(
      hwid_api_messages.ValidateConfigRequest,
      hwid_api_messages.ValidateConfigResponse,
      path='validateConfig',
      http_method='POST',
      name='validateConfig')
  def ValidateConfig(self, request):
    """Validate the config.

    Args:
      request: a ValidateConfigRequest.

    Returns:
      A ValidateConfigAndUpdateResponse containing an error message if an error
      occurred.
    """
    self._AuthCheck()

    try:
      self._hwid_validator.Validate(request.hwidConfigContents)
    except hwid_validator.ValidationError as e:
      logging.exception('ValidationError: %r', e.message)
      return hwid_api_messages.ValidateConfigResponse(errorMessage=e.message)

    return hwid_api_messages.ValidateConfigResponse()

  @endpoints.method(
      hwid_api_messages.ValidateConfigAndUpdateChecksumRequest,
      hwid_api_messages.ValidateConfigAndUpdateChecksumResponse,
      path='validateConfigAndUpdateChecksum',
      http_method='POST',
      name='validateConfigAndUpdateChecksum')
  def ValidateConfigAndUpdateChecksum(self, request):
    """Validate the config and update its checksum.

    Args:
      request: a ValidateConfigAndUpdateChecksumRequest.

    Returns:
      A ValidateConfigAndUpdateChecksumResponse containing either the updated
      config or an error message.
    """
    self._AuthCheck()

    updated_contents = self._hwid_updater.UpdateChecksum(
        request.hwidConfigContents)

    try:
      self._hwid_validator.ValidateChange(updated_contents,
                                          request.prevHwidConfigContents)
    except hwid_validator.ValidationError as e:
      logging.exception('ValidationError: %r', e.message)
      return hwid_api_messages.ValidateConfigAndUpdateChecksumResponse(
          errorMessage=e.message)

    return hwid_api_messages.ValidateConfigAndUpdateChecksumResponse(
        newHwidConfigContents=updated_contents)

  GET_DUTLABEL_REQUEST = endpoints.ResourceContainer(
      message_types.VoidMessage, hwid=messages.StringField(1, required=True))

  @endpoints.method(
      GET_DUTLABEL_REQUEST,
      hwid_api_messages.DUTLabelResponse,
      path='dutlabel/{hwid}',
      http_method='GET',
      name='dutlabel')
  def GetDUTLabels(self, request):
    """Return the components of the SKU identified by the HWID."""
    self._AuthCheck()

    labels = []
    # If you add any labels to the list of returned labels, also add to
    # the list of possible labels
    possible_labels = [
        'sku', 'phase', 'touchscreen', 'touchpad', 'variant', 'stylus'
    ]

    error = self._FastFailKnownBadHwid(request.hwid)
    if error:
      return hwid_api_messages.DUTLabelResponse(
          error=error, possible_labels=possible_labels)

    bom, error = self._GetBom(request.hwid)

    if error:
      return hwid_api_messages.DUTLabelResponse(
          error=error, possible_labels=possible_labels)

    try:
      sku = hwid_util.GetSkuFromBom(bom)
    except hwid_util.HWIDUtilException as e:
      return hwid_api_messages.DUTLabelResponse(
          error=str(e), possible_labels=possible_labels)

    labels.append(hwid_api_messages.DUTLabel(name='sku', value=sku['sku']))

    regexp_to_device = self._goldeneye_memcache_adaptor.Get('regexp_to_device')

    if not regexp_to_device:
      # TODO(haddowk) Kick off the ingestion to ensure that the memcache is
      # up to date.
      return hwid_api_messages.DUTLabelResponse(
          error='Missing Regexp List', possible_labels=possible_labels)
    for (regexp, device, unused_regexp_to_board) in regexp_to_device:
      del unused_regexp_to_board  # unused
      if re.match(regexp, request.hwid):
        labels.append(hwid_api_messages.DUTLabel(name='variant', value=device))
    if bom.phase:
      labels.append(hwid_api_messages.DUTLabel(name='phase', value=bom.phase))

    components = ['touchscreen', 'touchpad', 'stylus']
    for component in components:
      component_value = hwid_util.GetComponentValueFromBom(bom, component)
      if component_value and component_value[0]:
        # The lab just want the existance of a component they do not care
        # what type it is.
        labels.append(hwid_api_messages.DUTLabel(name=component, value=None))

    if set([label.name for label in labels]) - set(possible_labels):
      return hwid_api_messages.DUTLabelResponse(
          error='Possible labels is out of date',
          possible_labels=possible_labels)

    return hwid_api_messages.DUTLabelResponse(
        labels=labels, possible_labels=possible_labels)
