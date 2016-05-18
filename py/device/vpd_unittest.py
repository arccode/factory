#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.device import device_utils


class VPDTest(unittest.TestCase):

  def setUp(self):
    self.mox = mox.Mox()
    self.dut = device_utils.CreateDUTInterface()
    self.mox.StubOutWithMock(self.dut, 'CheckCall')
    self.mox.StubOutWithMock(self.dut, 'CallOutput')
    self.mox.StubOutWithMock(logging, 'info')
    self.mox.StubOutWithMock(logging, 'error')
    self.vpd = self.dut.vpd

  def MockVPDGetAll(self, section, data):
    """Mocks reading all data in vpd

    This function is used in every vpd Update test cases because
    we read data from vpd before writing it to avoid duplicate writing.
    Args:
      section: 'RW_VPD' or 'RO_VPD'.
      data: A dict to be read.
    """
    self.dut.CallOutput(['vpd', '-i', section, '-l']).AndReturn(
        '\n'.join(('"%s"="%s"' % (k, v) for k, v in data.iteritems())))

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGet(self):
    self.MockVPDGetAll('RW_VPD', {'a': 'b', 'foo': 'bar', 'empty': ''})
    self.dut.CallOutput(
        ['vpd', '-i', 'RW_VPD', '-g', 'a']).AndReturn('b')
    self.dut.CallOutput(
        ['vpd', '-i', 'RW_VPD', '-g', 'a']).AndReturn('b')
    self.dut.CallOutput(
        ['vpd', '-i', 'RW_VPD', '-g', 'nope']).AndReturn(None)
    self.dut.CallOutput(
        ['vpd', '-i', 'RW_VPD', '-g', 'nope']).AndReturn('default')
    self.mox.ReplayAll()
    self.assertEquals(dict(a='b', foo='bar', empty=''), self.vpd.rw.GetAll())
    self.assertEquals('b', self.vpd.rw.get('a'))
    self.assertEquals('b', self.vpd.rw.get('a', 'default'))
    self.assertEquals(None, self.vpd.rw.get('nope'))
    self.assertEquals('default', self.vpd.rw.get('nope', 'default'))
    self.mox.VerifyAll()

  def testGetAllBadVPD(self):
    # A bad input missing trailing " for item a.
    # Should ignore the bad line, but keep going
    self.dut.CallOutput(
        ['vpd', '-i', 'RW_VPD', '-l']).AndReturn(
            '"a"="b\n"foo"="bar"\n')
    logging.error('Unexpected line in %s VPD: %r',
                  'RW_VPD', '"a"="b')
    self.mox.ReplayAll()
    self.assertEquals(dict(foo='bar'), self.vpd.rw.GetAll())
    self.mox.VerifyAll()

  def testUpdate(self):
    self.MockVPDGetAll('RW_VPD', dict())
    self.dut.CheckCall(
        ['vpd', '-i', 'RW_VPD', '-s', 'a=b', '-s', 'foo=bar', '-s', 'unset='])
    logging.info('Updating %s: %s', 'RW_VPD',
                 dict(a='b', foo='bar', unset=None))
    self.mox.ReplayAll()
    self.vpd.rw.Update(dict(a='b', foo='bar', unset=None))
    self.mox.VerifyAll()

  def testUpdatePartial(self):
    # "a"="b" is already in vpd, update will skip it.
    self.MockVPDGetAll('RW_VPD', dict(a='b'))
    self.dut.CheckCall(
        ['vpd', '-i', 'RW_VPD', '-s', 'foo=bar', '-s', 'unset='])
    logging.info('Updating %s: %s', 'RW_VPD',
                 dict(a='b', foo='bar', unset=None))
    self.mox.ReplayAll()
    self.vpd.rw.Update(dict(a='b', foo='bar', unset=None))
    self.mox.VerifyAll()

  def testUpdateRO(self):
    self.MockVPDGetAll('RO_VPD', dict())
    self.dut.CheckCall(['vpd', '-i', 'RO_VPD', '-s', 'a=b'])
    logging.info('Updating %s: %s', 'RO_VPD', dict(a='b'))
    self.mox.ReplayAll()
    self.vpd.ro.Update(dict(a='b'))
    self.mox.VerifyAll()

  def testUpdateRedacted(self):
    self.MockVPDGetAll('RW_VPD', dict())
    self.dut.CheckCall(
        ['vpd', '-i', 'RW_VPD',
         '-s', 'a=b', '-s', 'gbind_attribute=', '-s', 'ubind_attribute=bar'])
    logging.info('Updating %s: %s', 'RW_VPD',
                 dict(a='b',
                      ubind_attribute='<redacted 3 chars>',
                      gbind_attribute=None))
    self.mox.ReplayAll()
    self.vpd.rw.Update(dict(a='b', ubind_attribute='bar', gbind_attribute=None))
    self.mox.VerifyAll()

  def testUpdateNothing(self):
    self.MockVPDGetAll('RW_VPD', dict())
    logging.info('Updating %s: %s', 'RW_VPD', dict())
    self.mox.ReplayAll()
    self.vpd.rw.Update({})
    self.mox.VerifyAll()

  def testUpdateInvalidKey(self):
    self.MockVPDGetAll('RW_VPD', dict())
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Invalid VPD key',
                            self.vpd.rw.Update, {' ': 'a'}, log=False)
    self.mox.VerifyAll()

  def testUpdateInvalidValue(self):
    self.MockVPDGetAll('RW_VPD', dict())
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Invalid VPD value',
                            self.vpd.rw.Update, {'a': '\"'}, log=False)
    self.mox.VerifyAll()

  def testDeleteNone(self):
    self.mox.ReplayAll()
    self.vpd.rw.Delete()  # no-op
    self.mox.VerifyAll()

  def testDeleteOne(self):
    self.dut.CheckCall(
        ['vpd', '-i', 'RW_VPD', '-d', 'a'])
    self.mox.ReplayAll()
    self.vpd.rw.Delete('a')
    self.mox.VerifyAll()

  def testDeleteTwo(self):
    self.dut.CheckCall(
        ['vpd', '-i', 'RW_VPD', '-d', 'a', '-d', 'b'])
    self.mox.ReplayAll()
    self.vpd.rw.Delete('a', 'b')
    self.mox.VerifyAll()

  def testDeleteError(self):
    self.dut.CheckCall(
        ['vpd', '-i', 'RW_VPD', '-d', 'a']).AndRaise(ValueError)
    self.mox.ReplayAll()
    self.assertRaises(ValueError, self.vpd.rw.Delete, 'a')
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
