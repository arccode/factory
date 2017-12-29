# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Messages used by the HWID API."""

from protorpc import messages  # pylint: disable=import-error


# pylint: disable=no-init
class Component(messages.Message):
  """A component of a BOM.

  Fields:
    componentClass: the type of component.
    name: the cannonical name
    probeResult: the probe result that results for this component.
  """
  componentClass = messages.StringField(1, required=False)
  name = messages.StringField(2, required=False)
  probeResult = messages.StringField(3)


class Label(messages.Message):
  """A label on a BOM.

  Fields:
    componentClass: the component-class this applies to, if any
    name: the label's name
    value: the label's value, possibly none.
  """
  componentClass = messages.StringField(1, required=False)
  name = messages.StringField(2, required=False)
  value = messages.StringField(3)


class BoardsRequest(messages.Message):
  """A request for all boards supported by the server.

  Fields:
    versions: List of BOM file versions to include.
  """
  versions = messages.StringField(1, repeated=True)


class ValidateConfigRequest(messages.Message):
  """A request to validate a config.

  Fields:
    hwidConfigContents: The HWID config as a string.
  """
  hwidConfigContents = messages.StringField(1, required=False)


class ValidateConfigAndUpdateChecksumRequest(messages.Message):
  """A request to validate a config and update its checksum.

  Fields:
    hwidConfigContents: The HWID config as a string.
    prevHwidConfigContents: The previous version of the HWID config (optional).
      If present, it will trigger some additional validation checks.
  """
  hwidConfigContents = messages.StringField(1, required=False)
  prevHwidConfigContents = messages.StringField(2)


class BoardsResponse(messages.Message):
  """The response to a boards request.

  Fields:
    boards: A list of the supported boards.
  """
  boards = messages.StringField(1, repeated=True)


class BomResponse(messages.Message):
  """The response to a BOM request.

  Fields:
    components: A list of the components in the BOM.
    labels: A list of labels of the BOM.
    phase: Build phase (corresponding to HWID image_id).
    error: Error message if there was a problem decoding the HWID, if error is
           set the other fields in the message should be disregarded.
  """
  components = messages.MessageField(Component, 1, repeated=True)
  labels = messages.MessageField(Label, 2, repeated=True)
  phase = messages.StringField(3)
  error = messages.StringField(4)


class HwidsResponse(messages.Message):
  """The response to a HWIDs request.

  Fields:
    hwids: A filtered list of the HWIDs for a board.
  """
  hwids = messages.StringField(1, repeated=True)


class ComponentClassesResponse(messages.Message):
  """The response to a component classes request.

  Fields:
    componentClasses: A list of the components for a board.
  """
  componentClasses = messages.StringField(1, repeated=True)


class ComponentsResponse(messages.Message):
  """The response to a components request.

  Fields:
    components: A filtered list of the components for a board.
  """
  components = messages.MessageField(Component, 1, repeated=True)


class ValidateConfigResponse(messages.Message):
  """The response to a 'validate config' request.

  Fields:
    errorMessage: If an error occurred, this describes the error.
  """
  errorMessage = messages.StringField(1)


class ValidateConfigAndUpdateChecksumResponse(messages.Message):
  """The response to a 'validate config and update checksum' request.

  Fields:
    newHwidConfigContents: The updated HWID config as a string.
    errorMessage: If an error occurred, this describes the error.
  """
  newHwidConfigContents = messages.StringField(1)
  errorMessage = messages.StringField(2)


class SKUResponse(messages.Message):
  """The response to a BOM request.

  Fields:
    board: The board listed in the BOM.
    cpu: The listed CPU in the BOM.
    memoryInBytes: Total number of bytes of memory in the BOM.
    sku: String combination of board, processor and memory.
    error: Error message if there was a problem decoding the HWID, if error is
           set the other fields in the message should be disregarded.
    memory: A human readable string representing the memory on the device.
  """
  board = messages.StringField(1)
  cpu = messages.StringField(2)
  memoryInBytes = messages.IntegerField(3)
  sku = messages.StringField(4)
  error = messages.StringField(5)
  memory = messages.StringField(6)


class DUTLabel(messages.Message):
  """A label of a DUT.

  Fields:
    name: the name of the label.
    value: the value of the property associated with this label name.

  """
  name = messages.StringField(1, required=False)
  value = messages.StringField(2, required=False)


class DUTLabelResponse(messages.Message):
  """The response to a DUT label request.

  Fields:
     labels: A list of DUTLabel messages.
     error: Details of any errors when constructing the list of labels.

  """
  labels = messages.MessageField(DUTLabel, 1, repeated=True)
  error = messages.StringField(2)
  possible_labels = messages.StringField(3, repeated=True)
