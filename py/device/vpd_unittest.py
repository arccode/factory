#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

import mox

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.gooftool.vpd import VPDTool


class VPDTest(unittest.TestCase):
  # pylint: disable=no-value-for-parameter

  def setUp(self):
    self.mox = mox.Mox()
    self.dut = device_utils.CreateDUTInterface()
    self.vpd = self.dut.vpd

    self.mox.StubOutWithMock(VPDTool, 'GetAllData')
    self.mox.StubOutWithMock(VPDTool, 'GetValue')
    self.mox.StubOutWithMock(VPDTool, 'UpdateData')

  def MockVPDGetAll(self, partition, data):
    """Mocks reading all data in vpd

    This function is used in every vpd Update test cases because
    we read data from vpd before writing it to avoid duplicate writing.
    Args:
      partition: 'RW_VPD' or 'RO_VPD'.
      data: A dict to be read.
    """
    self.dut.CallOutput(['vpd', '-i', partition, '-l']).AndReturn(
        '\n'.join(('"%s"="%s"' % (k, v) for k, v in data.iteritems())))

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGet(self):
    VPDTool.GetAllData(
        partition='RW_VPD').AndReturn(dict(a='b', foo='bar', empty=''))
    VPDTool.GetValue(
        'a', default_value=None, partition='RO_VPD').AndReturn('aa')
    VPDTool.GetValue('b', default_value=123, partition='RO_VPD').AndReturn(123)

    self.mox.ReplayAll()
    self.assertEquals(dict(a='b', foo='bar', empty=''), self.vpd.rw.GetAll())
    self.assertEquals('aa', self.vpd.ro.get('a'))
    self.assertEquals(123, self.vpd.ro.get('b', 123))
    self.mox.VerifyAll()

  def testUpdate(self):
    VPDTool.GetAllData(
        partition='RW_VPD').AndReturn(dict(a='b', foo='bar', empty=''))
    VPDTool.UpdateData(dict(w='x', y='z', foo=None), partition='RW_VPD')
    self.mox.ReplayAll()

    self.vpd.rw.Update(dict(w='x', y='z', foo=None))
    self.mox.VerifyAll()

  def testUpdatePartial(self):
    # "a"="b" is already in vpd, update will skip it.
    # "unset" is already not in vpd, update will skip it.
    VPDTool.GetAllData(
        partition='RW_VPD').AndReturn(dict(a='b', foo='bar', empty=''))
    VPDTool.UpdateData(dict(w='x', y='z'), partition='RW_VPD')
    self.mox.ReplayAll()

    self.vpd.rw.Update(dict(a='b', w='x', y='z', unset=None))
    self.mox.VerifyAll()

  def testDeleteOne(self):
    VPDTool.UpdateData(dict(a=None), partition='RW_VPD')
    self.mox.ReplayAll()

    self.vpd.rw.Delete('a')
    self.mox.VerifyAll()

  def testDeleteTwo(self):
    VPDTool.UpdateData(dict(a=None, b=None), partition='RW_VPD')
    self.mox.ReplayAll()

    self.vpd.rw.Delete('a', 'b')
    self.mox.VerifyAll()

  def testGetPartition(self):
    VPDTool.GetAllData(partition='RW_VPD').AndReturn(dict(foo='bar'))
    VPDTool.GetAllData(partition='RO_VPD').AndReturn(dict(bar='foo'))
    self.mox.ReplayAll()
    self.assertEquals(dict(foo='bar'),
                      self.vpd.GetPartition('rw').GetAll())
    self.assertEquals(dict(bar='foo'),
                      self.vpd.GetPartition('ro').GetAll())
    self.mox.VerifyAll()

if __name__ == '__main__':
  unittest.main()
