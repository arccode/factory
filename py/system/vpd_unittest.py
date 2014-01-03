#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import logging
import mox
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.system import vpd


class VPDTest(unittest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()
    self.mox.StubOutWithMock(vpd, 'Spawn')
    self.mox.StubOutWithMock(logging, 'info')
    self.mox.StubOutWithMock(logging, 'error')

  def MockVPDGetAll(self, section, data):
    """Mocks reading all data in vpd

    This function is used in every vpd Update test cases because
    we read data from vpd before writing it to avoid duplicate writing.
    Args:
      section: 'RW_VPD' or 'RO_VPD'.
      data: A dict to be read.
    """
    process = self.mox.CreateMockAnything()
    process.stdout_lines(strip=True).AndReturn(
        ['"%s"="%s"' % (k, v) for k, v in data.iteritems()])
    vpd.Spawn(['vpd', '-i', section, '-l'], check_output=True).AndReturn(
      process)

  def tearDown(self):
    self.mox.UnsetStubs()

  def testGet(self):
    process = self.mox.CreateMockAnything()
    process.stdout_lines(strip=True).MultipleTimes().AndReturn(
        ['"a"="b"',
         '"foo"="bar"',
         '"empty"=""'])

    # pylint: disable=E1101
    vpd.Spawn(['vpd', '-i', 'RW_VPD', '-l'], check_output=True
              ).MultipleTimes().AndReturn(process)
    self.mox.ReplayAll()
    self.assertEquals(dict(a='b', foo='bar', empty=''), vpd.rw.GetAll())
    self.assertEquals('b', vpd.rw.get('a'))
    self.assertEquals('b', vpd.rw.get('a', 'default'))
    self.assertEquals(None, vpd.rw.get('nope'))
    self.assertEquals('default', vpd.rw.get('nope', 'default'))
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
    self.MockVPDGetAll('RW_VPD', dict())
    vpd.Spawn(
        ['vpd', '-i', 'RW_VPD', '-s', 'a=b', '-s', 'foo=bar', '-s', 'unset='],
        check_call=True)
    logging.info('Updating %s: %s', 'RW_VPD',
                 dict(a='b', foo='bar', unset=None))
    self.mox.ReplayAll()
    vpd.rw.Update(dict(a='b', foo='bar', unset=None))
    self.mox.VerifyAll()

  def testUpdatePartial(self):
    # "a"="b" is already in vpd, update will skip it.
    self.MockVPDGetAll('RW_VPD', dict(a='b'))
    vpd.Spawn(
        ['vpd', '-i', 'RW_VPD', '-s', 'foo=bar', '-s', 'unset='],
        check_call=True)
    logging.info('Updating %s: %s', 'RW_VPD',
                 dict(a='b', foo='bar', unset=None))
    self.mox.ReplayAll()
    vpd.rw.Update(dict(a='b', foo='bar', unset=None))
    self.mox.VerifyAll()

  def testUpdateRO(self):
    self.MockVPDGetAll('RO_VPD', dict())
    vpd.Spawn(['vpd', '-i', 'RO_VPD', '-s', 'a=b'], check_call=True)
    logging.info('Updating %s: %s', 'RO_VPD', dict(a='b'))
    self.mox.ReplayAll()
    vpd.ro.Update(dict(a='b'))
    self.mox.VerifyAll()

  def testUpdateRedacted(self):
    self.MockVPDGetAll('RW_VPD', dict())
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
    self.MockVPDGetAll('RW_VPD', dict())
    logging.info('Updating %s: %s', 'RW_VPD', dict())
    self.mox.ReplayAll()
    vpd.rw.Update({})
    self.mox.VerifyAll()

  def testUpdateInvalidKey(self):
    self.MockVPDGetAll('RW_VPD', dict())
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Invalid VPD key',
                            vpd.rw.Update, {' ': 'a'}, log=False)
    self.mox.VerifyAll()

  def testUpdateInvalidValue(self):
    self.MockVPDGetAll('RW_VPD', dict())
    self.mox.ReplayAll()
    self.assertRaisesRegexp(ValueError, 'Invalid VPD value',
                            vpd.rw.Update, {'a': '\"'}, log=False)
    self.mox.VerifyAll()

  def testDeleteNone(self):
    self.mox.ReplayAll()
    vpd.rw.Delete()  # no-op
    self.mox.VerifyAll()

  def testDeleteOne(self):
    vpd.Spawn(
        ['vpd', '-i', 'RW_VPD', '-d', 'a'],
        check_call=True, log_stderr_on_error=True)
    self.mox.ReplayAll()
    vpd.rw.Delete('a')
    self.mox.VerifyAll()

  def testDeleteTwo(self):
    vpd.Spawn(
        ['vpd', '-i', 'RW_VPD', '-d', 'a', '-d', 'b'],
        check_call=True, log_stderr_on_error=True)
    self.mox.ReplayAll()
    vpd.rw.Delete('a', 'b')
    self.mox.VerifyAll()

  def testDeleteError(self):
    vpd.Spawn(
        ['vpd', '-i', 'RW_VPD', '-d', 'a'],
        check_call=True, log_stderr_on_error=True).AndRaise(ValueError)
    self.mox.ReplayAll()
    self.assertRaises(ValueError, vpd.rw.Delete, 'a')
    self.mox.VerifyAll()


if __name__ == '__main__':
  unittest.main()
