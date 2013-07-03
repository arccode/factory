# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.rf import lan_scpi
from cros.factory.rf.lan_scpi import Error


class AgilentSCPI(lan_scpi.LANSCPI):
  '''
  An Agilent device that supports SCPI.
  '''
  def __init__(self, expected_model, *args, **kwargs):
    super(AgilentSCPI, self).__init__(*args, **kwargs)
    self.id_fields = [x.strip() for x in self.id.split(',')]
    model = self.id_fields[1]
    if model != expected_model:
      raise Error('Expected model %s but got %s' % (
                  expected_model, model))

  def GetSerialNumber(self):
    '''Returns the serial number of the device.'''
    return self.id_fields[2]
