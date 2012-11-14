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
import tempfile
import time

import factory_common  # pylint: disable=W0611
from cros.factory.utils.process_utils import Spawn, TerminateOrKillProcess


SRCROOT = os.environ['CROS_WORKON_SRCROOT']


class FinalizeError(Exception):
  '''Failure of running finalize on DUT.'''
  pass


class GSUtil(object):
  '''Object that wraps gsutil and make it easier to download latest build from
  Google Storage.'''

  def __init__(self, board, channel):
    self.board = board
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
  def DownloadURI(uri, local_dir):
    Spawn(['gsutil', 'cp', '-q', uri, local_dir], log=True, check_call=True)
    return os.path.join(local_dir, uri.rpartition('/')[2])


def ExtractFile(compressed_file, output_dir):
  os.mkdir(output_dir)
  if compressed_file.endswith('.zip'):
    return Spawn(['unzip', compressed_file, '-d', output_dir], log=True,
                 check_call=True)
  elif compressed_file.endswith('.tar.bz2'):
    return Spawn(['tar', '-xjf', compressed_file, '-C', output_dir], log=True,
                 check_call=True)
  else:
    logging.error('Unsupported compressed file type', compressed_file)


def SetupNetboot(board, bundle_dir, recovery_bin,
                 dhcp_iface, host_ip, dut_mac, dut_ip, firmware_updater=''):
  script = os.path.join(SRCROOT,
                        'src/platform/factory/py/automation/setup_netboot.py')
  factory = os.path.join(bundle_dir, 'factory_test',
                         'chromiumos_factory_image.bin')
  miniomaha_dir = os.path.join(bundle_dir, 'factory_setup')
  netboot_dir = os.path.join(bundle_dir, 'factory_shim', 'netboot')
  vmlinux = os.path.join(netboot_dir, 'vmlinux.uimg')
  initrd = os.path.join(netboot_dir, 'initrd.uimg')
  hwid_updater = os.path.join(bundle_dir, 'hwid',
                              'hwid_bundle_%s_all.sh' % board.upper())
  cmd = [script,
         '--board=%s' % board,
         '--factory=%s' % factory,
         '--release=%s' % recovery_bin,
         '--miniomaha_dir=%s' % miniomaha_dir,
         '--vmlinux=%s' % vmlinux,
         '--initrd=%s' % initrd,
         '--hwid_updater=%s' % hwid_updater,
         '--host=%s' % host_ip,
         '--dhcp_iface=%s' % dhcp_iface,
         '--dut_mac=%s' % dut_mac,
         '--dut_address=%s' % dut_ip,
         ]
  if firmware_updater:
    cmd.append('--firmware_updater=%s' % firmware_updater)
  return Spawn(cmd, log=True, sudo=True)


def FlashFirmware(board, firmware, dut_ip, servo_serial=''):
  script = os.path.join(SRCROOT,
                        'src/platform/factory/py/automation/flash_firmware.py')
  cmd = [script,
         '--board=%s' % board,
         '--firmware=%s' % firmware,
         '--remote=%s' % dut_ip,
         ]
  if servo_serial:
    cmd.append('--servo_serial=%s' % servo_serial)
  return Spawn(cmd, log=True, check_call=True, sudo=True)


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


