#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import mox
import unittest2

import factory_common  # pylint: disable=W0611
from cros.factory.system import vpd


class VPDTest(unittest2.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(vpd, 'Spawn')
    self.mox.StubOutWithMock(logging, 'info')
    self.mox.StubOutWithMock(logging, 'error')

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGetAll(self):
    process = self.mox.CreateMockAnything()
    process.stdout_lines(strip=True).AndReturn(['"a"="b"',
                                                '"foo"="bar"'])
    vpd.Spawn(['vpd', '-i', 'RW_VPD', '-l'], check_output=True).AndReturn(
      process)
    self.mox.ReplayAll()
    self.assertEquals(dict(a='b', foo='bar'), vpd.rw.GetAll())
    self.mox.VerifyAll()

  def testGetAllBadVPD(self):
    # Should ignore the bad line, but keep going
    process = self.mox.CreateMockAnything()
    process.stdout_lines(strip=True).AndReturn(['"a"="b',  # Missing trailing "
                                                '"foo"="bar"'])
    vpd.Spawn(['vpd', '-i', 'RW_VPD', '-l'], check_output=True).AndReturn(
      process)
    logging.error('Unexpected line in %s VPD: %r',
                  'RW_VPD', '"a"="b')
    self.mox.ReplayAll()
    self.assertEquals(dict(foo='bar'), vpd.rw.GetAll())
    self.mox.VerifyAll()

  def testUpdate(self):
    vpd.Spawn(
        ['vpd', '-i', 'RW_VPD', '-s', 'a=b', '-s', 'foo=bar', '-s', 'unset='],
        check_call=True)
    logging.info('Updating %s: %s', 'RW_VPD',
                 dict(a='b', foo='bar', unset=None))
    self.mox.ReplayAll()
    vpd.rw.Update(dict(a='b', foo='bar', unset=None))
    self.mox.VerifyAll()

  def testUpdateRO(self):
    vpd.Spawn(['vpd', '-i', 'RO_VPD', '-s', 'a=b'], check_call=True)
    logging.info('Updating %s: %s', 'RO_VPD', dict(a='b'))
    self.mox.ReplayAll()
    vpd.ro.Update(dict(a='b'))
    self.mox.VerifyAll()

  def testUpdateRedacted(self):
    vpd.Spawn(
        ['vpd', '-i', 'RW_VPD',
         '-s', 'a=b', '-s', 'gbind_attribute=', '-s', 'ubind_attribute=bar'],
        check_call=True)
    logging.info('Updating %s: %s', 'RW_VPD',
                 dict(a='b',
                      ubind_attribute='<redacted 3 chars>',
                      gbind_attribute=None))
    self.mox.ReplayAll()
    vpd.rw.Update(dict(a='b', ubind_attribute='bar', gbind_attribute=None))
    self.mox.VerifyAll()

  def testUpdateNothing(self):
    logging.info('Updating %s: %s', 'RW_VPD', dict())
    self.mox.ReplayAll()
    vpd.rw.Update({})
    self.mox.VerifyAll()

  def testUpdateInvalidKey(self):
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Invalid VPD key',
                            vpd.rw.Update, {' ': 'a'}, log=False)
    self.mox.VerifyAll()

  def testUpdateInvalidValue(self):
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Invalid VPD value',
                            vpd.rw.Update, {'a': '\"'}, log=False)
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest2.main()
