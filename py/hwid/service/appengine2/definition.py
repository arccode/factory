# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=import-error

"""Definitions of the protorpc request and response for HWID Service Proxy

The file should be aligned with the protobuf definition at go/hwidservice_proto.
"""

from protorpc.messages import Enum
from protorpc.messages import EnumField
from protorpc.messages import Message
from protorpc.messages import StringField

# pylint: disable=no-init
class ErrorCode(Enum):
  UNKNOWN_ERROR = 0
  NO_ERROR = 1
  VALIDATION_ERROR = 2


# pylint: disable=no-init
class ValidateConfigRequest(Message):
  hwid = StringField(1, required=False)


class ValidateConfigResponse(Message):
  err_code = EnumField(ErrorCode, 1, required=False)
  err_msg = StringField(2, required=False)


class ValidateConfigAndUpdateChecksumResquest(Message):
  new_hwid = StringField(1, required=False)
  old_hwid = StringField(2, required=False)


class ValidateConfigAndUpdateChecksumResponse(Message):
  err_code = EnumField(ErrorCode, 1, required=False)
  err_msg = StringField(2, required=False)
  hwid = StringField(3, required=False)
