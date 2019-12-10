# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A pytest helps you control FactoryStateLayer

Description
-----------
This pytest helps you control `FactoryStateLayer`s.  The factory state server
(an instance of `cros.factory.test.state.FactoryState`) could have multiple
layers.  The first layer (layer 0) is the default layer which uses python shelve
module and will be saved under /var/factory/state/ by default.  You can create
levels on top of layer 0, but all additional layers only exists in memory, the
data will be destroyed when the layer is removed.  Unless the layer is merged to
first layer.  For example::

  Layer 1  # only exists in memory
  Layer 0  # saved in /var/factory/state/

If you try to read value from data shelf (e.g.
`state_proxy.data_shelf.Get('foo.bar')`), layer 1 will be checked first, and
then is layer 0.  For writing data (`state_proxy.data_shelf.Set('foo.bar', 5)`),
layer 1 will be modified, and layer 0 will not, no matter 'foo.bar' exists in
layer 0 or not.

This mechanism is designed for station based testing, so you can temporary copy
DUT state to test station, and remove it after the test is done.  Currently this
test only supports DUT using SSHLink, see examples for how it could be used.

Test Procedure
--------------
This pytest does not require operator interaction.

Dependency
----------
Depends on SSH to interact with remote DUT.

Examples
--------
Here is an example of station based test list::

  {
    "options": {
      "dut_options": {
        "link_class": "SSHLink",
        "host": "1.2.3.4"
      }
    },
    "tests": [
      {
        "inherit": "TestGroup",
        "label": "i18n! Main Loop",
        "iterations": -1,
        "retries": -1,
        "subtests": [
          {
            "pytest_name": "station_entry"
          },
          {
            "pytest_name": "factory_state",
            "args": {
              "action": "COPY",
              "device": "DUT"
            }
          },
          # Do the test ...
          {
            "pytest_name": "summary"
          },
          {
            "pytest_name": "factory_stateer",
            "args": {
              "action": "COPY",
              "device": "STATION"
            }
          },
          {
            "pytest_name": "factory_state",
            "args": {
              "action": "MERGE",
              "device": "DUT"
            }
          },
          {
            "pytest_name": "factory_state",
            "args": {
              "action": "POP",
              "device": "STATION"
            }
          },
          {
            "pytest_name": "station_entry",
            "args": {
              "start_station_tests": false
            }
          }
        ]
      }
    ]
  }
"""

import logging
import unittest

from cros.factory.device import device_utils
from cros.factory.device.links import ssh
from cros.factory.test import state
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import type_utils


ENUM_ACTION = type_utils.Enum(['APPEND', 'POP', 'COPY', 'MERGE'])

ENUM_ROLE = type_utils.Enum(['STATION', 'DUT'])


class ManipulateFactoryStateLayer(unittest.TestCase):
  ARGS = [
      Arg('action', ENUM_ACTION, 'What kind of action to do?'),
      Arg('dut_options', dict, 'DUT options to create remote dut instnace.',
          default={}),
      Arg('device', ENUM_ROLE,
          'Device to do the action.  If the action is COPY, it requires two '
          'devices (copy from source to destination), the `device` will be '
          'source, and destination will be the other role.',
          default=ENUM_ROLE.STATION),
      Arg('exclude_current_test_list', bool,
          "For `COPY` command, don't copy test states of current test list.",
          default=True),
      Arg('include_tests', bool,
          'For `COPY` command, include `tests_shelf`.', default=False),
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface(**self.args.dut_options)

  def _CreateStationStateProxy(self):
    return state.GetInstance()

  def _CreateDUTStateProxy(self):
    if self.dut.link.IsLocal():
      return state.GetInstance()
    if isinstance(self.dut.link, ssh.SSHLink):
      return state.GetInstance(self.dut.link.host)
    logging.warning('state proxy for %s is not supported',
                    self.dut.link.__class__.__name__)
    return None

  def runTest(self):
    _ACTION_TO_FUNC = {
        ENUM_ACTION.APPEND: self.DoAppend,
        ENUM_ACTION.POP: self.DoPop,
        ENUM_ACTION.COPY: self.DoCopy,
        ENUM_ACTION.MERGE: self.DoMerge,
    }

    if self.args.device == ENUM_ROLE.STATION:
      source = self._CreateStationStateProxy()
      destination = self._CreateDUTStateProxy()
    else:
      source = self._CreateDUTStateProxy()
      destination = self._CreateStationStateProxy()

    _ACTION_TO_FUNC[self.args.action](source, destination)

  def DoAppend(self, source, destination):
    del destination  # unused
    if source is None:
      raise type_utils.TestFailure('Unsupported operation')
    source.AppendLayer()

  def DoPop(self, source, destination):
    del destination  # unused
    if source is None:
      raise type_utils.TestFailure('Unsupported operation')
    source.PopLayer()

  def DoMerge(self, source, destination):
    del destination  # unused
    if source is None:
      raise type_utils.TestFailure('Unsupported operation')
    # currently, there are at most 2 layers, so you can only merge layer 1 to
    # layer 0.
    source.MergeLayer(1)

  def DoCopy(self, source, destination):
    if source is None or destination is None:
      raise type_utils.TestFailure('Unsupported operation')

    if destination.GetLayerCount() == state.FactoryState.MAX_LAYER_NUM:
      logging.warning('Max layer number reached, top layer will be popped.')
      destination.PopLayer()

    serialized_data = source.SerializeLayer(
        layer_index=-1, include_data=True, include_tests=True)
    layer = state.FactoryStateLayer()
    layer.Loads(serialized_data)

    # Only pack device data.
    # TODO(stimim): refactor state.py to make this more clear.
    device_data = layer.data_shelf.GetValue(state.KEY_DEVICE_DATA,
                                            optional=True) or {}
    layer.data_shelf.Clear()
    layer.data_shelf.SetValue(state.KEY_DEVICE_DATA, device_data)

    if self.args.include_tests:
      # We need to modify the test states, otherwise the test that is currently
      # running on station might be messed up.

      # remove root node, because every test list has this node.
      layer.tests_shelf.DeleteKeys(
          [state.FactoryState.ConvertTestPathToKey('')],
          optional=True)
      if self.args.exclude_current_test_list:
        test_list = self.test_info.ReadTestList()
        for test in test_list.Walk():
          layer.tests_shelf.DeleteKeys(
              [state.FactoryState.ConvertTestPathToKey(test.path)],
              optional=True)
    else:
      layer.tests_shelf.Clear()

    serialized_data = layer.Dumps(True, True)
    destination.AppendLayer(serialized_data=serialized_data)
