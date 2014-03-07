# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

""" A test of the Wifi hardware using RF.

The point of saying RF is to differentiate this test from other
tests which talk to the WiFi hardware without actually
transmitting or receiving.

This test has general capabilites and can be used in a
development environment as well as in MP and RMA factorys.
"""

import collections
import errno
import logging
import os
import serial
import subprocess
import threading
import time
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.args import Arg

_TEST_TITLE = test_ui.MakeLabel('RMA Factory WiFi RF Test')

TestRow = collections.namedtuple('TestRow', 'en_label zh_label freq antenna db')
_SUBTESTS = []
_SUBTESTS.append(TestRow(
                 '2.4GHz Antenna 1.', '2.4GHz 天线 1.', '2.4', '1', -65))
_SUBTESTS.append(TestRow(
                 '2.4GHz Antenna 2.', '2.4GHz 天线 2.', '2.4', '2', -62))
_SUBTESTS.append(TestRow(
                 '5.5GHz Antenna 1.', '5.5GHz 天线 1.', '5.5', '1', -68))
_SUBTESTS.append(TestRow(
                 '5.5GHz Antenna 2.', '5.5GHz 天线 2.', '5.5', '2', -57))


_MSG_INSTRUCTION = test_ui.MakeLabel(
   'WiFi RF Chamber Testing.', u'WiFi RF 测试')

_MSG_CHAMBER_REMOVE = test_ui.MakeLabel(
   'Remove device from chamber. Press SPACE when re-attached to network.',
  u'将装置从测试箱取出，重新连接网路后按下空白键')

_MSG_READY_CLOSE = test_ui.MakeLabel(
   'Place device in WiFi chamber. When ready to close chamber, press SPACE.',
  u'将设备放置在WiFi室。当您准备关闭室，按空格键。')

# Here's a command line that can be used to find the USB-serial dongle
#_CMD_FINDTTY = '/usr/bin/find /sys/bus/usb/drivers/pl2303/2-1.2\:1.0/ '\
#       '-type d -name "tty*" | /usr/bin/head -1 | /usr/bin/cut -d / -f8'

# NB: The 192.168.x.x series addresses in these next lines are
# fixed addresses. They are hardcoded into the WAP test device.
# WAP := industry standard term for Wireless Access Point
_CMD_IFCONFIG = '/sbin/ifconfig wlan0 192.168.%c.10'

# 'cooper.sh' is the name of a shell script on the computer
# which hosts the WAP. It's a single line script which runs
# 'tcpdump'. The name has no significance.
_CMD_SSH = '/usr/bin/ssh -i /home/chronos/wifi/testing_rsa '\
           '-o UserKnownHostsFile=/home/chronos/wifi/known_hosts '\
           '192.168.10.1 "/usr/local/sbin/cooper.sh mon%c 192.168.%c.254"'

_CMD_PING = '/bin/ping -q -i 0.1 -s 1000 -c120 192.168.%c.254'

