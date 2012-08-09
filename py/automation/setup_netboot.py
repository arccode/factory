#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import optparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time


def ErrorExit(msg):
  logging.error(msg)
  sys.exit(1)


def Call(cmd):
  logging.info(cmd)
  return subprocess.call(cmd, shell=True)


def CheckCall(cmd):
  logging.info(cmd)
  # Do not use subprocess.check_call, which shows annoying stacktrace.
  if subprocess.call(cmd, shell=True) != 0:
    ErrorExit('Run command "%s" failed.' % cmd)


def KillProcess(pat, timeout=5):
  Call('pgrep -f -l %s' % pat)
  killed = False
  Call('sudo pkill -f %s' % pat)
  while timeout > 0 and not killed:
    if Call('pgrep -f -l %s' % pat) != 0:
      killed = True
      break
    timeout -= 1
    time.sleep(1)
  if not killed and Call('pgrep -f -l %s' % pat) == 0:
    ErrorExit('Kill process "%s" failed.' % pat)


def CheckPackagesInstalled():
  pkgs = ['uboot-mkimage', 'python-cherrypy3',
          'pigz', 'tftpd-hpa', 'dhcp3-server']
  for pkg in pkgs:
    if Call('dpkg --get-selections | grep %s' % pkg) != 0:
      msg = 'Please install the package "%s".' % pkg
      if pkg in ['tftpd-hpa', 'dhcp3-server']:
        msg += '\nDo not forget to set configuration correctly.'
      ErrorExit(msg)


def RunService(name):
  status = subprocess.Popen('service %s status' % name, shell=True,
                            stdout=subprocess.PIPE).communicate()[0]
  STOP_PATTERNS = ['stop/waiting', 'is not running']
  if all(re.search(pat, status) == None for pat in STOP_PATTERNS):
    Call('sudo service %s stop' % name)
  CheckCall('sudo service %s start' % name)


def ModifyNetbootIP(host, initrd):
  """Modify the server addresses in lsb-factory to our host (192.168.123.1)
  Before:
    CHROMEOS_AUSERVER=http://build51-m2.golo.chromium.org:8080/update
    CHROMEOS_DEVSERVER=http://build51-m2.golo.chromium.org:8080/update
  After:
    CHROMEOS_AUSERVER=http://192.168.123.1:8080/update
    CHROMEOS_DEVSERVER=http://192.168.123.1:8080/update
  """
  header = subprocess.Popen('mkimage -l %s' % initrd, shell=True,
                            stdout=subprocess.PIPE).communicate()[0]
  load_address = re.findall('Load Address:\s*(.*)', header)[0]
  entry_point = re.findall('Entry Point:\s*(.*)', header)[0]
  image_name = re.findall('Image Name:\s*(.*)', header)[0]
  with open(initrd, mode='rb') as f:
    f.seek(64)  # skipping initrd header (64 bytes)
    gzipped_rootfs = f.read()
  with tempfile.NamedTemporaryFile(suffix='_rootfs.gz') as tf:
    tf.write(gzipped_rootfs)
    tf.flush()
    td = tempfile.mkdtemp(suffix='_mnt')
    tr = os.path.splitext(tf.name)[0]
    CheckCall('gunzip -d -f "%s"' % tf.name)
    CheckCall('sudo mount -o loop %s %s' % (tr, td))
    CheckCall("sudo sed -i \"s'//.*:'//%s:'\"" % host +
              " %s/mnt/stateful_partition/dev_image/etc/lsb-factory" % td)
    CheckCall('sudo umount -f %s' % td)
    CheckCall('rmdir %s' % td)
    CheckCall('pigz -9 %s' % tr)
    # TODO(shik): Support building ramdisk for ARM platform.
    CheckCall('mkimage -A x86 -O linux -T ramdisk'
              ' -a %s -e %s -n "%s" -C gzip -d %s %s'
              % (load_address, entry_point, image_name, tf.name, initrd))


