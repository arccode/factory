# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory test automator for 'audio_loop' test."""

import factory_common  # pylint: disable=W0611
from cros.factory.test.utils import audio_utils
from cros.factory.test.e2e_test.common import AutomationMode
from cros.factory.test.e2e_test.automator import Automator, AutomationFunction


class AudioLoopAutomator(Automator):
  """The 'audio_loop' factory test automator."""
  # pylint: disable=C0322
  pytest_name = 'audio_loop'

  @AutomationFunction(automation_mode=AutomationMode.FULL,
                      wait_for_factory_test=False)
  def automateAudioLoop(self):
    prompt_text = 'Hit s to start loopback test'
    jack_status = audio_utils.AudioUtil().GetAudioJackStatus()
    if self.args.require_dongle == jack_status:
      self.uictl.WaitForContent(search_text=prompt_text)
      self.uictl.PressKey('S')
    else:
      self.uictl.WaitForContent(search_text=prompt_text)
