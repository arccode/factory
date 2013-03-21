#!/usr/bin/env python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import glob
import logging
import optparse
import os
import shutil
import socket
import tempfile
import time

import factory_common  # pylint: disable=W0611
from cros.factory.automation.servo import Servo
from cros.factory.test import utils
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess


SRCROOT = os.environ['CROS_WORKON_SRCROOT']
SUPPORTED_INSTALL_METHODS = ('netboot', 'install_shim', 'usbimg')
FILE_CACHE_DIR = '/tmp/factory_file_cache'


class InvalidArgumentError(Exception):
  '''Failure of passing invalid arguments.'''
  pass


class FinalizeError(Exception):
  '''Failure of running finalize on DUT.'''
  pass


class ExtractFileError(Exception):
  '''Failure of extracting compressed file.'''
  pass


class DUTBootupError(Exception):
  '''Failure of booting up DUT.'''
  pass


class GSUtil(object):
  '''Object that wraps gsutil and make it easier to download latest build from
  Google Storage.'''

  def __init__(self, board, channel):
    self.board = board.replace('_', '-')
    self.channel = channel

  def GetLatestBuildDir(self, branch=''):
    uri = 'gs://chromeos-releases/%s-channel/%s/' % (self.channel, self.board)
    cmd = ['gsutil', 'ls', uri]
    if branch:
      cmd += ['|', 'grep', uri + branch]
    cmd += ['|', 'sort', '-V', '|', 'tail', '-n', '1']
    return Spawn(' '.join(cmd), log=True, check_call=True, read_stdout=True,
                 shell=True).stdout_data.strip()

  def GetBinaryURI(self, gs_dir, filetype, key='', tag=''):
    fileext = {'factory': 'zip',
               'firmware': 'tar.bz2',
               'recovery': 'zip'}
    if key:
      filespec = 'chromeos_*_%s_%s*%s_%s-channel_%s.bin' % (
          self.board, filetype, tag, self.channel, key)
    else:
      filespec = 'ChromeOS-%s-*-%s.%s' % (filetype, self.board,
                                          fileext[filetype])
    return Spawn(['gsutil', 'ls', gs_dir + filespec], log=True, check_call=True,
                 read_stdout=True).stdout_data.strip()

  @staticmethod
  def DownloadURI(uri, local_dir, force_download=False):
    local_file = os.path.join(local_dir, uri.rpartition('/')[2])
    if not force_download and os.path.isfile(local_file):
      # TODO(chinyue): Add md5sum checking to see if force download needed.
      logging.debug('Already downloaded %s', local_file)
    else:
      logging.debug('Downloading %s to %s', uri, local_dir)
      Spawn(['gsutil', 'cp', '-q', uri, local_dir], log=True, check_call=True)
    return local_file


def ExtractFile(compressed_file, output_dir):
  '''Extracts compressed file to output folder.'''

  utils.TryMakeDirs(output_dir)
  logging.debug('Extracting %s to %s', compressed_file, output_dir)
  if compressed_file.endswith('.zip'):
    cmd = ['unzip', compressed_file, '-d', output_dir]
  elif (compressed_file.endswith('.tar.bz2') or
        compressed_file.endswith('.tbz2')):
    cmd = ['tar', '-xjf', compressed_file, '-C', output_dir]
  elif (compressed_file.endswith('.tar.gz') or
        compressed_file.endswith('.tgz')):
    cmd = ['tar', '-xzf', compressed_file, '-C', output_dir]
  else:
    raise ExtractFileError('Unsupported compressed file: %s' % compressed_file)

  return Spawn(cmd, log=True, check_call=True)


