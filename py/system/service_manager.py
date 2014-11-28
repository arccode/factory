# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

import factory_common  # pylint: disable=W0611
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn


START_TEXT = 'start/running'
STOP_TEXT = 'stop/waiting'
Status = utils.Enum(['START', 'STOP', 'UNKNOWN'])


def ParseServiceStatus(status_output):
  '''Parses service status output and returns service status.'''
  if START_TEXT in status_output:
    return Status.START
  elif STOP_TEXT in status_output:
    return Status.STOP
  else:
    return Status.UNKNOWN


def SetServiceStatus(service, status=None):
  '''Sets service to the given status and returns the status'''
  upstart_command = {
      None: 'status',
      Status.START: 'start',
      Status.STOP: 'stop'}[status]
  stdout_data = Spawn([upstart_command, service], read_stdout=True,
                      check_call=True, log=True).stdout_data
  new_status = ParseServiceStatus(stdout_data)
  if status is not None:
    if new_status == status:
      logging.info('Service %s set to %s', service, status)
    else:
      logging.warning('Failed to set %s to %s (%s)', service, status,
                      stdout_data)
  return new_status


def GetServiceStatus(service, ignore_failure=False):
  '''Returns service status.

    Args:
      service: The service name we want to acquire status.
      ignore_failure: True to suppress exception when failed to get status.

    Returns:
      Service status. If ignore_failure is True, a None will be returned
      when failing to get status.
  '''
  try:
    return SetServiceStatus(service, None)
  except:  # pylint: disable=W0702
    if not ignore_failure:
      raise
    logging.exception('Failed to get service %s.', service)
    return None


class ServiceManager(object):
  '''Object to manage services for tests.

  Use SetupServices to setup services that should be enabled or disabled
  before invoking a test. When the test finishes, call RestoreServices to
  restore services that was affected to their status before.
  '''

  def __init__(self):
    self.original_status_map = {}

  def SetupServices(self, enable_services=None, disable_services=None):
    '''Makes sure the services in enable_services are started and those in
    disable_services are stopped.

    Args:
      enable_services: A list of services that should be started.
      disable_sercices: A list of services that should be stopped.
    '''
    for status, services in (
        (Status.START, enable_services),
        (Status.STOP, disable_services)):
      if services:
        for service in services:
          original_status = GetServiceStatus(service)
          if original_status != status:
            self.original_status_map[service] = original_status
            SetServiceStatus(service, status)

  def RestoreServices(self):
    '''Restores the services affected in SetupServices back to their original
    states.'''
    for service, status in self.original_status_map.iteritems():
      SetServiceStatus(service, status)
    self.original_status_map.clear()
