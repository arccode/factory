#!/usr/bin/trial --temp-directory=/tmp/_trial_temp/
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import logging
import os
import re
from twisted.trial import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire.service import umpire_service
from cros.factory.umpire import umpire_env
from cros.factory.umpire import utils


class SimpleService(umpire_service.UmpireService):

  """Test service that launches /bin/sh ."""

  def CreateProcesses(self, umpire_config, env):
    del umpire_config, env  # Unused.
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig({
        'executable': '/bin/sh',
        'name': 'P_bsh',
        'args': [],
        'path': '/tmp'})
    return [proc]


class MultiProcService(umpire_service.UmpireService):

  """Multiple process service."""

  def CreateProcesses(self, umpire_config, env):
    del umpire_config, env  # Unused.
    for p in xrange(0, 7):
      config_dict = {
          'executable': '/bin/sh',
          'name': 'P_%d' % p,
          'args': [],
          'path': '/tmp'}
      proc = umpire_service.ServiceProcess(self)
      proc.SetConfig(config_dict)
      yield proc


class RestartService(umpire_service.UmpireService):

  """A process that restarts fast."""

  def CreateProcesses(self, umpire_config, env):
    del umpire_config, env  # Unused.
    config_dict = {
        'executable': '/bin/sh',
        'name': 'P_restart',
        'args': ['-c', 'true'],
        'path': '/tmp',
        'restart': True}
    proc = umpire_service.ServiceProcess(self)
    proc.SetConfig(config_dict)
    return [proc]


class DupProcService(umpire_service.UmpireService):

  """Service contains duplicate processes."""

  def CreateProcesses(self, umpire_config, env):
    del umpire_config, env  # Unused.
    config_dict = {
        'executable': '/bin/sh',
        'name': 'P_dup',
        'args': [],
        'path': '/tmp'}
    proc1 = umpire_service.ServiceProcess(self)
    proc2 = umpire_service.ServiceProcess(self)
    proc1.SetConfig(config_dict)
    proc2.SetConfig(copy.deepcopy(config_dict))
    return [proc1, proc2]


class ServiceTest(unittest.TestCase):

  def setUp(self):
    self.umpire_config = {}
    self.services = []
    self.env = umpire_env.UmpireEnv()

  def tearDown(self):
    deferreds = []
    for svc in self.services:
      deferreds.append(svc.Stop())
    self.services = []
    return utils.ConcentrateDeferreds(deferreds)

  def testDuplicate(self):
    svc = DupProcService()
    self.services.append(svc)
    processes = svc.CreateProcesses(self.umpire_config, self.env)
    deferred = svc.Start(processes)

    def HandleStartResult(result):
      self.assertEqual(len(svc.processes), 1)
      return result

    deferred.addCallback(HandleStartResult)
    return deferred

  def testSetConfig(self):
    svc = SimpleService()
    proc = umpire_service.ServiceProcess(svc)
    # Config dict is empty
    self.assertRaises(ValueError, proc.SetConfig, {})
    # Required fields are missing
    self.assertRaises(ValueError, proc.SetConfig, {'name': 'foo'})
    # Config contains unknown fields
    self.assertRaises(ValueError, proc.SetConfig,
                      {'executable': 'foo', 'name': 'bar', 'args': [],
                       'path': '/', 'not_a_config_field': 'some_value'})
    # Config contains fields of wrong type.
    self.assertRaises(ValueError, proc.SetConfig,
                      {'executable': 'foo', 'name': 'bar', 'args': 'not-a-list',
                       'path': '/'})

  def testServiceStart(self):
    svc = SimpleService()
    self.services.append(svc)
    return svc.Start(svc.CreateProcesses(self.umpire_config, self.env))

  def testServiceMulti(self):
    svc = MultiProcService()
    self.services.append(svc)
    return svc.Start(svc.CreateProcesses(self.umpire_config, self.env))

  def testRestart(self):
    svc = RestartService()
    self.services.append(svc)
    deferred = svc.Start(svc.CreateProcesses(self.umpire_config, self.env))

    def HandleRestartResult(result):
      del result  # Unused.
      raise common.UmpireError('testRestart expects failure callback')

    def HandleRestartFailure(failure):
      # failure.trap(common.UmpireError)
      message = failure.getErrorMessage()
      logging.debug('Restart Errback() got: %s', message)
      self.assertTrue(re.search(r'^.+restart.+failed.+$', message))
      return 'OK'

    deferred.addCallbacks(HandleRestartResult, HandleRestartFailure)
    return deferred


# Turn on logging.DEBUG if env(LOG_LEVEL) is not empty
if os.environ.get('LOG_LEVEL'):
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(levelname)5s %(message)s')
else:
  # Disable logging for unittest
  logging.disable(logging.CRITICAL)
