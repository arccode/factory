# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.fixture.bft_fixture import BFTFixture


class DummyBFTFixture(BFTFixture):
  """A dummy class for BFT fixture.

  It is used when we want to verify a BFT test case without BFT fixture.
  For methods asking the fixture to do something, we place a timer for
  tester to act like the fixture.
  For methods getting status, like GetFixtureId, we returns a default value.
  """
  # For EngageDevice/DisengageDevice, it sleeps _delay_secs for user to mimic
  # fixture's action.
  _delay_secs = 3

  def Init(self, **kwargs):
    pass

  def Disconnect(self):
    pass

  def SetDeviceEngaged(self, device, engage):
    self._DisplayPrompt('Please %s device: %s' %
                        ('engage' if engage else 'disengage',
                         device))

  def Ping(self):
    pass

  def CheckPowerRail(self):
    pass

  def CheckExtDisplay(self):
    pass

  def GetFixtureId(self):
    return 1

  def ScanBarcode(self):
    self._DisplayPrompt('Please type a barcode.')

  def SimulateKeystrokes(self):
    self._DisplayPrompt('Please input keystoke sequence.')

  def IsLEDColor(self, unused_color):  # pylint: disable=W0613
    return True

  @property
  def delay_secs(self):
    return self._delay_secs

  @delay_secs.setter
  def delay_secs(self, delay_secs):
    self._delay_secs = delay_secs

  def _DisplayPrompt(self, prompt):
    """Asks user to do something to ack like a real fixture.

    It sleeps for _delay_secs for user to complete the action.

    Args:
      prompt: The prompt message.
    """
    factory.console.info(prompt)
    time.sleep(self._delay_secs)
