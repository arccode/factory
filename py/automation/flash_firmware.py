#!/usr/bin/env python
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import atexit
import logging
import optparse
import socket
import subprocess
import sys
import time


BOARD_CONFIG = {'link': {'vref': 'pp3300'}}
SERVO_PORT = 9999
SSH_PORT = 22


def Retry(timeout=0, delay=1):
  def WrapRetry(f):
    def DoRetry(*args, **kwargs):
      mtimeout, mdelay = timeout, delay
      while mtimeout >= mdelay:
        start_time = time.time()
        rv = f(*args, **kwargs)
        if rv:
          return rv
        used_time = time.time() - start_time
        if used_time < mdelay:
          time.sleep(mdelay - used_time)
          mtimeout -= mdelay
        else:
          mtimeout -= used_time
        logging.info('%s failed, timeout = %g, delay = %g',
                     f.__name__, mtimeout, mdelay)
      return f(*args, **kwargs)  # last chance
    return DoRetry
  return WrapRetry


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
    ErrorExit('Run command "%s" failed' % cmd)


@Retry(10)
def WaitProcessDie(pat):
  return Call('pgrep -f -l %s' % pat) != 0


def KillProcess(pat):
  Call('sudo pkill -f %s' % pat)
  if not WaitProcessDie(pat):
    ErrorExit('Kill process "%s" failed' % pat)


def ResetServoPort():
  global SERVO_PORT
  sock = socket.socket()
  sock.bind(('', 0))
  SERVO_PORT = sock.getsockname()[1]


def DUTControl(key, val):
  CheckCall('[ `dut-control --port {port} {key}:{val} {key}` == "{key}:{val}" ]'
            .format(port=SERVO_PORT, key=key, val=val))


@Retry(10)
def WaitServodUp(p):
  if p.poll() and p.returncode != 0:
    ErrorExit('Start servod failed (return code = %d)' % p.returncode)
  return Call('dut-control --port %d >/dev/null 2>&1' % SERVO_PORT) == 0


def StartServod(servo_serial):
  KillProcess('servod.*' + servo_serial)
  cmd = 'sudo servod --port %d' % SERVO_PORT
  if servo_serial:
    cmd += ' --serial %s' % servo_serial
  p = subprocess.Popen(cmd, shell=True)
  if not WaitServodUp(p):
    ErrorExit('Start servod failed (can not run dut-control)')
  atexit.register(KillProcess, 'servod.*' + servo_serial)


def FlashFirmware(board, firmware, servo_serial):
  DUTControl('cold_reset', 'on')
  DUTControl('spi2_vref', BOARD_CONFIG[board]['vref'])
  DUTControl('spi2_buf_en', 'on')
  DUTControl('spi2_buf_on_flex_en', 'on')
  DUTControl('spi_hold', 'off')
  cmd = 'sudo flashrom --ignore-lock -w %s' % firmware
  cmd += ' -p ft2232_spi:type=servo-v2'
  if servo_serial:
    cmd += ',serial=%s' % servo_serial
  if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
    cmd += ' -V'
  CheckCall(cmd)
  DUTControl('spi2_vref', 'off')
  DUTControl('spi2_buf_en', 'off')
  DUTControl('spi2_buf_on_flex_en', 'off')


def WaitPingUp(remote, timeout, delay):
  @Retry(timeout, delay)
  def _WaitPingUp():
    return Call('ping -c 1 %s >/dev/null 2>&1' % remote) == 0
  return _WaitPingUp()


def WaitSSHUp(remote, timeout, delay):
  @Retry(timeout, delay)
  def _WaitSSHUp():
    try:
      socket.create_connection((remote, SSH_PORT), timeout=delay)
      return True
    except socket.error:
      return False
  return _WaitSSHUp()


def CheckBoot(remote, ping_timeout, ping_delay, ssh_timeout, ssh_delay):
  DUTControl('cold_reset', 'on')
  DUTControl('cold_reset', 'off')
  if not WaitPingUp(remote, ping_timeout, ping_delay):
    ErrorExit('Boot Failed (ping)')
  if not WaitSSHUp(remote, ssh_timeout, ssh_delay):
    ErrorExit('Boot Failed (ssh)')


def ParseOptions():
  parser = optparse.OptionParser()
  parser.add_option('--board', help='')
  parser.add_option('--remote', help='Address of DUT.')
  parser.add_option('--firmware', help='/path/to/firmware.bin')
  parser.add_option('--servo_serial', default='', help='USB serial of servo.')
  parser.add_option('--ssh_timeout', default=600, type=float,
                    help='Wait SSH timeout in second. (default: %default)')
  parser.add_option('--ssh_delay', default=30, type=float,
                    help='Wait SSH delay in second. (default: %default)')
  parser.add_option('--ping_timeout', default=60, type=float,
                    help='Wait ping timeout in second. (default: %default)')
  parser.add_option('--ping_delay', default=10, type=float,
                    help='Wait ping delay in second. (default: %default)')
  parser.add_option('--no_flash_firmware', dest='do_flash_firmware',
                    default=True, action='store_false', help='')
  parser.add_option('--color', action='store_true', default=False, help='')
  parser.add_option('--debug', action='store_true', default=False, help='')
  options = parser.parse_args()[0]
  log_format = '%(asctime)s - %(levelname)s - %(funcName)s: %(message)s'
  if options.color:
    log_format = '\033[1;33m' + log_format + '\033[0m'
  if options.debug:
    logging.basicConfig(level=logging.DEBUG, format=log_format)
  else:
    logging.basicConfig(level=logging.INFO, format=log_format)
  miss_opts = [opt for opt, val in options.__dict__.iteritems() if val == None]
  if miss_opts:
    ErrorExit('Missing argument(s): ' + ', '.join(miss_opts))
  if not options.board in BOARD_CONFIG:
    ErrorExit('Unsupported board: %s' % options.board)
  return options


def main():
  options = ParseOptions()
  ResetServoPort()
  StartServod(options.servo_serial)
  if options.do_flash_firmware:
    FlashFirmware(options.board, options.firmware, options.servo_serial)
  CheckBoot(options.remote, options.ping_timeout, options.ping_delay,
            options.ssh_timeout, options.ssh_delay)
  logging.info('===== FINISH =====')

if __name__ == '__main__':
  main()
