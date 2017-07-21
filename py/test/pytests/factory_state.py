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
levels on top of layer 0, but all additional layers only exists in memroy, the
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

  with TestGroup(label=_('Main Loop')) as test_group:
    test_group.dut_options = {
        'link_class': 'SSHLink',
        'host': '1.2.3.4',
    }
    FactoryTest(pytest_name='station_entry')
    FactoryTest(  # copy DUT state to a new layer
        pytest_name='factory_state',
        dargs={
            'action': 'COPY',
            'device': 'DUT'})
    # Do the test ...
    FactoryTest(pytest_name='summary')  # show a summary
    FactoryTest(  # copy new state back to DUT
        pytest_name='factory_stateer',
        dargs={
            'action': 'COPY',
            'device': 'STATION')
    FactoryTest(  # merge new state with old state
        pytest_name='factory_state',
        dargs={
            'action': 'MERGE',
            'device': 'DUT'})
    FactoryTest(  # pop dut state
        pytest_name='factory_state',
        dargs={
            'action': 'POP',
            'device': 'STATION'})
    FactoryTest(  # wait for DUT to disconnect
        pytest_name='station_entry',
        dargs={'start_station_tests': False})
"""

import logging
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device.links import ssh
from cros.factory.test import factory
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
  ]

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface(**self.args.dut_options)

  def _CreateStationStateProxy(self):
    return state.get_instance()

  def _CreateDUTStateProxy(self):
    if self.dut.link.IsLocal():
      return state.get_instance()
    if isinstance(self.dut.link, ssh.SSHLink):
      return state.get_instance(self.dut.link.address)
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
      raise factory.FactoryTestFailure('Unsupported operation')
    source.AppendLayer()

  def DoPop(self, source, destination):
    del destination  # unused
    if source is None:
      raise factory.FactoryTestFailure('Unsupported operation')
    source.PopLayer()

  def DoMerge(self, source, destination):
    del destination  # unused
    if source is None:
      raise factory.FactoryTestFailure('Unsupported operation')
    # currently, there are at most 2 layers, so you can only merge layer 1 to
    # layer 0.
    source.MergeLayer(1)

  def DoCopy(self, source, destination):
    if source is None or destination is None:
      raise factory.FactoryTestFailure('Unsupported operation')
    # currently, we only support getting data from top layer
    serialized_data = source.SerializeLayer(-1)
    if destination.GetLayerCount() == state.FactoryState.MAX_LAYER_NUM:
      logging.warning('Max layer number reached, top layer will be popped.')
      destination.PopLayer()
    destination.AppendLayer(serialized_data=serialized_data)
