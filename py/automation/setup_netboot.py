#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import errno
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


def IsProcessAlive(pat):
  rc = Call('pgrep -f -l %s' % pat)
  return rc == 0


def KillProcess(pat, timeout=5):
  Call('pgrep -f -l %s' % pat)
  killed = False
  Call('sudo pkill -f %s' % pat)
  while timeout > 0:
    if not IsProcessAlive(pat):
      killed = True
      break
    timeout -= 1
    time.sleep(1)
  if not killed and IsProcessAlive(pat):
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


def RemoveFile(path):
  try:
    os.remove(path)
  except OSError as e:
    # Ignore the error 'No such file or directory'.
    # Do not use something like 'if not os.path.exists(path): os.remove(path)',
    # because there is a race condition in this statement.
    if e.errno != errno.ENOENT:
      raise


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


def GenerateImage(host, port, script, initrd, vmlinux):
  """Generate the script image which guides the netboot flow
  When netboot starts with command "dhcp", and the script image is set by
  by filename statement in DHCP server configuration, this image will be placed
  in address 0x100000 and executed on DUT by netboot firmware (coreboot.h).
  """
  # Place factory install shim onto TFTP server.
  tftp_config = file('/etc/default/tftpd-hpa').read()
  tftp_dir = re.findall('TFTP_DIRECTORY="(.*?)"', tftp_config)[0]
  td = tempfile.mkdtemp(dir=tftp_dir)
  uImage = os.path.join(td, 'uImage')
  rootImg = os.path.join(td, 'rootImg')
  scriptImg = os.path.join(tftp_dir, script)
  shutil.copy(vmlinux, uImage)
  shutil.copy(initrd, rootImg)
  with tempfile.NamedTemporaryFile(suffix='_scriptImage.scr') as tf:
    # Override Omaha URL by passing argument to kernel command line.
    # For more details about how does this work, see factory_install.sh.
    tf.write("setenv bootargs ${bootargs}"
             " 'omahaserver=http://%s:%d/update'\n" % (host, port))
    # Put kernel image at 0x101000 so as not to overlap with the script image.
    tf.write('tftpboot 0x101000 %s/uImage\n' % os.path.basename(td))
    tf.write('tftpboot 0x12008000 %s/rootImg\n' % os.path.basename(td))
    tf.write('bootm 0x101000 0x12008000\n')
    tf.flush()
    RemoveFile(scriptImg)  # this file may be generated by other user
    CheckCall('mkimage -T script -C none -n "Netboot Script Image"'
              ' -d %s %s' % (tf.name, scriptImg))
  # TFTP server needs universal read permission.
  mode = stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
  os.chmod(uImage, mode)
  os.chmod(rootImg, mode)
  os.chmod(scriptImg, mode)
  os.chmod(td, stat.S_IRWXU | stat.S_IXOTH)


def StartTFTPServer():
  RunService('tftpd-hpa')


def StartDHCPServer(host):
  dhcp_config = file('/etc/default/dhcp3-server').read()
  dhcp_interface = re.findall('INTERFACES="(.*?)"', dhcp_config)[0]
  if not dhcp_interface:
    ErrorExit('DHCP interface is empty (sudo vim /etc/default/dhcp3-server)')
  CheckCall('sudo ifconfig %s %s' % (dhcp_interface, host))
  RunService('dhcp3-server')


def CloneMiniomaha(miniomaha_dir):
  """Use cloned Mini-Omaha server to prevent race condition
  When running multiple Mini-Omaha server instance from same directory
  concurrently, they will use the same "static" folder thus hit race condition.
  """
  clone_dir = os.path.join(tempfile.mkdtemp(suffix='_miniomaha'), 'miniomaha')
  shutil.copytree(miniomaha_dir, clone_dir)
  return clone_dir


def MakeFactoryPackage(miniomaha_dir, board, release, factory,
                       hwid_updater, firmware_updater):
  cmd = os.path.join(miniomaha_dir, 'make_factory_package.sh')
  cmd += ' --board="%s"' % board
  cmd += ' --release="%s" --factory="%s"' % (release, factory)
  cmd += ' --hwid_updater="%s"' % hwid_updater
  if firmware_updater:
    cmd += ' --firmware_updater="%s"' % firmware_updater
  CheckCall(cmd)


def StartMiniomahaServer(miniomaha_dir, port):
  # Do not remove the extension ".py" when killing process,
  # or it may kill itself since when arguments is matching this pattern.
  KillProcess('miniomaha.py.*' + str(port))
  cmd = os.path.join(miniomaha_dir, 'miniomaha.py')
  cmd += ' --port %d' % port
  CheckCall(cmd)


def ParseOptions():
  parser = optparse.OptionParser()
  parser.add_option('--miniomaha_dir', help='/path/to/miniomaha_directory')
  parser.add_option('--board', help='Board for which the image was built.')
  parser.add_option('--release', help='/path/to/release_image.bin')
  parser.add_option('--factory', help='/path/to/factory_image.bin')
  parser.add_option('--hwid_updater', help='/path/to/hwid_updater.sh')
  parser.add_option('--firmware_updater', default='',
                    help='/path/to/firmware_updater')
  parser.add_option('--script', help='Script Image name in DHCP configuration.')
  parser.add_option('--initrd', help='/path/to/initrd.uimg')
  parser.add_option('--vmlinux', help='/path/to/vmlinux.uimg')
  parser.add_option('--host', default='192.168.123.1',
                    help='Server address. (default: %default)')
  parser.add_option('--port', default=8080, type=int,
                    help='Server port. (default: %default)')
  parser.add_option('--color', action='store_true', default=False,
                    help='Show colorful output for logging.')
  parser.add_option('--no_check_packages', dest='do_check_packages',
                    default=True, action='store_false', help='')
  parser.add_option('--do_modify_netboot_ip', dest='do_modify_netboot_ip',
                    default=True, action='store_true', help='')
  parser.add_option('--no_tftp', dest='do_tftp',
                    default=True, action='store_false', help='')
  parser.add_option('--no_dhcp', dest='do_dhcp',
                    default=True, action='store_false', help='')
  parser.add_option('--no_generate_image', dest='do_generate_image',
                    default=True, action='store_false', help='')
  parser.add_option('--no_clone_miniomaha', dest='do_clone_miniomaha',
                    default=True, action='store_false', help='')
  parser.add_option('--no_make_factory_package', dest='do_make_factory_package',
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

  return options


def main():
  options = ParseOptions()
  CheckCall('sudo true #caching sudo')

  if options.do_check_packages:
    CheckPackagesInstalled()

  if options.do_modify_netboot_ip:
    ModifyNetbootIP(options.host, options.initrd)

  if options.do_generate_image:
    GenerateImage(options.host, options.port,
                  options.script, options.initrd, options.vmlinux)

  if options.do_tftp:
    StartTFTPServer()

  if options.do_dhcp:
    StartDHCPServer(options.host)

  if options.do_clone_miniomaha:
    options.miniomaha_dir = CloneMiniomaha(options.miniomaha_dir)

  if options.do_make_factory_package:
    MakeFactoryPackage(options.miniomaha_dir, options.board,
                       options.release, options.factory,
                       options.hwid_updater, options.firmware_updater)

  if options.do_miniomaha:
    StartMiniomahaServer(options.miniomaha_dir, options.port)

if __name__ == '__main__':
  main()