# NB: The two keys contained here are meant to be used with the
# particular WAP device built into the RF Test Chamber at the
# RMA factory. Key for doing ssh access to WAP control computer
_TESTING_RSA = '-----BEGIN RSA PRIVATE KEY-----\n\
MIIEoAIBAAKCAQEAvsNpFdK5lb0GfKx+FgsrsM/2+aZVFYXHMPdvGtTz63ciRhq0\n\
Jnw7nln1SOcHraSz3/imECBg8NHIKV6rA+B9zbf7pZXEv20x5Ul0vrcPqYWC44PT\n\
tgsgvi8s0KZUZN93YlcjZ+Q7BjQ/tuwGSaLWLqJ7hnHALMJ3dbEM9fKBHQBCrG5H\n\
OaWD2gtXj7jp04M/WUnDDdemq/KMg6E9jcrJOiQ39IuTpas4hLQzVkKAKSrpl6MY\n\
2etHyoNarlWhcOwitArEDwf3WgnctwKstI/MTKB5BTpO2WXUNUv4kXzA+g8/l1al\n\
jIG13vtd9A/IV3KFVx/sLkkjuZ7z2rQXyNKuJwIBIwKCAQA79EWZJPh/hI0CnJyn\n\
16AEXp4T8nKDG2p9GpCiCGnq6u2Dvz/u1pZk97N9T+x4Zva0GvJc1vnlST7objW/\n\
Y8/ET8QeGSCT7x5PYDqiVspoemr3DCyYTKPkADKn+cLAngDzBXGHDTcfNP4U6xfr\n\
Qc5JK8BsFR8kApqSs/zCU4eqBtp2FVvPbgUOv3uUrFnjEuGs9rb1QZ0K6o08L4Cq\n\
N+e2nTysjp78blakZfqlurqTY6iJb0ImU2W3T8sV6w5GP1NT7eicXLO3WdIRB15a\n\
evogPeqtMo8GcO62wU/D4UCvq4GNEjvYOvFmPzXHvhTxsiWv5KEACtleBIEYmWHA\n\
POwrAoGBAOKgNRgxHL7r4bOmpLQcYK7xgA49OpikmrebXCQnZ/kZ3QsLVv1QdNMH\n\
Rx/ex7721g8R0oWslM14otZSMITCDCMWTYVBNM1bqYnUeEu5HagFwxjQ2tLuSs8E\n\
SBzEr96JLfhwuBhDH10sQqn+OQG1yj5acs4Pt3L4wlYwMx0vs1BxAoGBANd9Owro\n\
5ONiJXfKNaNY/cJYuLR+bzGeyp8oxToxgmM4UuA4hhDU7peg4sdoKJ4XjB9cKMCz\n\
ZGU5KHKKxNf95/Z7aywiIJEUE/xPRGNP6tngRunevp2QyvZf4pgvACvk1tl9B3HH\n\
7J5tY/GRkT4sQuZYpx3YnbdP5Y6Kx33BF7QXAoGAVCzghVQR/cVT1QNhvz29gs66\n\
iPIrtQnwUtNOHA6i9h+MnbPBOYRIpidGTaqEtKTTKisw79JjJ78X6TR4a9ML0oSg\n\
c1K71z9NmZgPbJU25qMN80ZCph3+h2f9hwc6AjLz0U5wQ4alP909VRVIX7iM8paf\n\
q59wBiHhyD3J16QAxhsCgYBu0rCmhmcV2rQu+kd4lCq7uJmBZZhFZ5tny9MlPgiK\n\
zIJkr1rkFbyIfqCDzyrU9irOTKc+iCUA25Ek9ujkHC4m/aTU3lnkNjYp/OFXpXF3\n\
XWZMY+0Ak5uUpldG85mwLIvATu3ivpbyZCTFYM5afSm4StmaUiU5tA+oZKEcGily\n\
jwKBgBdFLg+kTm877lcybQ04G1kIRMf5vAXcConzBt8ry9J+2iX1ddlu2K2vMroD\n\
1cP/U/EmvoCXSOGuetaI4UNQwE/rGCtkpvNj5y4twVLh5QufSOl49V0Ut0mwjPXw\n\
HfN/2MoO07vQrjgsFylvrw9A79xItABaqKndlmqlwMZWc9Ne\n\
-----END RSA PRIVATE KEY-----\n'

_SSH_KNOWN_HOSTS = 'accesspointwired,192.168.10.1 ssh-rsa \
AAAAB3NzaC1yc2EAAAABIwAAAQEA4EXuGUeYdiKt4P4foYDouAqAnHV+wyLDwLZu1X\
TQDTSeegq1KdNtn2pQrlepFqSjw+oUTUdG0WTp9U51GKBXWn/srnnxtmOgLnaRV7+O\
dxS85RUBiFVL7Z/hdLZ3AhHNUA/HY7G7qZx0GQ65xwKHBWEvqYqWmCD0PyiniZueOD\
954iJj0sAhp+z4OWURO1Wg3LOmL6toUI3sDy/17ORGOrb1YmylARttnVPR/5KXitv5\
gKfKFmI4G7uV3L6G0PfVx57Ex2y8wEu5d8Dmo2CQkTymoY41Zagho0GvyCteuxC9wW\
kK0yAPBZ9yHOAKZbgJNTn3Tylt2w60spSFKW14QQ==\n'


class LEDflasher(threading.Thread):
  """Thread for independently blinking Red and Green LEDs.

  Red LED connected to RTS.
  Green LED connected to DTR.

  Attributes:
    ser: A file descriptor for serial port controlling the LEDs.
    color: The color LED to control.
    duration: Total runtime of on/off sequence.
    on_secs=0.4: LED on time.
    off_secs=0.4: LED off time.
  """

  def __init__(self, ser, color, duration, on_secs=0.4, off_secs=0.4):
    threading.Thread.__init__(self)
    self._ser = ser
    self._color = color
    self._duration = duration
    self._on = on_secs
    self._off = off_secs
    self.pinmap = { 'red':self.SetRedLED, 'green':self.SetGreenLED }
    self._done = threading.Event()

    ser.setRTS(False)
    ser.setDTR(False)

  def SetRedLED(self, state):
    """Sets Red LED.
    Args:
      state: True|False for On|Off.
    """
    self._ser.setRTS(state)

  def SetGreenLED(self, state):
    """Sets Green LED.
    Args:
      state: True|False for On|Off.
    """
    self._ser.setDTR(state)

  def run(self):
    timeout = time.time() + self._duration
    while ((time.time() < timeout) and not self._done.is_set()):
      self.pinmap[self._color](True)
      time.sleep(self._on)
      self.pinmap[self._color](False)
      time.sleep(self._off)

  def Stop(self):
    self._done.set()



