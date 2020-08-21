# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID Api definition.  Defines all the exposed API methods.

This file is also the place that all the binding is done for various components.
"""

import functools
import gzip
import http
import logging
import operator
import re
import urllib.parse

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import flask
import flask.views
from google.protobuf import json_format
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.chromeoshwid import update_checksum
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import goldeneye_ingestion
from cros.factory.hwid.service.appengine import hwid_util
from cros.factory.hwid.service.appengine import hwid_validator
from cros.factory.hwid.service.appengine import memcache_adapter
from cros.factory.hwid.v3.rule import Value
from cros.factory.hwid.v3 import validator as v3_validator
import hwid_api_messages_pb2  # pylint: disable=import-error


KNOWN_BAD_HWIDS = ['DUMMY_HWID', 'dummy_hwid']
KNOWN_BAD_SUBSTR = [
    '.*TEST.*', '.*CHEETS.*', '^SAMS .*', '.* DEV$', '.*DOGFOOD.*'
]

_hwid_manager = CONFIG.hwid_manager
_hwid_validator = hwid_validator.HwidValidator()
_goldeneye_memcache_adapter = memcache_adapter.MemcacheAdapter(
    namespace=goldeneye_ingestion.MEMCACHE_NAMESPACE)

bp = flask.Blueprint('hwid_api', __name__,
                     url_prefix='/api/chromeoshwid/v1')


class HwidApiException(Exception):
  def __init__(self, message, status_code):
    super(HwidApiException, self).__init__()
    self.message = message
    self.status_code = status_code

  def __str__(self):
    return '%s <Status: %d>' % (self.message, self.status_code)

  def FlaskResponse(self):
    return flask.Response(self.message, self.status_code)


class _NotFoundException(HwidApiException):
  def __init__(self, message):
    super(_NotFoundException, self).__init__(
        message, status_code=http.HTTPStatus.NOT_FOUND)


class _BadRequestException(HwidApiException):
  def __init__(self, message):
    super(_BadRequestException, self).__init__(
        message, status_code=http.HTTPStatus.BAD_REQUEST)


bp.register_error_handler(HwidApiException, operator.methodcaller(
    'FlaskResponse'))


def _FastFailKnownBadHwid(hwid):
  if hwid in KNOWN_BAD_HWIDS:
    return 'No metadata present for the requested board: %s' % hwid

  for regexp in KNOWN_BAD_SUBSTR:
    if re.search(regexp, hwid):
      return 'No metadata present for the requested board: %s' % hwid
  return ''


def _GetBomAndConfigless(raw_hwid, verbose=False):
  try:
    hwid = urllib.parse.unquote(raw_hwid)
    bom, configless = _hwid_manager.GetBomAndConfigless(hwid, verbose)

    if bom is None:
      raise _NotFoundException('HWID not found.')
  except KeyError as e:
    logging.exception('KeyError -> not found')
    return None, None, str(e)
  except ValueError as e:
    logging.exception('ValueError -> bad input')
    return None, None, str(e)

  return bom, configless, None


def _HandleGzipRequests(method):
  @functools.wraps(method)
  def _MethodWrapper(*args, **kwargs):
    if flask.request.content_encoding == 'gzip':
      flask.request.stream = gzip.GzipFile(fileobj=flask.request.stream)
    return method(*args, **kwargs)
  return _MethodWrapper


def HWIDAPI(*args, **kwargs):
  """ Decorator for HWID APIs"""
  def _DecorateMethod(method):
    @bp.route(*args, **kwargs)
    @_HandleGzipRequests
    @functools.wraps(method)
    def _MethodWrapper(*inner_args, **inner_kwargs):
      response = method(*inner_args, **inner_kwargs)
      logging.info("Response: \n%s", response)
      return flask.jsonify(json_format.MessageToDict(
          response, preserving_proto_field_name=True))
    return _MethodWrapper
  return _DecorateMethod


@HWIDAPI('/boards', methods=('GET',))
def GetBoards():
  """Return all of the supported boards in sorted order."""

  versions = set(
      flask.request.args.to_dict(flat=False).get('versions', [])) or None
  boards = _hwid_manager.GetBoards(versions)

  logging.debug('Found boards: %r', boards)
  response = hwid_api_messages_pb2.BoardsResponse(boards=sorted(boards))

  return response


@HWIDAPI('/bom/<hwid>', methods=('GET',))
def GetBom(hwid):
  """Return the components of the BOM identified by the HWID."""
  error = _FastFailKnownBadHwid(hwid)
  if error:
    return hwid_api_messages_pb2.BomResponse(error=error)

  verbose = ('verbose' in flask.request.args)

  logging.debug('Retrieving HWID %s', hwid)
  bom, unused_configless, error = _GetBomAndConfigless(hwid, verbose)
  if error:
    return hwid_api_messages_pb2.BomResponse(error=error)

  response = hwid_api_messages_pb2.BomResponse()
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


@HWIDAPI('/sku/<hwid>', methods=('GET',))
def GetSKU(hwid):
  """Return the components of the SKU identified by the HWID."""
  error = _FastFailKnownBadHwid(hwid)
  if error:
    return hwid_api_messages_pb2.SKUResponse(error=error)

  bom, configless, error = _GetBomAndConfigless(hwid)
  if error:
    return hwid_api_messages_pb2.SKUResponse(error=error)

  try:
    sku = hwid_util.GetSkuFromBom(bom, configless)
  except hwid_util.HWIDUtilException as e:
    return hwid_api_messages_pb2.SKUResponse(error=str(e))

  return hwid_api_messages_pb2.SKUResponse(
      board=sku['board'],
      cpu=sku['cpu'],
      memoryInBytes=sku['total_bytes'],
      memory=sku['memory_str'],
      sku=sku['sku'])


@HWIDAPI('/hwids/<board>', methods=('GET',))
def GetHwids(board):
  """Return a filtered list of HWIDs for the given board."""

  board = urllib.parse.unquote(board)

  args = flask.request.args.to_dict(flat=False)

  with_classes = set(filter(None, args.get('withClasses', [])))
  without_classes = set(filter(None, args.get('withoutClasses', [])))
  with_components = set(filter(None, args.get('withComponents', [])))
  without_components = set(filter(None, args.get('withoutComponents', [])))

  if (with_classes and without_classes and
      with_classes.intersection(without_classes)):
    raise _BadRequestException('One or more component classes '
                               'specified for both with and '
                               'without')

  if (with_components and without_components and
      with_components.intersection(without_components)):
    raise _BadRequestException('One or more components specified '
                               'for both with and without')

  try:
    hwids = _hwid_manager.GetHwids(board, with_classes, without_classes,
                                   with_components, without_components)
  except ValueError:
    logging.exception('ValueError -> bad input')
    raise _BadRequestException('Invalid input: %s' % board)

  logging.debug('Found HWIDs: %r', hwids)

  return hwid_api_messages_pb2.HwidsResponse(hwids=hwids)


@HWIDAPI('/classes/<board>', methods=('GET',))
def GetComponentClasses(board):
  """Return a list of all component classes for the given board."""

  try:
    board = urllib.parse.unquote(board)
    classes = _hwid_manager.GetComponentClasses(board)
  except ValueError:
    logging.exception('ValueError -> bad input')
    raise _BadRequestException('Invalid input: %s' % board)

  logging.debug('Found component classes: %r', classes)

  return hwid_api_messages_pb2.ComponentClassesResponse(
      componentClasses=classes)


@HWIDAPI('/components/<board>', methods=('GET',))
def GetComponents(board):
  """Return a filtered list of components for the given board."""

  args = flask.request.args.to_dict(flat=False)
  with_classes = set(args.get('withClasses', []))

  try:
    board = urllib.parse.unquote(board)
    components = _hwid_manager.GetComponents(board, with_classes)
  except ValueError:
    logging.exception('ValueError -> bad input')
    raise _BadRequestException('Invalid input: %s' % board)

  logging.debug('Found component classes: %r', components)

  components_list = list()
  for cls, comps in components.items():
    for comp in comps:
      components_list.append(
          hwid_api_messages_pb2.Component(componentClass=cls, name=comp))

  return hwid_api_messages_pb2.ComponentsResponse(components=components_list)


@HWIDAPI('/validateConfig', methods=('POST',))
def ValidateConfig():
  """Validate the config.

  Args:
    request: a ValidateConfigRequest.

  Returns:
    A ValidateConfigAndUpdateResponse containing an error message if an error
    occurred.
  """
  if flask.request.is_json:
    hwidConfigContents = flask.request.json.get('hwidConfigContents')
  else:
    hwidConfigContents = flask.request.values.get('hwidConfigContents')

  try:
    _hwid_validator.Validate(hwidConfigContents)
  except v3_validator.ValidationError as e:
    logging.exception('Validation failed')
    return hwid_api_messages_pb2.ValidateConfigResponse(errorMessage=str(e))

  return hwid_api_messages_pb2.ValidateConfigResponse()


@HWIDAPI('/validateConfigAndUpdateChecksum', methods=('POST',))
def ValidateConfigAndUpdateChecksum():
  """Validate the config and update its checksum.

  Args:
    request: a ValidateConfigAndUpdateChecksumRequest.

  Returns:
    A ValidateConfigAndUpdateChecksumResponse containing either the updated
    config or an error message.
  """

  if flask.request.is_json:
    hwidConfigContents = flask.request.json.get('hwidConfigContents')
    prevHwidConfigContents = flask.request.json.get('prevHwidConfigContents')
  else:
    hwidConfigContents = flask.request.values.get('hwidConfigContents')
    prevHwidConfigContents = flask.request.values.get('prevHwidConfigContents')

  updated_contents = update_checksum.ReplaceChecksum(hwidConfigContents)

  try:
    _hwid_validator.ValidateChange(updated_contents, prevHwidConfigContents)
  except v3_validator.ValidationError as e:
    logging.exception('Validation failed')
    return hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
        errorMessage=str(e))

  return hwid_api_messages_pb2.ValidateConfigAndUpdateChecksumResponse(
      newHwidConfigContents=updated_contents)


@HWIDAPI('/dutlabel/<hwid>', methods=('GET',))
def GetDUTLabels(hwid):
  """Return the components of the SKU identified by the HWID."""

  # If you add any labels to the list of returned labels, also add to
  # the list of possible labels
  possible_labels = [
      'hwid_component',
      'phase',
      'sku',
      'stylus',
      'touchpad',
      'touchscreen',
      'variant',
  ]

  error = _FastFailKnownBadHwid(hwid)
  if error:
    return hwid_api_messages_pb2.DUTLabelResponse(
        error=error, possible_labels=possible_labels)

  bom, configless, error = _GetBomAndConfigless(hwid)

  if error:
    return hwid_api_messages_pb2.DUTLabelResponse(
        error=error, possible_labels=possible_labels)

  try:
    sku = hwid_util.GetSkuFromBom(bom, configless)
  except hwid_util.HWIDUtilException as e:
    return hwid_api_messages_pb2.DUTLabelResponse(
        error=str(e), possible_labels=possible_labels)

  response = hwid_api_messages_pb2.DUTLabelResponse()
  response.labels.add(name='sku', value=sku['sku'])

  regexp_to_device = _goldeneye_memcache_adapter.Get('regexp_to_device')

  if not regexp_to_device:
    # TODO(haddowk) Kick off the ingestion to ensure that the memcache is
    # up to date.
    return hwid_api_messages_pb2.DUTLabelResponse(
        error='Missing Regexp List', possible_labels=possible_labels)
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
    # The lab just want the existance of a component they do not care
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
      response.labels.add(
          name="hwid_component",
          value=component.cls + '/' + name)

  unexpected_labels = set(
      label.name for label in response.labels) - set(possible_labels)

  if unexpected_labels:
    logging.error('unexpected labels: %r', unexpected_labels)
    return hwid_api_messages_pb2.DUTLabelResponse(
        error='Possible labels are out of date',
        possible_labels=possible_labels)

  response.labels.sort(key=operator.attrgetter('name', 'value'))
  response.possible_labels[:] = possible_labels
  return response
