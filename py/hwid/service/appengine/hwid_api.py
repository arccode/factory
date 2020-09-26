# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID Api definition.  Defines all the exposed API methods.

This file is also the place that all the binding is done for various components.
"""

import functools
import gzip
import logging
import operator
import re

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import flask
import flask.views
import yaml
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.chromeoshwid import update_checksum
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import goldeneye_ingestion
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.service.appengine import hwid_validator
from cros.factory.hwid.service.appengine import memcache_adapter
from cros.factory.hwid.v3.rule import Value
from cros.factory.hwid.v3 import validator as v3_validator
# pylint: disable=import-error, no-name-in-module
from cros.factory.hwid.service.appengine.proto import hwid_api_messages_pb2
# pylint: enable=import-error, no-name-in-module
from cros.factory.probe_info_service.app_engine import protorpc_utils
from cros.factory.utils import schema


KNOWN_BAD_HWIDS = ['DUMMY_HWID', 'dummy_hwid']
KNOWN_BAD_SUBSTR = [
    '.*TEST.*', '.*CHEETS.*', '^SAMS .*', '.* DEV$', '.*DOGFOOD.*'
]

_hwid_manager = CONFIG.hwid_manager
_hwid_validator = hwid_validator.HwidValidator()
_goldeneye_memcache_adapter = memcache_adapter.MemcacheAdapter(
    namespace=goldeneye_ingestion.MEMCACHE_NAMESPACE)


def _FastFailKnownBadHwid(hwid):
  if hwid in KNOWN_BAD_HWIDS:
    return (hwid_api_messages_pb2.Status.KNOWN_BAD_HWID,
            'No metadata present for the requested board: %s' % hwid)

  for regexp in KNOWN_BAD_SUBSTR:
    if re.search(regexp, hwid):
      return (hwid_api_messages_pb2.Status.KNOWN_BAD_HWID,
              'No metadata present for the requested board: %s' % hwid)
  return (hwid_api_messages_pb2.Status.SUCCESS, '')


def _GetBomAndConfigless(hwid, verbose=False):
  try:
    bom, configless = _hwid_manager.GetBomAndConfigless(hwid, verbose)

    if bom is None:
      return (None, None, hwid_api_messages_pb2.Status.NOT_FOUND,
              'HWID not found.')
  except KeyError as e:
    logging.exception('KeyError -> not found')
    return None, None, hwid_api_messages_pb2.Status.NOT_FOUND, str(e)
  except ValueError as e:
    logging.exception('ValueError -> bad input')
    return None, None, hwid_api_messages_pb2.Status.BAD_REQUEST, str(e)

  return bom, configless, hwid_api_messages_pb2.Status.SUCCESS, None


def _HandleGzipRequests(method):
  @functools.wraps(method)
  def _MethodWrapper(*args, **kwargs):
    if flask.request.content_encoding == 'gzip':
      flask.request.stream = gzip.GzipFile(fileobj=flask.request.stream)
    return method(*args, **kwargs)

  return _MethodWrapper


def _MapException(ex, cls):
  if isinstance(ex.__context__, schema.SchemaException):
    return cls(
        errorMessage=str(ex), status=hwid_api_messages_pb2.Status.SCHEMA_ERROR)
  if isinstance(ex.__context__, yaml.error.YAMLError):
    return cls(
        errorMessage=str(ex), status=hwid_api_messages_pb2.Status.YAML_ERROR)
  if isinstance(ex.__context__, yaml.error.YAMLError):
    return cls(
        errorMessage=str(ex), status=hwid_api_messages_pb2.Status.YAML_ERROR)
  return cls(
      errorMessage=str(ex), status=hwid_api_messages_pb2.Status.BAD_REQUEST)


class ProtoRPCService(protorpc_utils.ProtoRPCServiceBase):
  SERVICE_DESCRIPTOR = hwid_api_messages_pb2.DESCRIPTOR.services_by_name[
      'HwidService']

  @protorpc_utils.ProtoRPCServiceMethod
  def GetBoards(self, request):
    """Return all of the supported boards in sorted order."""

    versions = request.versions
    boards = _hwid_manager.GetBoards(versions)

    logging.debug('Found boards: %r', boards)
    response = hwid_api_messages_pb2.BoardsResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS, boards=sorted(boards))

    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def GetBom(self, request):
    """Return the components of the BOM identified by the HWID."""
    verbose = request.verbose
    hwid = request.hwid

    status, error = _FastFailKnownBadHwid(hwid)
    if status != hwid_api_messages_pb2.Status.SUCCESS:
      return hwid_api_messages_pb2.BomResponse(error=error, status=status)

    logging.debug('Retrieving HWID %s', hwid)
    bom, unused_configless, status, error = _GetBomAndConfigless(hwid, verbose)
    if status != hwid_api_messages_pb2.Status.SUCCESS:
      return hwid_api_messages_pb2.BomResponse(error=error, status=status)

    response = hwid_api_messages_pb2.BomResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS)
    response.phase = bom.phase

    for component in bom.GetComponents():
      name = _hwid_manager.GetAVLName(component.cls, component.name)
      fields = []
      if verbose:
        for fname, fvalue in component.fields.items():
          field = hwid_api_messages_pb2.Field()
          field.name = fname
          if isinstance(fvalue, Value):
            if fvalue.is_re:
              field.value = '!re ' + fvalue.raw_value
            else:
              field.value = fvalue.raw_value
          else:
            field.value = str(fvalue)
          fields.append(field)

      fields.sort(key=lambda field: field.name)
      response.components.add(componentClass=component.cls, name=name,
                              fields=fields)

    response.components.sort(key=operator.attrgetter('componentClass', 'name'))

    for label in bom.GetLabels():
      response.labels.add(componentClass=label.cls, name=label.name,
                          value=label.value)
    response.labels.sort(key=operator.attrgetter('name', 'value'))

    return response

  @protorpc_utils.ProtoRPCServiceMethod
  def GetSku(self, request):
    """Return the components of the SKU identified by the HWID."""
    status, error = _FastFailKnownBadHwid(request.hwid)
    if status != hwid_api_messages_pb2.Status.SUCCESS:
      return hwid_api_messages_pb2.SkuResponse(error=error, status=status)

    bom, configless, status, error = _GetBomAndConfigless(request.hwid)
    if status != hwid_api_messages_pb2.Status.SUCCESS:
      return hwid_api_messages_pb2.SkuResponse(error=error, status=status)

    try:
      sku = hwid_util.GetSkuFromBom(bom, configless)
    except hwid_util.HWIDUtilException as e:
      return hwid_api_messages_pb2.SkuResponse(
          error=str(e), status=hwid_api_messages_pb2.Status.BAD_REQUEST)

    return hwid_api_messages_pb2.SkuResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS, board=sku['board'],
        cpu=sku['cpu'], memoryInBytes=sku['total_bytes'],
        memory=sku['memory_str'], sku=sku['sku'])

  @protorpc_utils.ProtoRPCServiceMethod
  def GetHwids(self, request):
    """Return a filtered list of HWIDs for the given board."""

    board = request.board

    with_classes = set(filter(None, request.withClasses))
    without_classes = set(filter(None, request.withoutClasses))
    with_components = set(filter(None, request.withComponents))
    without_components = set(filter(None, request.withoutComponents))

    if (with_classes and without_classes and
        with_classes.intersection(without_classes)):
      return hwid_api_messages_pb2.HwidsResponse(
          status=hwid_api_messages_pb2.Status.BAD_REQUEST,
          error=('One or more component classes specified for both with and '
                 'without'))

    if (with_components and without_components and
        with_components.intersection(without_components)):
      return hwid_api_messages_pb2.HwidsResponse(
          status=hwid_api_messages_pb2.Status.BAD_REQUEST,
          error='One or more components specified for both with and without')

    try:
      hwids = _hwid_manager.GetHwids(board, with_classes, without_classes,
                                     with_components, without_components)
    except ValueError:
      logging.exception('ValueError -> bad input')
      return hwid_api_messages_pb2.HwidsResponse(
          status=hwid_api_messages_pb2.Status.BAD_REQUEST,
          error='Invalid input: %s' % board)

    logging.debug('Found HWIDs: %r', hwids)

    return hwid_api_messages_pb2.HwidsResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS, hwids=hwids)

  @protorpc_utils.ProtoRPCServiceMethod
  def GetComponentClasses(self, request):
    """Return a list of all component classes for the given board."""

    try:
      board = request.board
      classes = _hwid_manager.GetComponentClasses(board)
    except ValueError:
      logging.exception('ValueError -> bad input')
      return hwid_api_messages_pb2.ComponentClassesResponse(
          status=hwid_api_messages_pb2.Status.BAD_REQUEST,
          error='Invalid input: %s' % board)

    logging.debug('Found component classes: %r', classes)

    return hwid_api_messages_pb2.ComponentClassesResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS, componentClasses=classes)

  @protorpc_utils.ProtoRPCServiceMethod
  def GetComponents(self, request):
    """Return a filtered list of components for the given board."""

    board = request.board
    with_classes = set(filter(None, request.withClasses))

    try:
      components = _hwid_manager.GetComponents(board, with_classes)
    except ValueError:
      logging.exception('ValueError -> bad input')
      return hwid_api_messages_pb2.ComponentsResponse(
          status=hwid_api_messages_pb2.Status.BAD_REQUEST,
          error='Invalid input: %s' % board)

    logging.debug('Found component classes: %r', components)

    components_list = list()
    for cls, comps in components.items():
      for comp in comps:
        components_list.append(
            hwid_api_messages_pb2.Component(componentClass=cls, name=comp))

    return hwid_api_messages_pb2.ComponentsResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS, components=components_list)

  @protorpc_utils.ProtoRPCServiceMethod
  def ValidateConfig(self, request):
    """Validate the config.

    Args:
      request: a ValidateConfigRequest.

    Returns:
      A ValidateConfigAndUpdateResponse containing an error message if an error
      occurred.
    """
    hwidConfigContents = request.hwidConfigContents

    try:
      _hwid_validator.Validate(hwidConfigContents)
    except v3_validator.ValidationError as e:
      logging.exception('Validation failed')
      return _MapException(e, hwid_api_messages_pb2.ValidateConfigResponse)

    return hwid_api_messages_pb2.ValidateConfigResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS)

  @protorpc_utils.ProtoRPCServiceMethod
  def ValidateConfigAndUpdateChecksum(self, request):
    """Validate the config and update its checksum.

    Args:
      request: a ValidateConfigAndUpdateChecksumRequest.

    Returns:
      A ValidateConfigAndUpdateChecksumResponse containing either the updated
      config or an error message.
    """

    hwidConfigContents = request.hwidConfigContents
    prevHwidConfigContents = request.prevHwidConfigContents

    updated_contents = update_checksum.ReplaceChecksum(hwidConfigContents)

    try:
      _hwid_validator.ValidateChange(updated_contents, prevHwidConfigContents)
    except v3_validator.ValidationError as e:
      logging.exception('Validation failed')
      return _MapException(
          e, hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse)

    return hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS,
        newHwidConfigContents=updated_contents)

  @protorpc_utils.ProtoRPCServiceMethod
  def GetDutLabels(self, request):
    """Return the components of the SKU identified by the HWID."""
    hwid = request.hwid

    # If you add any labels to the list of returned labels, also add to
    # the list of possible labels.
    possible_labels = [
        'hwid_component',
        'phase',
        'sku',
        'stylus',
        'touchpad',
        'touchscreen',
        'variant',
    ]

    status, error = _FastFailKnownBadHwid(hwid)
    if status != hwid_api_messages_pb2.Status.SUCCESS:
      return hwid_api_messages_pb2.DutLabelsResponse(
          error=error, possible_labels=possible_labels, status=status)

    bom, configless, status, error = _GetBomAndConfigless(hwid)

    if status != hwid_api_messages_pb2.Status.SUCCESS:
      return hwid_api_messages_pb2.DutLabelsResponse(
          status=status, error=error, possible_labels=possible_labels)

    try:
      sku = hwid_util.GetSkuFromBom(bom, configless)
    except hwid_util.HWIDUtilException as e:
      return hwid_api_messages_pb2.DutLabelsResponse(
          status=hwid_api_messages_pb2.Status.BAD_REQUEST, error=str(e),
          possible_labels=possible_labels)

    response = hwid_api_messages_pb2.DutLabelsResponse(
        status=hwid_api_messages_pb2.Status.SUCCESS)
    response.labels.add(name='sku', value=sku['sku'])

    regexp_to_device = _goldeneye_memcache_adapter.Get('regexp_to_device')

    if not regexp_to_device:
      # TODO(haddowk) Kick off the ingestion to ensure that the memcache is
      # up to date.
      return hwid_api_messages_pb2.DutLabelsResponse(
          error='Missing Regexp List', possible_labels=possible_labels,
          status=hwid_api_messages_pb2.Status.SERVER_ERROR)
    for (regexp, device, unused_regexp_to_board) in regexp_to_device:
      del unused_regexp_to_board  # unused
      try:
        if re.match(regexp, hwid):
          response.labels.add(name='variant', value=device)
      except re.error:
        logging.exception('invalid regex pattern: %r', regexp)
    if bom.phase:
      response.labels.add(name='phase', value=bom.phase)

    components = ['touchscreen', 'touchpad', 'stylus']
    for component in components:
      # The lab just want the existence of a component they do not care
      # what type it is.
      if configless and 'has_' + component in configless['feature_list']:
        if configless['feature_list']['has_' + component]:
          response.labels.add(name=component, value=None)
      else:
        component_value = hwid_util.GetComponentValueFromBom(bom, component)
        if component_value and component_value[0]:
          response.labels.add(name=component, value=None)

    # cros labels in host_info store, which will be used in tast tests of
    # runtime probe
    for component in bom.GetComponents():
      if component.name and component.is_vp_related:
        name = _hwid_manager.GetAVLName(component.cls, component.name)
        if component.information is not None:
          name = component.information.get('comp_group', name)
        response.labels.add(name="hwid_component",
                            value=component.cls + '/' + name)

    unexpected_labels = set(
        label.name for label in response.labels) - set(possible_labels)

    if unexpected_labels:
      logging.error('unexpected labels: %r', unexpected_labels)
      return hwid_api_messages_pb2.DutLabelsResponse(
          error='Possible labels are out of date',
          possible_labels=possible_labels,
          status=hwid_api_messages_pb2.Status.SERVER_ERROR)

    response.labels.sort(key=operator.attrgetter('name', 'value'))
    response.possible_labels[:] = possible_labels
    return response
