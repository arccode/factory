# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common variables and functions declartion used by ServiceManager and
HWIDService.

This file should not import cros.factory modules, because the file will be
copied into Docker environment.
ServiceManager is a standalone program running in docker environment that have
no factory python modules dependency and HWIDService is running in the normal
factory environment. It is used to share the Request and Response data
structures between ServiceManager and HWIDService.
To share the data structure Reqeust and Response and to decouple the dependency
from the module import paths that socket uses, we use dictonary object to pass
the information.
"""

import time
import uuid


class Command(object):
  """Placeholder class for commands"""
  TERMINATE = 'Terminate'


def CreateRequest(command):
  return {
      'uuid': uuid.uuid4(),
      'timestamp': time.time(),
      'command': command,
  }


def CreateResponse(request, success, msg):
  return {
      'uuid': request['uuid'],
      'timestamp': time.time(),
      'command': request['command'],
      'success': success,
      'message': msg
  }