def StartTFTPServer(initrd, vmlinux):
  tftp_config = file('/etc/default/tftpd-hpa').read()
  tftp_dir = re.findall('TFTP_DIRECTORY="(.*?)"', tftp_config)[0]
  shutil.copy(initrd, tftp_dir + '/rootImg')
  shutil.copy(vmlinux, tftp_dir + '/uImage')
  mode = stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
  os.chmod(tftp_dir + '/rootImg', mode)
  os.chmod(tftp_dir + '/uImage', mode)
  RunService('tftpd-hpa')


def StartDHCPServer(host):
  dhcp_config = file('/etc/default/dhcp3-server').read()
  dhcp_interface = re.findall('INTERFACES="(.*?)"', dhcp_config)[0]
  if not dhcp_interface:
    ErrorExit('DHCP interface is empty (sudo vim /etc/default/dhcp3-server)')
  CheckCall('sudo ifconfig %s %s' % (dhcp_interface, host))
  RunService('dhcp3-server')


def StartMiniomahaServer(miniomaha_dir, board, release, factory,
                         hwid_updater, firmware_updater):
  KillProcess('miniomaha.py')
  cmd = '%s/make_factory_package.sh' % miniomaha_dir
  cmd += ' --run --board="%s"' % board
  cmd += ' --release="%s" --factory="%s"' % (release, factory)
  cmd += ' --hwid_updater="%s"' % hwid_updater
  if firmware_updater:
    cmd += ' --firmware_updater="%s"' % firmware_updater
  CheckCall(cmd)


def main():
  parser = optparse.OptionParser()
  parser.add_option('--miniomaha_dir', help='/path/to/miniomaha_directory')
  parser.add_option('--board', help='Board for which the image was built.')
  parser.add_option('--release', help='/path/to/release_image.bin')
  parser.add_option('--factory', help='/path/to/factory_image.bin')
  parser.add_option('--hwid_updater', help='/path/to/hwid_updater.sh')
  parser.add_option('--firmware_updater', default='',
                    help='/path/to/firmware_updater')
  parser.add_option('--initrd', help='/path/to/initrd.uimg')
  parser.add_option('--vmlinux', help='/path/to/vmlinux.uimg')
  parser.add_option('--host', default='192.168.123.1',
                    help='Server address. (default: %default)')
  parser.add_option('--color', action='store_true', default=False,
                    help='Show colorful output for logging.')
  parser.add_option('--no_check_packages', dest='do_check_packages',
                    default=True, action='store_false', help='')
  parser.add_option('--no_modify_netboot_ip', dest='do_modify_betboot_ip',
                    default=True, action='store_false', help='')
  parser.add_option('--no_tftp', dest='do_tftp',
                    default=True, action='store_false', help='')
  parser.add_option('--no_dhcp', dest='do_dhcp',
                    default=True, action='store_false', help='')
  parser.add_option('--no_miniomaha', dest='do_miniomaha',
                    default=True, action='store_false', help='')
  options = parser.parse_args()[0]
  log_format = '%(asctime)s - %(levelname)s - %(funcName)s: %(message)s'
  if options.color:
    log_format = '\033[1;33m' + log_format + '\033[0m'
  logging.basicConfig(level=logging.INFO, format=log_format)
  miss_opts = [opt for opt, val in options.__dict__.iteritems() if val == None]
  if miss_opts:
    ErrorExit('Missing argument(s): ' + ', '.join(miss_opts))
  CheckCall('sudo true #caching sudo')
  if options.do_check_packages:
    CheckPackagesInstalled()
  if options.do_modify_betboot_ip:
    ModifyNetbootIP(options.host, options.initrd)
  if options.do_tftp:
    StartTFTPServer(options.initrd, options.vmlinux)
  if options.do_dhcp:
    StartDHCPServer(options.host)
  if options.do_miniomaha:
    StartMiniomahaServer(options.miniomaha_dir, options.board,
                         options.release, options.factory,
                         options.hwid_updater, options.firmware_updater)

if __name__ == '__main__':
  main()