class Wifi_RF(unittest.TestCase):
  """Factory test for Wifi.
    Tests both 2.5 and 5.5 GHz bands. Uses modified WAP with attenuated
    antennas that simulate distance from base station. This test qualifies
    the antennas and antenna connections in a Chromebook. Of course, it
    also tests basic Chromebook WiFi functionality.
    Requires operation in a Faraday cage where the captive WAP
    is the only one. If run where other WAPs are seen by the DUT, the
    average signal strength measurements won't be as accurate and
    could fail incorrectly.
  """
  ARGS = [
    Arg('led_serial_port', str,
        'Serial port device for controlling LED Annunciator',
        default= '/dev/ttyUSB4'),
    Arg('delay_network_scan_secs', int,
        'Delay while WiFi looks for WAPs', default= 5),
    Arg('delay_packet_capture_secs', int,
        'Delay while test WAP captures measurment packets', default= 15),
  ]


  def setUp(self):
    self._ui = test_ui.UI()
    self._template = ui_templates.OneSection(self._ui)
    self._ser = 0
    self._fail = False
    self._initflag = True
    self._led_testing = 0
    self._led_flasher = 0


  def mkdir_p(self, path):
    try:
      os.makedirs(path)
    except OSError as exc: # Python >2.5
      if exc.errno == errno.EEXIST and os.path.isdir(path):
        pass
      else: raise


  def TestInit(self):
    """Setup in-chamber test.

    Give operator time to close chamber door after hitting key.
    Connect to LED control serial port.

    Args:
      None.
    """
    # Delay to let operator close RF Chamber door after hitting SPACE key.
    for i in range(5, 0, -1):
      self._template.SetState(test_ui.MakeLabel(
                              'Countdown', '倒计时') + ': %d ' % i)
      time.sleep(1)

    # Have serial port initialization here because the USB-serial dongle
    # isn't attached until this point where the DUT is placed in the
    # RF Chamber and connected.

    # TODO (wmurphy) Find pl2303 automatically. This simple 'find' code
    # doesn't work reliably because it's searching over a 'sys' path.
    #  found = subprocess.Popen(_CMD_FINDTTY, shell=True).communicate()[0]
    #  factory.console.info('find tty: %s\n' % found)
    self._ser = serial.Serial(self.args.led_serial_port, 9600, timeout=1)

    self._ser.setRTS(False)
    self._ser.setDTR(False)

    self._template.SetState('')
    self._led_testing = LEDflasher(self._ser, 'red', 150, on_secs=1.0,
                                   off_secs=0.5)
    self._led_testing.start()


  def TestFinish(self):
    """Indicate in-chamber test is finished.

    Change LED flash pattern to Pass or Fail.
    Give operator a chance to remove DUT from chamber, bring back to a test
    station and re-connect to network.

    Args:
      None.
    """
    self._led_testing.Stop()

    led_color = 'red' if self._fail is True else 'green'
    self._led_flasher = LEDflasher(self._ser, led_color, 3600, on_secs=0.1,
                                   off_secs=0.1)
    self._led_flasher.start()

    # RF Chamber testing is finished. Bring back to test station.

    self._template.SetState(_MSG_CHAMBER_REMOVE)
    self._ui.BindKey(' ', self.TestEnd)


  def TestEnd(self, dummy_event):
    """Test is Done.

    Args:
      None.
    """
    self._led_flasher.Stop()
    if (self._fail == True):
      self._ui.Fail('Problem with WiFi signal testing')
    else:
      self._ui.Pass()
    # Testing Finished.


  def Calc_Signal_Strength(self, db_val_line):
    """Calculate average, Min, Max signal strength.

    Args:
      db_val_line: Text string from Stumpy used to control the testing WAP.
                   A single line of terxst containing a seriesx  of signal
                   strength values separated by space charrascters.
    Returns:
      Named Tuple containing 'min', 'max', and 'avg' db values.
    """
    db_max = -1000
    db_min = 0
    db_avg = 0
    run_avg = 0
    run_avg_cnt = 0
    for dbt in db_val_line.split():
      db = int(dbt)
      run_avg += db
      run_avg_cnt += 1
      if db > db_max:
        db_max = db
      if db < db_min:
        db_min = db
    if run_avg_cnt == 0:
      run_avg = 0
    else:
      db_avg = run_avg / run_avg_cnt

    results = collections.namedtuple('db_Results', 'min max avg')
    results.min = db_min
    results.max = db_max
    results.avg = db_avg
    return results


  def RunSubtests(self, dummy_event):
    """Iterate to next test.

    Args:
      dummy_event: ignored.
    """
    for test in _SUBTESTS:
      self.Subtest(test)

    self.TestFinish()


  def Subtest(self, test):
    """Basic test sequence for one band and one antenna.

      Args:
        test: List of subtests. Expected to be one for each band and one for
          each antenna.
    """
    # Start of WiFi test sequence
    if (self._initflag == True):
      self.TestInit()
      self._initflag = False

    factory.console.info('%sGHz. Antenna %s.' % (test.freq, test.antenna))

    subprocess.call(['/sbin/ifconfig', 'wlan0', 'down'])

    # A dynamic file path. Don't keep it open longterm.
    with open("/sys/kernel/debug/ieee80211/phy0/ath9k/tx_chainmask", "wb") as f:
      subprocess.call(['/bin/echo', '%s' % test.antenna], stdout=f)

    subprocess.call(['/sbin/ifconfig', 'wlan0', 'up'])
    subprocess.call(['/usr/sbin/iw', 'wlan0', 'scan'])

    factory.console.info('%sGHz. Antenna %s. Scanning for networks.' %
                         (test.freq, test.antenna))
    time.sleep(self.args.delay_network_scan_secs)

    wap_index = str(0) if test.freq == '2.4' else str(1)
    subprocess.call(['/usr/sbin/iw', 'wlan0', 'connect',
                     'WifiManaged%s' % wap_index])
    factory.console.info('%sGHz. Antenna %s. Connecting WifiManaged%s. '\
                         'sleep 15s' % (test.freq, test.antenna, wap_index))

    time.sleep(self.args.delay_packet_capture_secs)

    factory.console.info('%sGHz. Antenna %s. Bringing up network' %
                         (test.freq, test.antenna))

    subprocess.Popen(_CMD_IFCONFIG % wap_index, shell=True)
    factory.console.info('%sGHz. Antenna %s. Gathering packet data on AP' %
                         (test.freq, test.antenna))
    ssh_proc = subprocess.Popen(_CMD_SSH % (wap_index, wap_index), shell=True,
                                stdout=subprocess.PIPE)
    subprocess.Popen( _CMD_PING % wap_index, shell=True)
    db_val_line = ssh_proc.communicate()[0]

    db_result = self.Calc_Signal_Strength(db_val_line)

    factory.console.info(
        '%sGHz. Antenna %s. Run complete. Average signal strength %d db.' %
        (test.freq, test.antenna, db_result.avg))
    if abs(db_result.max - db_result.min) > 10:
      factory.console.info(
      '%sGHz. Antenna %s. Signal strength inconsistent, did the door open ?' %
      (test.freq, test.antenna))

    if ( db_result.avg == 0 ):
      factory.console.info('Possible problem with test equipment.')

    if ((db_result.avg < test.db) or (abs(db_result.max-db_result.min) > 10)) :
      logging.info('%sGHz. Antenna %s. Signal problems.',
                   test.freq, test.antenna)
      self._fail = True


  def runTest(self):
    """Run the test.

    This test assumes a USB-Ethernet dongle has already been inserted.
    The dongle will be 'eth1' if this is an LTE capable system.
    If there is a 'eth1' then use that as the wired host ethernet port.
    If 'eth1' is not present then this is a WiFi only system and use
    'eth0' as the usb-ethernet port.

    Setup SSH key so a password doesn't need to be entered
    every time a connection attempt is made to the AP control computer.

    Args:
      None.
    """

    self._template.SetTitle(_TEST_TITLE)

    self._template.SetState(_MSG_INSTRUCTION)

    self.mkdir_p('/home/chronos/wifi')

    with os.fdopen(
        os.open("/home/chronos/wifi/testing_rsa", os.O_WRONLY | os.O_CREAT,
                0600),
        "w") as f:
      f.write(_TESTING_RSA)

    with open("/home/chronos/wifi/known_hosts", "w") as f:
      f.write(_SSH_KNOWN_HOSTS)

    subprocess.call(['stop', 'shill'])

    ifc_proc = subprocess.Popen(['/sbin/ifconfig','eth1'])
    ifc_proc.wait()
    if ifc_proc.returncode == 0:
      subprocess.call(['/sbin/ifconfig', 'eth1', '192.168.10.2'])
      factory.console.info( 'LTE system, using eth1 for wired network.' )
    else:
      subprocess.call(['/sbin/ifconfig', 'eth0', '192.168.10.2'])
      factory.console.info( 'Not LTE system, using eth0 for wired network.' )

    factory.console.info('Stopping WPA Supplicant.')
    subprocess.call(['stop', 'wpasupplicant'])

    self._initflag = True
    self._template.SetState(_MSG_READY_CLOSE)
    self._ui.BindKey(' ', self.RunSubtests)
    self._ui.Run()
