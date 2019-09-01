#!/usr/bin/env python2
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for toybox."""

import textwrap
import unittest

import mock

import factory_common  # pylint: disable=unused-import
from cros.factory.device import device_utils
from cros.factory.device import toybox


class ToyboxTest(unittest.TestCase):

  def setUp(self):
    self.dut = device_utils.CreateDUTInterface()

  def testBaseName(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='abc\n')
    self.assertEquals(self.dut.toybox.basename('abc.def'), 'abc')
    self.dut.CheckOutput.assert_called_with(['toybox', 'basename', 'abc.def'])

  def testCat(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='abc\n')
    self.assertEquals(self.dut.toybox.cat('/abc'), 'abc\n')
    self.dut.CheckOutput.assert_called_with(['toybox', 'cat', '/abc'])

    self.dut.CheckOutput = mock.MagicMock(return_value='abc\n')
    self.assertEquals(self.dut.toybox.cat('/abc', unbuffered=True), 'abc\n')
    self.dut.CheckOutput.assert_called_with(['toybox', 'cat', '-u', '/abc'])

    self.dut.CheckOutput = mock.MagicMock(return_value='abc\ndef\n')
    self.assertEquals(self.dut.toybox.cat(['/abc', '/def']), 'abc\ndef\n')
    self.dut.CheckOutput.assert_called_with(['toybox', 'cat', '/abc', '/def'])

  def testChvt(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.chvt(3)
    self.dut.CheckCall.assert_called_with(['toybox', 'chvt', '3'])

  def testClear(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.clear()
    self.dut.CheckCall.assert_called_with(['toybox', 'clear'])

  def testDd(self):
    self.dut.CheckOutput = mock.MagicMock(return_value=' ')
    self.assertEquals(self.dut.toybox.dd('/dev/null', bs=1, count=1), ' ')
    self.dut.CheckOutput.assert_called_with(['toybox', 'dd', 'if=/dev/null',
                                             'bs=1', 'count=1'])
    self.assertEquals(self.dut.toybox.dd('/dev/null', bs=1, count=1, conv=[]),
                      ' ')
    self.dut.CheckOutput.assert_called_with(['toybox', 'dd', 'if=/dev/null',
                                             'bs=1', 'count=1'])

  def testDf(self):
    output = textwrap.dedent("""
      Filesystem      1K-blocks       Used  Available Use% Mounted on
      udev             32924692         12   32924680   1% /dev
      """[1:])
    self.dut.CheckOutput = mock.MagicMock(return_value=output)
    self.assertEquals(self.dut.toybox.df('')[0].kblocks, 32924692)
    self.dut.CheckOutput.assert_called_with(['toybox', 'df'])

  def testDirname(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='/abc\n')
    self.assertEquals(self.dut.toybox.dirname('/abc/def'), '/abc')
    self.dut.CheckOutput.assert_called_with(['toybox', 'dirname', '/abc/def'])

  def testFree(self):
    output = textwrap.dedent("""
                total        used        free      shared     buffers
      Mem:      67450236928 62023270400  5426966528           0  2090393600
      -/+ buffers/cache:    59932876800  7517360128
      Swap:     68618809344  2034167808 66584641536
      """[1:])
    self.dut.CheckOutput = mock.MagicMock(return_value=output)
    self.assertEquals(self.dut.toybox.free().mem_min_used, 59932876800)
    self.dut.CheckOutput.assert_called_with(['toybox', 'free', '-b'])

  def testFstype(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='ext2\n')
    self.assertEquals(self.dut.toybox.fstype('/dev/sda'), ['ext2'])
    self.dut.CheckOutput.assert_called_with(['toybox', 'fstype', '/dev/sda'])

  def testHead(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='123\n')
    self.assertEquals(self.dut.toybox.head('abc'), '123\n')
    self.dut.CheckOutput.assert_called_with(['toybox', 'head', 'abc'])

    self.dut.CheckOutput = mock.MagicMock(return_value='123\n')
    self.assertEquals(self.dut.toybox.head('abc', number=10), '123\n')
    self.dut.CheckOutput.assert_called_with(
        ['toybox', 'head', '-n', '10', 'abc'])

  def testHostname(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='tpe\n')
    self.assertEquals(self.dut.toybox.hostname(), 'tpe')
    self.dut.CheckOutput.assert_called_with(['toybox', 'hostname'])

    self.dut.CheckCall = mock.MagicMock(return_value='new-tpe\n')
    self.assertEquals(self.dut.toybox.hostname('new-tpe'), 'new-tpe')
    self.dut.CheckCall.assert_called_with(['toybox', 'hostname', 'new-tpe'])

  def testLogname(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='root\n')
    self.assertEquals(self.dut.toybox.logname(), 'root')
    self.dut.CheckOutput.assert_called_with(['toybox', 'logname'])

  def testMount(self):
    output = textwrap.dedent("""
      rootfs on / type rootfs (rw)
      """[1:])
    self.dut.CheckOutput = mock.MagicMock(return_value=output)
    results = self.dut.toybox.mount()[0]
    self.assertEquals(results.device, 'rootfs')
    self.assertEquals(results.path, '/')
    self.assertEquals(results.type, 'rootfs')
    self.assertEquals(results.options, 'rw')
    self.dut.CheckOutput.assert_called_with(['toybox', 'mount'])

  def testNohup(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.nohup(['sleep', '10'])
    self.dut.CheckCall.assert_called_with(['toybox', 'nohup', 'sleep', '10'])

  def testPartprobe(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.partprobe('/dev/sda')
    self.dut.CheckCall.assert_called_with(['toybox', 'partprobe', '/dev/sda'])

  def testPkill(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.pkill('stressapptest', signal=9)
    self.dut.CheckCall.assert_called_with(['toybox', 'pkill', '-l', '9',
                                           'stressapptest'])

    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.pkill('ls -al', exact=True, full=True, pgroup=0)
    self.dut.CheckCall.assert_called_with(['toybox', 'pkill', '-x', '-f',
                                           '-g', '0', '\'ls -al\''])

  def testPwd(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='/\n')
    self.assertEquals(self.dut.toybox.pwd(), '/')
    self.dut.CheckOutput.assert_called_with(['toybox', 'pwd'])

  def testReset(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.reset()
    self.dut.CheckCall.assert_called_with(['toybox', 'reset'])

  def testRmdir(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.rmdir('/abc')
    self.dut.CheckCall.assert_called_with(['toybox', 'rmdir', '/abc'])
    self.dut.toybox.rmdir('/abc', parents=True)
    self.dut.CheckCall.assert_called_with(['toybox', 'rmdir', '-p', '/abc'])

  def testSync(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.sync()
    self.dut.CheckCall.assert_called_with(['toybox', 'sync'])

  def testUnlink(self):
    self.dut.CheckCall = mock.MagicMock(return_value=0)
    self.dut.toybox.unlink('/abc')
    self.dut.CheckCall.assert_called_with(['toybox', 'unlink', '/abc'])

  def testUptime(self):
    output = textwrap.dedent("""
      07:02:03 up 45 days,  4:56,  2 users,  load average: 1.26, 1.37, 1.20
      """[1:])
    self.dut.CheckOutput = mock.MagicMock(return_value=output)
    self.assertEquals(self.dut.toybox.uptime().loadavg_1min, 1.26)
    self.dut.CheckOutput.assert_called_with(['toybox', 'uptime'])

  def testWc(self):
    output = textwrap.dedent("""
      74  309 2193 link.py
      """[1:])
    self.dut.CheckOutput = mock.MagicMock(return_value=output)
    results = self.dut.toybox.wc('link.py')[0]
    self.assertEquals(results.lines, 74)
    self.assertEquals(results.words, 309)
    self.assertEquals(results.bytes, 2193)
    self.assertEquals(results.filename, 'link.py')
    self.dut.CheckOutput.assert_called_with(
        ['toybox', 'wc', '-l', '-w', '-c', 'link.py'])

  def testWhich(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='/bin/ls\n')
    self.assertEquals(self.dut.toybox.which('ls'), ['/bin/ls'])
    self.dut.CheckOutput.assert_called_with(['toybox', 'which', 'ls'])

  def testWhoami(self):
    self.dut.CheckOutput = mock.MagicMock(return_value='root\n')
    self.assertEquals(self.dut.toybox.whoami(), 'root')
    self.dut.CheckOutput.assert_called_with(['toybox', 'whoami'])

  def testOverrideProvider(self):
    # pylint: disable=protected-access
    # set default provider to toolbox
    _toybox = toybox.Toybox(self.dut, provider_map={'*': 'toolbox'})
    self.dut.CheckOutput = mock.MagicMock(return_value=None)
    _toybox.dd('/dev/null', bs=1, count=1)
    self.dut.CheckOutput.assert_called_with(['toolbox', 'dd', 'if=/dev/null',
                                             'bs=1', 'count=1'])

    # use dd provided by busybox
    _toybox = toybox.Toybox(self.dut, provider_map={'*': 'toolbox',
                                                    'dd': 'busybox'})
    _toybox.dd('/dev/null', bs=1, count=1)
    self.dut.CheckOutput.assert_called_with(['busybox', 'dd', 'if=/dev/null',
                                             'bs=1', 'count=1'])

    # use dd provided by system
    _toybox = toybox.Toybox(self.dut, provider_map={'*': 'toolbox',
                                                    'dd': None})
    _toybox.dd('/dev/null', bs=1, count=1)
    self.dut.CheckOutput.assert_called_with(['dd', 'if=/dev/null',
                                             'bs=1', 'count=1'])


if __name__ == '__main__':
  unittest.main()