def SetupNetboot(board, bundle_dir, recovery_image,
                 dhcp_iface, host_ip, dut_mac, dut_ip,
                 firmware_updater='', hwid_updater='',
                 install_method='netboot'):
  script = os.path.join(SRCROOT,
                        'src/platform/factory/py/automation/setup_netboot.py')
  factory = os.path.join(bundle_dir, 'factory_test',
                         'chromiumos_factory_image.bin')
  miniomaha_dir = os.path.join(bundle_dir, 'factory_setup')
  if not hwid_updater:
    hwid_updater = os.path.join(bundle_dir, 'hwid',
                                'hwid_bundle_%s_all.sh' % board.upper())
  subnet = host_ip.rsplit('.', 1)[0] + '.0'
  cmd = [script,
         '--board=%s' % board,
         '--factory=%s' % factory,
         '--release=%s' % recovery_image,
         '--miniomaha_dir=%s' % miniomaha_dir,
         '--hwid_updater=%s' % hwid_updater,
         '--host=%s' % host_ip,
         '--dhcp_iface=%s' % dhcp_iface,
         '--dhcp_subnet=%s' % subnet,
         '--dut_mac=%s' % dut_mac,
         '--dut_address=%s' % dut_ip,
         ]
  if firmware_updater:
    cmd.append('--firmware_updater=%s' % firmware_updater)
  if install_method == 'netboot':
    netboot_dir = os.path.join(bundle_dir, 'factory_shim', 'netboot')
    vmlinux = os.path.join(netboot_dir, 'vmlinux.uimg')
    cmd.append('--vmlinux=%s' % vmlinux)
    initrd = os.path.join(netboot_dir, 'initrd.uimg')
    if os.path.exists(initrd):
      cmd.append('--initrd=%s' % initrd)
    else:
      cmd.append('--no_modify_netboot_ip')
  elif install_method in ('install_shim', 'usbimg'):
    cmd.append('--no_modify_netboot_ip')
    cmd.append('--no_generate_image')
    cmd.append('--no_tftp')
    if install_method == 'usbimg':
      cmd.append('--no_clone_miniomaha')
      cmd.append('--no_make_factory_package')
      cmd.append('--no_miniomaha')
  return Spawn(cmd, log=True, sudo=True)


def UpdateFirmwareVars(bundle_dir, netboot_bios, host_ip):
  omaha_url = 'http://%s:8080/update' % host_ip
  script = os.path.join(bundle_dir, 'factory_setup', 'update_firmware_vars.py')
  return Spawn([script, '--force',
                '--input', netboot_bios,
                '--tftpserverip', host_ip,
                '--omahaserver', omaha_url],
               log=True, check_call=True, sudo=True)


def UpdateServerAddress(lsb_factory, host_ip):
  Spawn(['sed', '-i', 's|//.*:|//%s:|' % host_ip, lsb_factory],
        log=True, check_call=True, sudo=True)


def MakeFactoryPackage(board, bundle_dir, recovery_image, install_shim='',
                       firmware_updater='', hwid_updater='', **kwargs):
  script = os.path.join(bundle_dir, 'factory_setup', 'make_factory_package.sh')
  factory_image = os.path.join(bundle_dir, 'factory_test',
                               'chromiumos_factory_image.bin')
  if not hwid_updater:
    hwid_updater = os.path.join(bundle_dir, 'hwid',
                                'hwid_bundle_%s_all.sh' % board.upper())
  cmd = [script,
         '--board=%s' % board,
         '--factory=%s' % factory_image,
         '--release=%s' % recovery_image,
         '--hwid_updater=%s' % hwid_updater,
         ]
  if install_shim:
    cmd.append('--install_shim=%s' % install_shim)
  if firmware_updater:
    cmd.append('--firmware_updater=%s' % firmware_updater)
  cmd.extend(['--%s=%s' % (key, value) for key, value in kwargs.items()])
  return Spawn(cmd, log=True, check_call=True)


