# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import threading

from . import sync_utils
from . import type_utils
from . import process_utils


START_TEXT = 'start/running'
STOP_TEXT = 'stop/waiting'
Status = type_utils.Enum(['START', 'STOP', 'UNKNOWN'])


def ParseServiceStatus(status_output):
  """Parses service status output and returns service status."""
  if START_TEXT in status_output:
    return Status.START
  if STOP_TEXT in status_output:
    return Status.STOP
  return Status.UNKNOWN


def SetServiceStatus(service, status=None, dut=None):
  """Sets service to the given status and returns the status"""
  upstart_command = {
      None: 'status',
      Status.START: 'start',
      Status.STOP: 'stop'}[status]

  check_output = dut.CheckOutput if dut else process_utils.CheckOutput
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
  """Returns service status.

    Args:
      service: The service name we want to acquire status.
      ignore_failure: True to suppress exception when failed to get status.

    Returns:
      Service status. If ignore_failure is True, a None will be returned
      when failing to get status.
  """
  try:
    return SetServiceStatus(service, None, dut)
  except Exception:
    if not ignore_failure:
      raise
    logging.exception('Failed to get service %s.', service)
    return None


def CheckServiceExists(service, dut=None):
  """Check if the given service name exists or not.

  Use 'status' command and check its return code. If the command
  excutes successfully, the service is considered existed.
  And, vice versa.

  Args:
    service: The service name to test existence
    dut: optional argument to check the service on the given DUT

  Returns:
    A boolean flag tells if the given service name exists or not.
  """
  try:
    check_output = dut.CheckOutput if dut else process_utils.CheckOutput
    cmd = ['status', service]
    check_output(cmd, stderr=process_utils.DEVNULL)
  except Exception:
    return False
  return True


class ServiceManager:
  """Object to manage services for tests.

  Use SetupServices to setup services that should be enabled or disabled
  before invoking a test. When the test finishes, call RestoreServices to
  restore services that was affected to their status before.
  """

  # This is a class variable that counts the balance of setup/restore calls: it
  # will be incresed by 1 for each SetupServices() called, and decreased by 1
  # for each RestoreServices() called.
  _service_setup_count = 0
  _lock = threading.RLock()
  _original_status_map = {}
  _enable_services = []
  _disable_services = []

  def __init__(self, dut=None):
    # Lock is needed for @sync_utils.Synchronized.
    # Let all instances use the same lock from class to avoid race condition of
    # accessing class members.
    self._lock = ServiceManager._lock
    self.dut = dut

  @classmethod
  def _GetServiceSetupCount(cls):
    """Return the current service_setup_count.

    Returns:
      service_setup_count: The current balance of setup/restore calls.
    """
    return cls._service_setup_count

  @classmethod
  def _SetServiceSetupCount(cls, new_count):
    """Set service_setup_count to a new value.

    Args:
      new_count: The new balance of setup/restore calls.
    """
    cls._service_setup_count = new_count

  @sync_utils.Synchronized
  def SetupServices(self, enable_services=None, disable_services=None):
    """Makes sure the services in enable_services are started and those in
    disable_services are stopped.

    Args:
      enable_services: A list of services that should be started.
      disable_services: A list of services that should be stopped.
    """
    enable_services = enable_services or []
    disable_services = disable_services or []
    service_setup_count = self._GetServiceSetupCount()
    self._SetServiceSetupCount(service_setup_count + 1)

    if service_setup_count > 0:
      if (set(ServiceManager._enable_services) != set(enable_services) or
          set(ServiceManager._disable_services) != set(disable_services)):
        logging.warning('Trying to setup services lists which are '
                        'different from the existing ones. Do nothing. '
                        'Existing enable_services: %s. '
                        'Existing disable_services: %s. '
                        'New enable_services: %s. '
                        'New disable_services: %s.',
                        ServiceManager._enable_services,
                        ServiceManager._disable_services,
                        enable_services, disable_services)
      else:
        logging.debug('Services have already set up, do nothing with extra '
                      'SetupServices(). '
                      'service_setup_count: %d', service_setup_count)
      return

    if set(enable_services) & set(disable_services):
      logging.warning('Trying to setup intersecting service lists. '
                      'Do nothing. New enable_services: %s. '
                      'New disable_services: %s.',
                      enable_services, disable_services)
      return

    ServiceManager._enable_services = []
    ServiceManager._disable_services = []

    for status, services in (
        (Status.START, enable_services),
        (Status.STOP, disable_services)):
      for service in services:
        try:
          original_status = GetServiceStatus(service, dut=self.dut)
          if original_status != status:
            ServiceManager._original_status_map[service] = original_status
            SetServiceStatus(service, status, self.dut)
        except Exception:
          # Reach here probably because disable or enable some non-existing
          # services. Do not add this service to the restore list.
          logging.exception('Unable to set service status of %s.', service)
        else:
          if status == Status.START:
            ServiceManager._enable_services.append(service)
          else:
            ServiceManager._disable_services.append(service)


  @sync_utils.Synchronized
  def RestoreServices(self):
    """Restores the services affected in SetupServices back to their original
    states."""
    service_setup_count = self._GetServiceSetupCount()

    if service_setup_count < 1:
      # There should be at least 1 setup before calling restore. May happen
      # if RestoreServices() is called in wrong way.
      logging.error('There is no corresponding SetupServices() called before '
                    'RestoreServices().')
      return

    self._SetServiceSetupCount(service_setup_count - 1)

    if service_setup_count > 1:
      logging.debug('Services are still being used by other tests. Waiting for '
                    'the last RestoreServices(). '
                    'service_setup_count: %d', service_setup_count)
      return

    # Restore services if there's only 1 setup record left, which means this
    # should be the last restore request.
    for service, status in ServiceManager._original_status_map.items():
      SetServiceStatus(service, status, self.dut)
    ServiceManager._original_status_map.clear()
    ServiceManager._enable_services = []
    ServiceManager._disable_services = []
