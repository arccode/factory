#!/usr/bin/python -Bu
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Base classes for running factory flow tests."""


import collections
import copy
import os
import yaml


class InfoParsingError(Exception):
  """Info parsing error."""
  pass


class CommandBuilderError(Exception):
  """Command builder error."""
  pass


class BaseInfo(object):
  """Base class of test info objects."""
  name = None
  fields = {}

  def __init__(self, info_dict):
    self._fields = copy.deepcopy(self.fields)
    for k, v in info_dict.iteritems():
      if k not in self._fields:
        raise InfoParsingError('Invalid %s info field %r' % (self.name, k))
      if self._fields[k] is not None:
        raise InfoParsingError('Re-defining %s info field %r' % (self.name, k))
      self._fields[k] = v

  def __getitem__(self, key):
    if key not in self._fields:
      raise InfoParsingError('Invalid %s info field %r' % (self.name, key))
    return self._fields[key]

  def get(self, key, default=None):
    return self.__getitem__(key) or default

  def __setitem__(self, key, value):
    if key not in self._fields:
      raise InfoParsingError('Invalid %s info field %r' % (self.name, key))
    self._fields[key] = value


class RunnerInfo(BaseInfo):
  """Class to hold test runner info."""
  name = 'runner'
  fields = {
      'board': None,
      'output_dir': None,
      }


class HostInfo(BaseInfo):
  """Class to hold host info."""
  name = 'host'
  fields = {
      'dhcp_iface': None,
      'host_ip': None,
      }


class DUTInfo(BaseInfo):
  """Class to hold DUT info."""
  name = 'DUT'
  fields = {
      'dut_id': None,
      'log_dir': None,
      'eth_mac': None,
      'ip': None,
      'servo_host': None,
      'servo_port': None,
      'servo_serial': None,
      'test_list_customization': None,
      }


CommandArguments = collections.namedtuple('CommandArguments', ['duts', 'args'])


class FactoryFlowCommandBuilder(object):
  """Base class of factory flow subcommand builders."""
  subcommand = None
  module = None
  classname = None
  FACTORY_FLOW = os.path.join(os.environ['CROS_WORKON_SRCROOT'], 'src',
                              'platform', 'factory', 'bin', 'factory_flow')

  def __init__(self):
    assert self.subcommand is not None
    self.class_obj = getattr(
        __import__(
            'cros.factory.factory_flow.%s' % self.module,
            fromlist=[self.classname]),
        self.classname)
    self.valid_args = self.class_obj.args

  def BuildCommand(self, test_item, runner_info, host_info, dut_info_list):
    """Public API for building command from the given info objects.

    Args:
      test_item: A dict of test_item definition.
      runner_info: A RunnerInfo instance.
      host_info: A HostInfo instance.
      dut_info_list: A list of DUTInfo instances.

    Returns:
      A list of CommandArguments listing all the commands to run for each DUT.
    """
    base_args = copy.deepcopy(test_item)
    base_args['board'] = runner_info['board']
    dut_args_list = self.BuildArgs(base_args, runner_info, host_info,
                                  dut_info_list)
    self.VerifyArgs(dut_args_list)
    return self.GenerateCommand(dut_args_list)

  def BuildArgs(self, base_args, runner_info, host_info, dut_info_list):
    """Per-subcommand function to build subcommand arguments for each DUT."""
    raise NotImplementedError

  def VerifyArgs(self, dut_args_list):
    """Verifies that all the arguments are valid.

    Args:
      dut_args_list: A list of CommandArguments instances.

    Raises:
      CommandBuilderError if verification fails.
    """
    arg_names = set()
    for names, _ in self.valid_args:
      arg_names.update(set([x.lstrip('-') for x in names]))
    for dut_args in dut_args_list:
      for name in dut_args.args.iterkeys():
        if name == 'command':
          continue
        if name not in arg_names:
          raise CommandBuilderError(
              'Invalid argument %r of subcommand %s' % (name, self.subcommand))

  def GenerateCommand(self, dut_args_list):
    """Generates the final commands for each DUT.

    Args:
      dut_args_list: A list of CommandArguments instances.

    Returns:
      A list of CommandArguments listing all the commands to run for each DUT.
    """
    result = []
    for dut_args in dut_args_list:
      command = [self.FACTORY_FLOW, self.subcommand]
      for name, value in dut_args.args.iteritems():
        if name == 'command' or value is None:
          continue
        if isinstance(value, bool) and value:
          command += ['--%s' % name]
        else:
          command += ['--%s=%s' % (name, value)]
      result.append(CommandArguments(dut_args.duts, command))
    return result


class CreateBundleCommandBuilder(FactoryFlowCommandBuilder):
  """Subcommand builder for create-bundle."""
  subcommand = 'create-bundle'
  module = 'create_bundle'
  classname = 'CreateBundle'

  def BuildArgs(self, base_args, runner_info, host_info, dut_info_list):
    # Only create one bundle regardless of the number of DUTs to test.
    all_duts = [dut_info['dut_id'] for dut_info in dut_info_list]
    args = copy.deepcopy(base_args)
    args['output-dir'] = runner_info['output_dir']
    args['mini-omaha-ip'] = host_info['host_ip']
    return [CommandArguments(all_duts, args)]


class StartServerCommandBuilder(FactoryFlowCommandBuilder):
  """Subcommand builder for start-server."""
  subcommand = 'start-server'
  module = 'start_server'
  classname = 'StartServer'

  def BuildArgs(self, base_args, runner_info, host_info, dut_info_list):
    for field in ('dhcp_iface', 'host_ip'):
      if not host_info[field]:
        raise CommandBuilderError(
            'Missing mandatory field %r in host info' % field)
    for dut_info in dut_info_list:
      for field in ('eth_mac', 'ip'):
        if not dut_info[field]:
          raise CommandBuilderError(
              'Missing mandatory field %r in DUT info of %s' %
              (field, dut_info['dut_id']))

    result = []
    all_duts = [dut_info['dut_id'] for dut_info in dut_info_list]
    if len(dut_info_list) == 1 or base_args.get('stop'):
      # Just one DUT or shutting down all servers; start/stop all servers in one
      # command.
      dut_info = dut_info_list[0]
      args = copy.deepcopy(base_args)
      args['dhcp-iface'] = host_info['dhcp_iface']
      args['host-ip'] = host_info['host_ip']
      args['dut-mac'] = dut_info['eth_mac']
      args['dut-ip'] = dut_info['ip']
      result.append(CommandArguments(all_duts, args))
    elif len(dut_info_list) > 1:
      # Multiple DUTs; start TFTP server, Download server, and shop floor server
      # in one command.
      args = copy.deepcopy(base_args)
      args['host-ip'] = host_info['host_ip']
      args['no-dhcp'] = True
      result.append(CommandArguments(all_duts, args))

      for dut_info in dut_info_list:
        # And one DHCP server for each DUT
        args = copy.deepcopy(base_args)
        args['dhcp-iface'] = host_info['dhcp_iface']
        args['host-ip'] = host_info['host_ip']
        args['dut-mac'] = dut_info['eth_mac']
        args['dut-ip'] = dut_info['ip']
        args['no-tftp'] = True
        args['no-download'] = True
        args['no-shopfloor'] = True
        result.append(CommandArguments([dut_info['dut_id']], args))
    return result


class NetbootInstallCommandBuilder(FactoryFlowCommandBuilder):
  """Subcommand builder for netboot-install."""
  subcommand = 'netboot-install'
  module = 'netboot_install'
  classname = 'NetbootInstall'

  def BuildArgs(self, base_args, runner_info, host_info, dut_info_list):
    # Run netboot install on all DUTs concurrently.
    result = []
    for dut_info in dut_info_list:
      args = copy.deepcopy(base_args)
      args['dut'] = dut_info['ip']
      args['servo-host'] = dut_info['servo_host']
      args['servo-port'] = dut_info['servo_port']
      args['servo-serial'] = dut_info['servo_serial']
      result.append(CommandArguments([dut_info['dut_id']], args))
    return result


class USBInstallCommandBuilder(FactoryFlowCommandBuilder):
  """Subcommand builder for usb-install."""
  subcommand = 'usb-install'
  module = 'usb_install'
  classname = 'USBInstall'

  def BuildArgs(self, base_args, runner_info, host_info, dut_info_list):
    # Run USB install on all DUTs concurrently.
    result = []
    for dut_info in dut_info_list:
      args = copy.deepcopy(base_args)
      args['dut'] = dut_info['ip']
      args['servo-host'] = dut_info['servo_host']
      args['servo-port'] = dut_info['servo_port']
      args['servo-serial'] = dut_info['servo_serial']
      result.append(CommandArguments([dut_info['dut_id']], args))
    return result


class RunAutomatedTestsCommandBuilder(FactoryFlowCommandBuilder):
  """Subcommand builder for run-automated-tests."""
  subcommand = 'run-automated-tests'
  module = 'run_automated_tests'
  classname = 'RunAutomatedTests'

  def BuildArgs(self, base_args, runner_info, host_info, dut_info_list):
    # Run automated tests on all DUTs concurrently.
    result = []
    for dut_info in dut_info_list:
      args = copy.deepcopy(base_args)
      args['dut'] = dut_info['ip']
      args['shopfloor-ip'] = host_info['host_ip']

      log_dir = dut_info['log_dir']
      if log_dir:
        args['log-dir'] = os.path.join(log_dir, 'factory_logs')

      if args['test-list'] in dut_info.get('test_list_customization', []):
        # Generate YAML files and set up automation environment on the DUT.
        def CreateTempYAMLFile(suffix, data):
          filename = os.path.join(
              runner_info['output_dir'],
              '%s-%s-%s.yaml' % (dut_info['dut_id'], args['test-list'], suffix))
          with open(filename, 'w') as f:
            f.write(yaml.safe_dump(data))
          return filename

        settings = dut_info['test_list_customization'][args['test-list']]
        for item in ('device_data', 'vpd', 'test_list_dargs',
                     'automation_function_kwargs'):
          data = settings.get(item)
          if data:
            args[item.replace('_', '-') + '-yaml'] = CreateTempYAMLFile(
                item, data)
      result.append(CommandArguments([dut_info['dut_id']], args))
    return result


CommandBuilder = {
    'create-bundle': CreateBundleCommandBuilder(),
    'start-server': StartServerCommandBuilder(),
    'netboot-install': NetbootInstallCommandBuilder(),
    'usb-install': USBInstallCommandBuilder(),
    'run-automated-tests': RunAutomatedTestsCommandBuilder(),
    }
