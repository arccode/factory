# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging

from six import iteritems

from . import type_utils
from .process_utils import CheckOutput
from .process_utils import OpenDevNull


START_TEXT = 'start/running'
STOP_TEXT = 'stop/waiting'
Status = type_utils.Enum(['START', 'STOP', 'UNKNOWN'])


def ParseServiceStatus(status_output):
  """Parses service status output and returns service status."""
  if START_TEXT in status_output:
    return Status.START
  elif STOP_TEXT in status_output:
    return Status.STOP
  else:
    return Status.UNKNOWN


def SetServiceStatus(service, status=None, dut=None):
  """Sets service to the given status and returns the status"""
  upstart_command = {
      None: 'status',
      Status.START: 'start',
      Status.STOP: 'stop'}[status]

  check_output = dut.CheckOutput if dut else CheckOutput
  cmd = [upstart_command, service]

  logging.info('SetServiceStatus: cmd=%r, function=%r', cmd, check_output)
  stdout_data = check_output(cmd)

  new_status = ParseServiceStatus(stdout_data)
  if status is not None:
    if new_status == status:
      logging.info('Service %s set to %s', service, status)
    else:
      logging.warning('Failed to set %s to %s (%s)', service, status,
                      stdout_data)
  return new_status


def GetServiceStatus(service, ignore_failure=False, dut=None):
  '''Returns service status.

    Args:
      service: The service name we want to acquire status.
      ignore_failure: True to suppress exception when failed to get status.

    Returns:
      Service status. If ignore_failure is True, a None will be returned
      when failing to get status.
  '''
  try:
    return SetServiceStatus(service, None, dut)
  except Exception:
    if not ignore_failure:
      raise
    logging.exception('Failed to get service %s.', service)
    return None


def CheckServiceExists(service, dut=None):
  '''Check if the given service name exists or not.

  Use 'status' command and check its return code. If the command
  excutes successfully, the service is considered existed.
  And, vice versa.

  Args:
    service: The service name to test existence
    dut: optional argument to check the service on the given DUT

  Returns:
    A boolean flag tells if the given service name exists or not.
  '''
  try:
    check_output = dut.CheckOutput if dut else CheckOutput
    cmd = ['status', service]
    check_output(cmd, stderr=OpenDevNull())
  except Exception:
    return False
  return True


class ServiceManager(object):
  '''Object to manage services for tests.

  Use SetupServices to setup services that should be enabled or disabled
  before invoking a test. When the test finishes, call RestoreServices to
  restore services that was affected to their status before.
  '''

  def __init__(self, dut=None):
    self.original_status_map = {}
    self.dut = dut

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
          original_status = GetServiceStatus(service, dut=self.dut)
          if original_status != status:
            self.original_status_map[service] = original_status
            SetServiceStatus(service, status, self.dut)

  def RestoreServices(self):
    '''Restores the services affected in SetupServices back to their original
    states.'''
    for service, status in iteritems(self.original_status_map):
      SetServiceStatus(service, status, self.dut)
    self.original_status_map.clear()