def WaitDUTBootup(install_method, dut_ip, ping_timeout=120, ssh_timeout=600):
  if install_method in ('netboot', 'install_shim'):
    logging.debug('Ping DUT...')
    start_time = time.time()
    while ping_timeout:
      if Spawn(['ping', '-c', '1', '-W', '1', dut_ip],
               log=False, call=True, ignore_stdout=True).returncode == 0:
        break
      ping_timeout -= 1
    else:
      raise DUTBootupError('Unable to ping %s' % dut_ip)
    logging.debug("DUT could be ping'd after %d seconds",
                  time.time() - start_time)

  logging.debug('Connect DUT ssh port...')
  start_time = time.time()
  deadline = start_time + ssh_timeout
  while time.time() < deadline:
    try:
      socket.create_connection((dut_ip, 22)).close()
      break
    except:  # pylint: disable=W0702
      time.sleep(1)
  else:
    raise DUTBootupError('Unable to ssh %s' % dut_ip)
  logging.debug("DUT could be ssh'd after %d seconds", time.time() - start_time)


def FinalizeDUT(shopfloor_dir, host_ip, dut_ip, logdata_dir,
                config='', testlist='', serial_number=''):
  script = os.path.join(
      SRCROOT, 'src/platform/factory/py/automation/automation_remote.py')
  cmd = [script, dut_ip,
         '--shopfloor_dir=%s' % shopfloor_dir,
         '--shopfloor_ip=%s' % host_ip,
         '--shopfloor_port=8082',
         '--logdata_dir=%s' % logdata_dir,
         ]
  if config:
    cmd.append('--config=%s' % config)
  if testlist:
    cmd.append('--testlist=%s' % testlist)
  if serial_number:
    cmd.append('--serial_number=%s' % serial_number)
  return Spawn(cmd, log=True, sudo=True)


