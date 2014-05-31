#!/usr/bin/python -Bu
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Factory flow command-line interface."""

import logging

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow import run_automated_tests
from cros.factory.factory_flow import create_bundle
from cros.factory.factory_flow import netboot_install
from cros.factory.factory_flow import modify_bundle
from cros.factory.factory_flow import run_host_command
from cros.factory.factory_flow import start_server
from cros.factory.factory_flow import usb_install
from cros.factory.hacked_argparse import (Command, ParseCmdline,
                                          verbosity_cmd_arg)


# Set default verbosity to INFO.
verbosity_cmd_arg[1]['default'] = logging.INFO
_COMMON_ARGS = [
    verbosity_cmd_arg,
]


# pylint: disable=C0322
@Command('run-automated-tests', *run_automated_tests.RunAutomatedTests.args,
         doc=run_automated_tests.RunAutomatedTests.__doc__)
def RunAutomatedTests(options):
  """Runs automated factory tests on a given DUT."""
  run_automated_tests.RunAutomatedTests().Main(options)


@Command('create-bundle', *create_bundle.CreateBundle.args,
         doc=create_bundle.CreateBundle.__doc__)
def CreateBundle(options):
  """Creates a factory bundle for testing."""
  create_bundle.CreateBundle().Main(options)


@Command('start-server', *start_server.StartServer.args,
         doc=start_server.StartServer.__doc__)
def StartServer(options):
  """Starts factory server to run factory flow."""
  start_server.StartServer().Main(options)


@Command('modify-bundle', *modify_bundle.ModifyBundle.args,
         doc=modify_bundle.ModifyBundle.__doc__)
def ModifyBundle(options):
  """Modifies settings of an existing factory bundle."""
  modify_bundle.ModifyBundle().Main(options)


@Command('netboot-install', *netboot_install.NetbootInstall.args,
         doc=netboot_install.NetbootInstall.__doc__)
def NetbootInstall(options):
  """Runs factory install on a given DUT with netboot flow."""
  netboot_install.NetbootInstall().Main(options)


@Command('usb-install', *usb_install.USBInstall.args,
         doc=usb_install.USBInstall.__doc__)
def USBInstall(options):
  """Runs factory install on a given DUT with a USB disk on a servo."""
  usb_install.USBInstall().Main(options)


@Command('run-host-command', *run_host_command.RunHostCommand.args,
         doc=run_host_command.RunHostCommand.__doc__)
def RunHostCommand(options):
  """Runs the given command on the host."""
  run_host_command.RunHostCommand().Main(options)


# TODO(jcliang): Add disk-image-install subcommand, which creates a disk image
#                using make_factory_package, and dd the disk image through SSH
#                onto DUT. For example:
#                `pv disk_image.bin | gzip -2 | ssh <dut ip> "gzip -d - | \
#                 dd of=/dev/mmcblk0 bs=8M iflag=fullblock oflag=dsync"`


def main():
  options = ParseCmdline('Factory flow command-line interface.', *_COMMON_ARGS)
  assert not logging.getLogger().handlers, (
      'Logging has already been initialized')
  logging.basicConfig(
      format=('[%(levelname)s] factory_flow ' +
              '%(filename)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=options.verbosity, datefmt='%Y-%m-%d %H:%M:%S')
  options.command(options)


if __name__ == '__main__':
  main()
