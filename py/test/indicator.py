#!/usr/bin/python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This file is a simple example for indicator implementation.

import logging
import os
import threading
import yaml

from cros.factory.utils.process_utils import Spawn

# Use configuration file to define different state.
# Configuration file is using YAML nested collections format.
#
# =============== Configuration Example ===================
# running: ['echo', 'In running state']
# failed: ['echo', 'In failed state']
# =========================================================

_DEFAULT_CONFIG_PATH = '/usr/local/factory/py/test/indicator.conf'

# In test list, we can add indicator test cases.
# For example:
#
# def SetIndicatorState(state):
#   indicator_instance = indicator.get_indicator_instance()
#   indicator_instance.SetState(state)
#
# INDICATOR_RUNNING = FactoryTest(
#     id='Indicator_running',
#     invocation_target=lambda t: SetIndicatorState('running')
#     )
#
# We can also use prepare and finish parameters in OperatorTest.
# Then we can set running indicator before test case starts to run
# and check test result when test case completed.
# For example:
#
# def CheckTestResult(test_state):
#   if test_state == TestState.FAILED:
#     indicator_instance = indicator.get_indicator_instance()
#     indicator_instance.SetState('failed')
#
# OperatorTest(
#     id='test_case',
#     pytest_name='test_case',
#     prepare=lambda : SetIndicatorState('running'),
#     finish=CheckTestResult)

_indicator_instance = None

def get_indicator_instance():
  global _indicator_instance  # pylint: disable=W0603
  if _indicator_instance is None:
    _indicator_instance = Indicator()
  return _indicator_instance


class Indicator(object):
  """This class is used for indicator.

  User can define the indicator method in configuration file and set different
  state during tests.
  """

  def __init__(self):
    self.config = {}
    self.enabled = False
    self.lock = threading.Lock()
    if os.path.exists(_DEFAULT_CONFIG_PATH):
      with open(_DEFAULT_CONFIG_PATH, 'r') as config_file:
        self.config = yaml.load(config_file)
    else:
      logging.error('Cannot find configuration file.')

  def SetIndicator(self, enable):
    """Sets indicator enable or disable. This function is used in
    test_list.

    Args:
      enable: boolean value.
    """
    with self.lock:
      self.enabled = enable

  def SetState(self, state):
    """Sets state. This function is used in test_list."""
    with self.lock:
      if not self.enabled:
        return
      if state in self.config:
        command = self.config[state]
        Spawn(command)
      else:
        logging.error('No matched state: %s', state)