def RunFactoryFlow(board, factory_channel, recovery_channel,
                   dhcp_iface, host_ip, dut_mac, dut_ip,
                   factory_branch='', recovery_branch='', recovery_key='',
                   bios_channel='', bios_branch='', bios_key='', bios_tag='',
                   firmware_updater='', bios_file='', ec_file='',
                   servo_serial='', finalize=False,
                   config='', testlist='', serial_number=''):
  gsutil = GSUtil(board, factory_channel)
  build_dir = gsutil.GetLatestBuildDir(branch=factory_branch)
  factory_version = build_dir[:-1].rpartition('/')[2]
  logging.info('Latest factory build: %s', factory_version)
  bundle_uri = gsutil.GetBinaryURI(build_dir, 'factory')
  logging.debug('Factory bundle URI: %s', bundle_uri)
  firmware_uri = gsutil.GetBinaryURI(build_dir, 'firmware')
  logging.debug('Firmware from source URI: %s', firmware_uri)

  gsutil = GSUtil(board, recovery_channel)
  build_dir = gsutil.GetLatestBuildDir(branch=recovery_branch)
  recovery_version = build_dir[:-1].rpartition('/')[2]
  logging.info('Latest recovery build: %s', recovery_version)
  recovery_uri = gsutil.GetBinaryURI(build_dir, 'recovery', key=recovery_key)
  logging.debug('recovery URI: %s', recovery_uri)

  if bios_channel and not bios_file:
    gsutil = GSUtil(board, bios_channel)
    build_dir = gsutil.GetLatestBuildDir(branch=bios_branch)
    bios_version = build_dir[:-1].rpartition('/')[2]
    logging.info('Latest bios build: %s', bios_version)
    bios_uri = gsutil.GetBinaryURI(build_dir, 'firmware',
                                   key=bios_key, tag=bios_tag)
    logging.debug('bios URI: %s', bios_uri)

  work_dir = tempfile.mkdtemp(prefix='build_%s_' % factory_version)
  logging.debug('Downloading files to %s', work_dir)
  bundle_file = GSUtil.DownloadURI(bundle_uri, work_dir)
  firmware_file = GSUtil.DownloadURI(firmware_uri, work_dir)
  recovery_file = GSUtil.DownloadURI(recovery_uri, work_dir)
  if bios_channel and not bios_file:
    bios_file = GSUtil.DownloadURI(bios_uri, work_dir)

  logging.debug('Extracting files...')
  bundle_dir = os.path.join(work_dir, 'bundle')
  ExtractFile(bundle_file, bundle_dir)
  firmware_dir = os.path.join(work_dir, 'firmware_from_source')
  ExtractFile(firmware_file, firmware_dir)
  if not recovery_key:
    recovery_dir = os.path.join(work_dir, 'recovery')
    ExtractFile(recovery_file, recovery_dir)
    recovery_file = os.path.join(recovery_dir, 'recovery_image.bin')

  if bios_file or ec_file:
    if not firmware_updater:
      Spawn([os.path.join(bundle_dir, 'factory_setup',
                          'extract_firmware_updater.sh'),
             '--image', recovery_file, '--output_dir', work_dir],
            log=True, check_call=True)
      firmware_updater = os.path.join(work_dir, 'chromeos-firmwareupdate')
    updater_dir = os.path.join(work_dir, 'updater')
    os.mkdir(updater_dir)
    Spawn([firmware_updater, '--sb_extract', updater_dir],
          log=True, check_call=True)
    if bios_file:
      logging.info('Using BIOS from %s', bios_file)
      shutil.copyfile(bios_file, os.path.join(updater_dir, 'bios.bin'))
    if ec_file:
      logging.info('Using EC from %s', ec_file)
      shutil.copyfile(ec_file, os.path.join(updater_dir, 'ec.bin'))
    Spawn([firmware_updater, '--sb_repack', updater_dir],
          log=True, check_call=True)

  netboot_process = None
  automation_process = None
  try:
    logging.debug('Setting up netboot environment...')
    netboot_process = SetupNetboot(board, bundle_dir, recovery_file,
                                   dhcp_iface, host_ip, dut_mac, dut_ip,
                                   firmware_updater)

    logging.debug('Flashing firmware to DUT...')
    netboot_bios = os.path.join(firmware_dir, 'nv_image-%s.bin' % board)
    FlashFirmware(board, netboot_bios, dut_ip, servo_serial=servo_serial)

    if finalize:
      logging.debug('Running GRT tests and finalize DUT...')
      shopfloor_dir = os.path.join(bundle_dir, 'shopfloor')
      logdata_dir = os.path.join(shopfloor_dir, 'log_data')
      os.mkdir(logdata_dir)
      log_file = os.path.join(logdata_dir, 'factory', 'log', 'factory.log')
      logging.debug('Factory log: %s', log_file)
      automation_process = FinalizeDUT(shopfloor_dir, host_ip, dut_ip,
                                       logdata_dir, config, testlist,
                                       serial_number)

      def WaitReport(wait_seconds=300):
        report_spec = os.path.join(shopfloor_dir, 'shopfloor_data', 'reports',
                                   '*.tbz2')
        logging.debug('Watching for finalize report at %s', report_spec)
        start = time.time()
        while time.time() - start < wait_seconds:
          match = glob.glob(report_spec)
          if match:
            return match[0]
          time.sleep(5)
        return None
      report_file = WaitReport()
      if not report_file:
        logging.info('No report found, DUT finalize failed.')
        raise FinalizeError
      logging.info('Finalize report: %s', report_file)

    logging.info('Test result: SUCCESS! %s %s factory %s recovery %s',
                 board, serial_number, factory_version, recovery_version)
  except:  # pylint: disable=W0702
    logging.error('Test result: FAIL! %s %s factory %s recovery %s',
                  board, serial_number, factory_version, recovery_version)
  finally:
    if netboot_process:
      TerminateOrKillProcess(netboot_process)
    if automation_process:
      TerminateOrKillProcess(automation_process)


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
  parser.add_option('--bios_channel',
                    help='Channel from where to download BIOS image.')
  parser.add_option('--bios_branch', default='',
                    help='BIOS branch to use.')
  parser.add_option('--bios_key', default='',
                    help='Key by which BIOS image was signed.')
  parser.add_option('--bios_tag', default='',
                    help='Tag to select which BIOS image to use.')
  parser.add_option('--firmware_updater', default='',
                    help='Firmware updater to use.')
  parser.add_option('--bios_file', default='',
                    help='Local BIOS image to use.')
  parser.add_option('--ec_file', default='',
                    help='Local EC image to use.')
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
  parser.add_option('--finalize', action='store_true', default=False,
                    help='Finalize DUT after installation.')
  parser.add_option('--config', default='',
                    help='Automation config used to finalize DUT.')
  parser.add_option('--testlist', default='',
                    help='Test list used to finalize DUT.')
  parser.add_option('--serial_number', default='',
                    help='Serial number for DUT.')
  options = parser.parse_args()[0]

  RunFactoryFlow(options.board,
                 options.factory_channel, options.recovery_channel,
                 options.dhcp_iface, options.host_ip,
                 options.dut_mac, options.dut_ip,
                 options.factory_branch, options.recovery_branch,
                 options.recovery_key, options.bios_channel,
                 options.bios_branch, options.bios_key, options.bios_tag,
                 options.firmware_updater, options.bios_file, options.ec_file,
                 options.servo_serial, options.finalize,
                 options.config, options.testlist, options.serial_number)