def RunFactoryFlow(board, dhcp_iface, host_ip, dut_mac, dut_ip, install_method,
                   factory_channel='', factory_branch='', recovery_channel='',
                   recovery_branch='', recovery_key='', firmware_channel='',
                   firmware_branch='', firmware_key='', firmware_tag='',
                   bundle_dir='', recovery_image='',
                   install_shim='', install_shim_key='',
                   firmware_updater='', hwid_updater='', bios_bin='', ec_bin='',
                   netboot_bios='', finalize=False, automation_config='',
                   testlist='', serial_number='', servo_serial='',
                   servo_config='', servo_usb_dev='', devices_csv=''):
  start_time = time.time()
  utils.TryMakeDirs(FILE_CACHE_DIR)
  work_dir = tempfile.mkdtemp(prefix='build_')
  logging.debug('Work dir: %s', work_dir)

  if factory_channel and not bundle_dir:
    # Download and extract factory bundle.
    gsutil = GSUtil(board, factory_channel)
    build_dir = gsutil.GetLatestBuildDir(branch=factory_branch)
    factory_version = build_dir[:-1].rpartition('/')[2]
    bundle_uri = gsutil.GetBinaryURI(build_dir, 'factory')
    logging.info('Latest factory bundle version %s URI %s',
                 factory_version, bundle_uri)
    bundle_file = GSUtil.DownloadURI(bundle_uri, FILE_CACHE_DIR)
    bundle_dir = os.path.join(work_dir, 'bundle')
    ExtractFile(bundle_file, bundle_dir)
  else:
    # TODO(chinyue): Have a better way to determine factory bundle version.
    factory_version = os.path.basename(bundle_dir)

  if recovery_channel and not recovery_image:
    # Download recovery image.
    gsutil = GSUtil(board, recovery_channel)
    build_dir = gsutil.GetLatestBuildDir(branch=recovery_branch)
    recovery_version = build_dir[:-1].rpartition('/')[2]
    recovery_uri = gsutil.GetBinaryURI(build_dir, 'recovery', key=recovery_key)
    logging.info('Latest recovery image version %s URI %s',
                 recovery_version, recovery_uri)
    recovery_image = GSUtil.DownloadURI(recovery_uri, FILE_CACHE_DIR)
    if not recovery_key:
      # Unsigned recovery image is inside a compressed file, so extract it.
      recovery_dir = os.path.join(work_dir, 'recovery')
      ExtractFile(recovery_image, recovery_dir)
      recovery_image = os.path.join(recovery_dir, 'recovery_image.bin')
  else:
    # TODO(chinyue): Have a better way to determine recovery image version.
    recovery_version = os.path.basename(recovery_image)

  if firmware_channel and not bios_bin:
    # Download firmware.
    gsutil = GSUtil(board, firmware_channel)
    build_dir = gsutil.GetLatestBuildDir(branch=firmware_branch)
    firmware_version = build_dir[:-1].rpartition('/')[2]
    firmware_uri = gsutil.GetBinaryURI(build_dir, 'firmware',
                                       key=firmware_key, tag=firmware_tag)
    logging.info('Latest firmware version %s URI: %s',
                 firmware_version, firmware_uri)
    bios_bin = GSUtil.DownloadURI(firmware_uri, FILE_CACHE_DIR)
  else:
    # TODO(chinyue): Have a better way to determine firmware version.
    firmware_version = os.path.basename(bios_bin)

  if install_method == 'netboot' and not netboot_bios:
    # Download netboot firmware.
    gsutil = GSUtil(board, factory_channel)
    build_dir = gsutil.GetLatestBuildDir(branch=factory_branch)
    firmware_uri = gsutil.GetBinaryURI(build_dir, 'firmware')
    logging.info('Latest firmware from source URI %s', firmware_uri)
    firmware_file = GSUtil.DownloadURI(firmware_uri, FILE_CACHE_DIR)
    firmware_dir = os.path.join(work_dir, 'firmware_from_source')
    ExtractFile(firmware_file, firmware_dir)
    netboot_bios = os.path.join(firmware_dir, 'nv_image-%s.bin' % board)

  if bios_bin or ec_bin:
    # Replace firmware updater with BIOS or EC specified.
    if not firmware_updater:
      Spawn([os.path.join(bundle_dir, 'factory_setup',
                          'extract_firmware_updater.sh'),
             '--image', recovery_image, '--output_dir', work_dir],
            log=True, check_call=True)
      firmware_updater = os.path.join(work_dir, 'chromeos-firmwareupdate')
    updater_dir = os.path.join(work_dir, 'updater')
    utils.TryMakeDirs(updater_dir)
    Spawn([firmware_updater, '--sb_extract', updater_dir],
          log=True, check_call=True)
    if bios_bin:
      logging.info('Using firmware from %s', bios_bin)
      shutil.copyfile(bios_bin, os.path.join(updater_dir, 'bios.bin'))
    if ec_bin:
      logging.info('Using EC from %s', ec_bin)
      shutil.copyfile(ec_bin, os.path.join(updater_dir, 'ec.bin'))
    Spawn([firmware_updater, '--sb_repack', updater_dir],
          log=True, check_call=True)

  if install_method in ('install_shim', 'usbimg'):
    if not install_shim:
      gsutil = GSUtil(board, factory_channel)
      build_dir = gsutil.GetLatestBuildDir(branch=factory_branch)
      install_shim_uri = gsutil.GetBinaryURI(build_dir, 'factory',
                                             key=install_shim_key)
      logging.info('Latest install shim URI %s', install_shim_uri)
      install_shim = GSUtil.DownloadURI(install_shim_uri, FILE_CACHE_DIR)

    # Update IP addresses in copied install shim.
    clone_install_shim = os.path.join(work_dir, 'install_shim.bin')
    shutil.copyfile(install_shim, clone_install_shim)
    mount_dir = os.path.join(work_dir, 'install_shim_1')
    utils.TryMakeDirs(mount_dir)
    Spawn([os.path.join(bundle_dir, 'factory_setup', 'mount_partition.sh'),
           clone_install_shim, '1', mount_dir],
          log=True, check_call=True, sudo=True)
    UpdateServerAddress(os.path.join(mount_dir, 'dev_image/etc/lsb-factory'),
                        host_ip)
    Spawn(['umount', mount_dir], log=True, check_call=True, sudo=True)
    install_shim = clone_install_shim

    if install_method == 'install_shim':
      install_image = install_shim
    elif install_method == 'usbimg':
      logging.debug('Prepare USB image...')
      install_image = os.path.join(work_dir, 'USB.img')
      MakeFactoryPackage(board, bundle_dir, recovery_image, install_shim,
                         firmware_updater, hwid_updater, usbimg=install_image)

  test_setup = '%s %s %s install, factory: %s, recovery: %s' % (
      board, serial_number if finalize else '', install_method,
      factory_version, recovery_version)
  netboot_process = None
  automation_process = None
  try:
    logging.debug('Setting up environment...')
    netboot_process = SetupNetboot(board, bundle_dir, recovery_image,
                                   dhcp_iface, host_ip, dut_mac, dut_ip,
                                   firmware_updater, hwid_updater,
                                   install_method)

    servo = Servo(board=board, servo_serial=servo_serial)
    servo.StartServod(config=servo_config)
    time.sleep(3)
    try:
      servo.ConnectServod()
      servo.HWInit()
      if install_method == 'netboot':
        logging.debug('Updating netboot firmware vars...')
        UpdateFirmwareVars(bundle_dir, netboot_bios, host_ip)
        logging.debug('Flashing netboot firmware to DUT...')
        servo.FlashFirmware(netboot_bios)
        servo.ColdReset()
      elif install_method in ('install_shim', 'usbimg'):
        logging.debug('Boot DUT using image %s', install_image)
        servo.BootDUTFromImage(install_image, servo_usb_dev)
    finally:
      servo.StopServod()

    WaitDUTBootup(install_method, dut_ip)

    if finalize:
      logging.debug('Running GRT tests and finalize DUT...')
      shopfloor_dir = os.path.join(bundle_dir, 'shopfloor')
      logdata_dir = os.path.join(shopfloor_dir, 'log_data')
      utils.TryMakeDirs(logdata_dir)
      log_file = os.path.join(logdata_dir, 'log', 'factory.log')
      logging.debug('Factory log: %s', log_file)
      shopfloor_data_dir = os.path.join(shopfloor_dir, 'shopfloor_data')
      if devices_csv:
        shutil.copyfile(devices_csv,
                        os.path.join(shopfloor_data_dir, 'devices.csv'))
      automation_process = FinalizeDUT(shopfloor_dir, host_ip, dut_ip,
                                       logdata_dir, automation_config, testlist,
                                       serial_number)

      def WaitReport(wait_seconds=300):
        report_spec = os.path.join(shopfloor_data_dir,
                                   time.strftime('logs.%Y%m%d'), 'reports',
                                   '*.tbz2')
        logging.debug('Watching for finalize report at %s', report_spec)
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
          match = glob.glob(report_spec)
          if match:
            return match[0]
          time.sleep(1)
        return None
      report_file = WaitReport()
      if not report_file:
        raise FinalizeError('No report found, DUT finalize failed')
      logging.info('Finalize report: %s', report_file)

      # Wait a few seconds for DUT to send finalize message to shopfloor server.
      time.sleep(5)

    logging.info('Test result: SUCCESS! %s', test_setup)
  except:  # pylint: disable=W0702
    logging.exception('Factory flow testing terminated')
    logging.error('Test result: FAIL! %s', test_setup)
  finally:
    if netboot_process:
      TerminateOrKillProcess(netboot_process)
    if automation_process:
      TerminateOrKillProcess(automation_process)

  logging.debug("Factory testing took %d seconds", time.time() - start_time)


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)

  parser = optparse.OptionParser(usage='''Usage: %prog [options]

  Example usage:

  To verify latest factory branch build with mp signed recovery image, run:

  ./run_factory_flow.py
    --board=link
    --factory_channel=canary
    --factory_branch=3004
    --recovery_channel=beta
    --recovery_key=mp-v2
    --dhcp_iface=eth1
    --dut_mac=10:9a:dd:40:99:4d

  If you have multiple servo boards, pass --servo_serial to specify the
  servo board to use.''')
  parser.add_option('--board', help='Board for which images are built.')
  parser.add_option('--install_method', default='netboot',
                    help='Install method user for factory flow testing. '
                         'One of %s' % str(SUPPORTED_INSTALL_METHODS))
  parser.add_option('--factory_channel',
                    help='Channel from where to download factory bundle.')
  parser.add_option('--factory_branch', default='',
                    help='Factory branch to use.')
  parser.add_option('--recovery_channel',
                    help='Channel from where to download recovery image.')
  parser.add_option('--recovery_branch', default='',
                    help='FSI branch to use.')
  parser.add_option('--recovery_key', default='',
                    help='Key by which recovery image was signed.')
  parser.add_option('--firmware_channel',
                    help='Channel from where to download firmware.')
  parser.add_option('--firmware_branch', default='',
                    help='Firmware branch to use.')
  parser.add_option('--firmware_key', default='',
                    help='Key by which firmware was signed.')
  parser.add_option('--firmware_tag', default='',
                    help='Tag to select which firmware to use.')
  parser.add_option('--bundle_dir', default='',
                    help='Factory bundle that has been extracted.')
  parser.add_option('--recovery_image', default='',
                    help='Recovery image to use.')
  parser.add_option('--install_shim', default='',
                    help='Install shim to use.')
  parser.add_option('--install_shim_key', default='',
                    help='Key by which install shim was signed.')
  parser.add_option('--firmware_updater', default='',
                    help='Firmware updater to use.')
  parser.add_option('--hwid_updater', default='',
                    help='HWID updater to use.')
  parser.add_option('--bios_bin', default='',
                    help='Firmware to use.')
  parser.add_option('--ec_bin', default='',
                    help='EC to use.')
  parser.add_option('--netboot_bios', default='',
                    help='Netboot firmware to use.')
  parser.add_option('--servo_usb_dev', default='',
                    help='Device path for the USB key on Servo.')
  parser.add_option('--devices_csv', default='',
                    help='Custom devices.csv to use in shopfloor server.')
  parser.add_option('--dhcp_iface',
                    help='Network interface to run DHCP server.')
  parser.add_option('--host_ip', default='192.168.1.254',
                    help='Host IP address. (default: %default)')
  parser.add_option('--dut_mac',
                    help='DUT MAC address.')
  parser.add_option('--dut_ip', default='192.168.1.1',
                    help='DUT IP address. (default: %default)')
  parser.add_option('--servo_serial', default='',
                    help='Servo serial number.')
  parser.add_option('--servo_config', default='',
                    help='Servo config file.')
  parser.add_option('--finalize', action='store_true', default=False,
                    help='Finalize DUT after installation.')
  parser.add_option('--automation_config', default='',
                    help='Automation config used to finalize DUT.')
  parser.add_option('--testlist', default='',
                    help='Test list used to finalize DUT.')
  parser.add_option('--serial_number', default='',
                    help='Serial number for DUT.')
  options = parser.parse_args()[0]

  if options.install_method not in SUPPORTED_INSTALL_METHODS:
    raise InvalidArgumentError('Invalid install method specified')

  RunFactoryFlow(
      options.board, options.dhcp_iface, options.host_ip, options.dut_mac,
      options.dut_ip, options.install_method,
      options.factory_channel, options.factory_branch,
      options.recovery_channel, options.recovery_branch, options.recovery_key,
      options.firmware_channel, options.firmware_branch, options.firmware_key,
      options.firmware_tag, options.bundle_dir, options.recovery_image,
      options.install_shim, options.install_shim_key,
      options.firmware_updater, options.hwid_updater,
      options.bios_bin, options.ec_bin, options.netboot_bios,
      options.finalize, options.automation_config, options.testlist,
      options.serial_number, options.servo_serial, options.servo_config,
      options.servo_usb_dev, options.devices_csv)
