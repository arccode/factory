#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""RPC methods exported from Goofy."""

import argparse
import inspect
import json
import logging
import os
import Queue
import random
import re
import subprocess
import tempfile
import threading
import time
import uuid
import yaml
from xml.sax import saxutils

import factory_common  # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test import shopfloor
from cros.factory.test import utils
from cros.factory.test.event import Event, EventClient
from cros.factory.test.test_lists.test_lists import SetActiveTestList
from cros.factory.tools import factory_bug
from cros.factory.utils import debug_utils, file_utils, process_utils


DEFAULT_GOOFY_RPC_TIMEOUT_SECS = 10
REBOOT_AFTER_UPDATE_DELAY_SECS = 5
PING_SHOPFLOOR_TIMEOUT_SECS = 2
UPLOAD_FACTORY_LOGS_TIMEOUT_SECS = 20
VAR_LOG_MESSAGES = '/var/log/messages'
RunState = utils.Enum(['UNINITIALIZED', 'STARTING', 'NOT_ACTIVE_RUN', 'RUNNING',
                       'FINISHED'])


class GoofyRPCException(Exception):
  """Goofy RPC exception."""
  pass


class GoofyRPC(object):
  """Goofy RPC main class."""

  def _InRunQueue(self, func, timeout_secs=None):
    """Runs a function in the Goofy run queue.

    Args:
      func: A callable to evaluate in Goofy run queue.
      timeout_secs: The duration in seconds after which to abort the call.  None
        to block until the call is done.

    Returns:
      Any value returned by the function.

    Raises:
      Any exception raised by the function.
    """
    # A queue to store the results of evaluating the function.  This
    # will contain a two-element tuple (ret, exc), where ret is the
    # return value or exc is any exception thrown.  Only one will be
    # set.
    result = Queue.Queue()
    def Target():
      try:
        # Call the function, and put the the return value on success.
        result.put((func(), None))
      except Exception as e:
        # Failure; put e.
        logging.exception('Exception in RPC handler')
        result.put((None, e))
      except:
        # Failure (but not an Exception); wrap whatever it is in an exception.
        result.put((None, GoofyRPCException(utils.FormatExceptionOnly())))

    def _GetFuncString():
      func_string = func.__name__
      if func.__name__ == '<lambda>':
        try:
          func_string = inspect.getsource(func).strip()
        except IOError:
          pass
      return func_string

    self.goofy.run_queue.put(Target)
    try:
      ret, exc = result.get(block=True, timeout=timeout_secs)
    except Queue.Empty:
      raise GoofyRPCException('Time out waiting for %s to complete' %
                              _GetFuncString())
    if exc:
      raise exc
    return ret

  def __init__(self, goofy):
    self.goofy = goofy

  def RegisterMethods(self, state_instance):
    """Registers exported RPC methods in a state object."""
    for name, m in inspect.getmembers(self):
      # Find all non-private methods (except this one)
      if ((not inspect.ismethod(m)) or
          name.startswith('_') or
          name == 'RegisterMethods'):
        continue

      # Bind the state instance method to our method.  (We need to
      # put this in a separate method to rebind m, since it will
      # change during the next for loop iteration.)
      def SetEntry(m):
        # pylint: disable=W0108
        state_instance.__dict__[name] = (
          lambda *args, **kwargs: m(*args, **kwargs))
      SetEntry(m)

  def FlushEventLogs(self):
    """Flushes event logs if an event_log_watcher is available.

    Raises an Exception if syncing fails.
    """
    self.goofy.log_watcher.FlushEventLogs()

  def UpdateFactory(self):
    """Performs a factory update.

    Returns:
      [success, updated, restart_time, error_msg] where:
        success: Whether the operation was successful.
        updated: Whether the update was a success and the system will reboot.
        restart_time: The time at which the system will restart (on success).
        error_msg: An error message (on failure).
    """
    ret_value = Queue.Queue()

    def PostUpdateHook():
      # After update, wait REBOOT_AFTER_UPDATE_DELAY_SECS before the
      # update, and return a value to the caller.
      now = time.time()
      ret_value.put([True, True, now + REBOOT_AFTER_UPDATE_DELAY_SECS, None])
      time.sleep(REBOOT_AFTER_UPDATE_DELAY_SECS)

    def Target():
      try:
        self.goofy.update_factory(
            auto_run_on_restart=True,
            post_update_hook=PostUpdateHook)
        # Returned... which means that no update was necessary.
        ret_value.put([True, False, None, None])
      except:  # pylint: disable=W0702
        # There was an update available, but we couldn't get it.
        logging.exception('Update failed')
        ret_value.put([False, False, None, utils.FormatExceptionOnly()])

    self.goofy.run_queue.put(Target)
    return ret_value.get()

  def AddNote(self, note):
    note['timestamp'] = int(time.time())
    self.goofy.event_log.Log('note',
                             name=note['name'],
                             text=note['text'],
                             timestamp=note['timestamp'],
                             level=note['level'])
    logging.info('Factory note from %s at %s (level=%s): %s',
                 note['name'], note['timestamp'], note['level'],
                 note['text'])
    if note['level'] == 'CRITICAL':
      self.goofy.run_queue.put(self.goofy.stop)
    self.goofy.state_instance.append_shared_data_list(
        'factory_note', note)
    self.PostEvent(Event(Event.Type.UPDATE_NOTES))

  def GetVarLogMessages(self, max_length=256*1024):
    """Returns the last n bytes of /var/log/messages.

    Args:
      max_length: Maximum number of bytes to return.
    """
    offset = max(0, os.path.getsize(VAR_LOG_MESSAGES) - max_length)
    with open(VAR_LOG_MESSAGES, 'r') as f:
      f.seek(offset)
      if offset != 0:
        # Skip first (probably incomplete) line
        offset += len(f.readline())
      data = f.read()

    if offset:
      data = ('<truncated %d bytes>\n' % offset) + data

    return unicode(data, encoding='utf-8', errors='replace')

  def GetVarLogMessagesBeforeReboot(self, lines=100, max_length=5*1024*1024):
    """Returns the last few lines in /var/log/messages before the current boot.

    Args:
      See utils.var_log_messages_before_reboot.
    """
    lines = utils.var_log_messages_before_reboot(lines=lines,
                                                 max_length=max_length)
    if lines:
      return unicode('\n'.join(lines) + '\n',
                     encoding='utf-8', errors='replace')
    else:
      return None

  @staticmethod
  def _ReadUptime():
    return open('/proc/uptime').read()

  def GetDmesg(self):
    """Returns the contents of dmesg.

    Approximate timestamps are added to each line.
    """
    dmesg = process_utils.Spawn(['dmesg'],
                                check_call=True, read_stdout=True).stdout_data
    uptime = float(self._ReadUptime().split()[0])
    boot_time = time.time() - uptime

    def FormatTime(match):
      return (utils.TimeString(boot_time + float(match.group(1))) + ' ' +
              match.group(0))

    # (?m) = multiline
    return re.sub(r'(?m)^\[\s*([.\d]+)\]', FormatTime, dmesg)

  def GetDeviceInfo(self):
    """Returns system hardware info in XML format."""

    def DeviceNodeString(node_id, node_description, tag_list):
      """Returns a XML format string of a specific device.

      Args:
        node_id: An id attribute to identify the device in XML document.
        node_description: A human readable name of the device.
        tag_list: A list of more detailed information of the device. Each
          element, including (tag_name, tag_text, split_multiline), represents
          a tag, which is a child node of the device node.

      Returns:
        A string with XML format of the device node.
      """

      def SplitMultilineToNodes(lines):
        """Returns a XML format string to split lines of a output string.

        Since HTML cannot identify '\n' automatically, we should split the
        multiline output into multiple tags (one line is transformed into one
        tag) so that the device manager can show it in multiline format.

        Args:
          lines: The multiline output to split.

        Returns:
          A string with XML format of the lines.
        """
        lines = lines.rstrip()

        return ''.join(
            '<line>%s</line>' % saxutils.escape(l) for l in lines.split('\n'))

      result = []
      result.append('<node id="%s">' % saxutils.escape(node_id))
      result.append(
          '<description>%s</description>' % saxutils.escape(node_description))

      for tag_name, tag_text, split_multiline in tag_list:
        xml_tag_name = saxutils.escape(tag_name)
        if split_multiline:
          xml_tag_text = SplitMultilineToNodes(tag_text)
        else:
          xml_tag_text = saxutils.escape(tag_text)
        result.append(
            '<%s>%s</%s>' % (xml_tag_name, xml_tag_text, xml_tag_name))

      result.append('</node>')

      return ''.join(result)

    def GetBootDisk():
      """Returns boot disk info."""
      boot_device = subprocess.check_output(['rootdev', '-s', '-d']).strip()

      boot_device_removable_path = (
          os.path.join('/sys/block/',
                       os.path.basename(boot_device),
                       'removable'))
      boot_device_removable = open(boot_device_removable_path).read().strip()

      if boot_device.startswith('/dev/sd'):
        boot_device_type = (
            'SSD' if boot_device_removable == '0' else 'USB drive')
      elif boot_device.startswith('/dev/mmcblk'):
        boot_device_type = (
            'eMMC' if boot_device_removable == '0' else 'SD card')
      else:
        boot_device_type = 'unknown'

      return DeviceNodeString(
          'bootdisk', 'Boot disk',
          [('device', boot_device, False), ('type', boot_device_type, False)])

    def GetTPMStatus():
      """Returns TPM status info."""
      tpm_stat = (
          subprocess.check_output(['cryptohome', '--action=tpm_status']) +
          subprocess.check_output('crossystem | grep tpm_owner', shell=True))

      return DeviceNodeString(
          'tpm', 'TPM status', [('status', tpm_stat, True)])

    def GetHWID():
      """Returns HWID."""
      hwid = subprocess.check_output(['crossystem', 'hwid'])

      return DeviceNodeString('hwid', 'HWID', [('hwid', hwid, False)])

    def GetWPStatus():
      """Returns current write protection status info."""
      host_wp_stat = (
          subprocess.check_output(['flashrom', '-p', 'host', '--wp-status']))

      try:
        ec_wp_stat = (
            subprocess.check_output(['flashrom', '-p', 'ec', '--wp-status']))
      except:
        ec_wp_stat = 'EC not available.'

      return DeviceNodeString(
          'wp', 'Current write protection status',
          [('host', host_wp_stat, True), ('ec', ec_wp_stat, True)])

    def GetVersion():
      """Returns EC/BIOS/Image version info."""
      fw_version = (
          subprocess.check_output(['crossystem', 'fwid']) +
          subprocess.check_output(['crossystem', 'ro_fwid']))

      try:
        ec_version = subprocess.check_output(['ectool', 'version'])
      except:
        ec_version = 'EC not available.'

      image_version = ''.join(open('/etc/lsb-release', 'r').readlines())

      return DeviceNodeString(
          'version', 'AP Firmware(BIOS)/EC/Image Version',
          [('fw', fw_version, True), ('ec', ec_version, True),
           ('image', image_version, True)])

    def GetVPD():
      """Returns RO VPD and RW VPD info."""
      ro_vpd = subprocess.check_output(['vpd', '-i', 'RO_VPD', '-l'])
      rw_vpd = subprocess.check_output(['vpd', '-i', 'RW_VPD', '-l'])

      return DeviceNodeString(
          'vpd', 'RO/RW VPD', [('ro', ro_vpd, True), ('rw', rw_vpd, True)])

    def GetInputDeviceFirmwareVersion(device_name_list):
      """Returns firmware version of a specific hardware.

      Args:
        device_name_list: A list consists of possible human readable names of
          the hardware.

      Returns:
        A string including the firmware version.
      """
      re_device_name = (
          re.compile(r'N: Name=".*(%s).*"' % ('|'.join(device_name_list))))
      re_device_sysfs = re.compile(r'S: Sysfs=(.*)')

      device_list = open('/proc/bus/input/devices').read().split('\n\n')

      for device_data in device_list:
        match_device_name = re_device_name.findall(device_data)
        if not match_device_name:
          continue
        device_sysfs = re_device_sysfs.findall(device_data)[0].lstrip('/')
        firmware_path_patterns = ['firmware_version', 'fw_version']
        device_path = os.path.join('/sys', device_sysfs, 'device')

        for path_pattern in firmware_path_patterns:
          device_firmware_path = os.path.join(device_path, path_pattern)
          if os.path.exists(device_firmware_path):
            return open(device_firmware_path).read().strip()
        return 'unknown'

      return 'unknown'

    def GetTouchscreenFirmwareVersion():
      """Returns touchscreen firmware version."""
      return DeviceNodeString(
          'touchscreen_version', 'Touchscreen firmware version',
          [('fw_version', GetInputDeviceFirmwareVersion(['Touchscreen']),
            False)])

    def GetTouchpadFirmwareVersion():
      """Returns touchpad firmware version."""
      return DeviceNodeString(
          'touchpad_version', 'Touchpad firmware version',
          [('fw_version',
            GetInputDeviceFirmwareVersion(['Trackpad', 'Touchpad']),
            False)])

    def GetTouchpadStatus():
      """Returns touchpad status."""
      touchpad_stat = subprocess.check_output(
          ['/opt/google/touchpad/tpcontrol_xinput', 'status'])
      lines = (
          [re.sub(r'\s\s+', '', line) for line in touchpad_stat.splitlines()])

      return DeviceNodeString(
          'touchpad_status', 'Touchpad status',
          [('status', '\n'.join(lines), True)])

    def GetPanelHDMIStatus():
      """Returns panel and HDMI status."""
      panel_hdmi_stat = subprocess.check_output(['xrandr', '-d', ':0'])

      return DeviceNodeString(
          'panel_hdmi_stat', 'Panel/HDMI status',
          [('status', panel_hdmi_stat, True)])

    def GetModemStatus():
      """Returns modem status."""
      modem_stat = subprocess.check_output(['modem', 'status'])

      modem_stat_tag_list = []
      tag_content = []
      tag_name = ''

      for line in modem_stat.splitlines():
        if line.startswith('    '):
          tag_content.append(line.strip())
        elif line.startswith('  '):
          if tag_content:
            modem_stat_tag_list.append(
                (tag_name, '\n'.join(tag_content), True))

          tag_name = line.strip(' :').lower()
          tag_content = []

      if tag_content:
        modem_stat_tag_list.append((tag_name, '\n'.join(tag_content), True))

      return DeviceNodeString('modem', 'Modem status', modem_stat_tag_list)

    def ComposeHTMLTable(table_data):
      """Constructs a HTML format string containing a table of the input.

      If the input is [[data1, data2], [data3, data4]] then the output string
      would be '<table><tr><td>data1</td><td>data2</td></tr><tr><td>data3</td><
      td>data4</td></tr></table>'.

      Args:
        table_data: A list of list consisting of the table elements.

      Returns:
        HTML string.
      """
      table_html_string = ['<table class="multi-column-table">']

      first_row = True
      for row in table_data:
        table_html_string.append('<tr>')
        if first_row:
          table_html_string.extend(
              ('<th>' + element + '</th>') for element in row)
          first_row = False
        else:
          table_html_string.extend(
              ('<td>' + element + '</td>') for element in row)
        table_html_string.append('</tr>')

      table_html_string.append('</table>')

      return ''.join(table_html_string)

    def GetCPUUsage():
      """Returns CPU usage detail in HTML format."""
      cpu_usage_output = subprocess.check_output(['top', '-n', '1', '-b'])
      cpu_usage_table = []

      lines = cpu_usage_output.split('\n')
      first_blank_line_index = lines.index('')

      # CPU / memory info
      cpu_usage_table.append('<ul>')
      cpu_usage_table.extend(
          ('<li>' + line + '</li>') for line in lines[:first_blank_line_index])
      cpu_usage_table.append('</ul>')

      # Process info
      cpu_usage_table.append(
          ComposeHTMLTable(
              [line.split() for line in lines[first_blank_line_index + 1:]]))

      return DeviceNodeString(
          'cpu_usage', 'CPU usage',
          [('html_string', ''.join(cpu_usage_table), False)])

    def GetDiskUsage():
      """Returns disk usage detail in HTML format."""
      disk_usage_output = subprocess.check_output(['df', '-h'])

      disk_usage_html_string = ComposeHTMLTable(
          [line.split() for line in disk_usage_output.splitlines()])

      return DeviceNodeString(
          'disk_usage', 'Disk usage',
          [('html_string', disk_usage_html_string, False)])

    def GetMemoryUsage():
      """Returns memory usage detail."""
      memory_usage_output = file_utils.ReadLines('/proc/meminfo')
      memory_usage_list = []

      for line in memory_usage_output:
        line = re.sub(r'\s+', '', line.strip())
        data = line.split(':')
        memory_usage_list.append((data[0], data[1], False))

      return DeviceNodeString(
          'memory_usage', 'Memory usage', memory_usage_list)

    def GetItemListFromPowerTOPHTML(html_file_path):
      """Returns a list of item information by extracting the PowerTOP report.

      This method is used to get data from HTML file generated by PowerTOP.
      The relationship between tag id and description of an item is defined
      in 'blocks' structure, we need to extract it out.

      Args:
        html_file_path: Path to HTML generated by PowerTOP.

      Returns:
        A list of tuples (description, node_id) for each item.
      """
      lines = file_utils.ReadLines(html_file_path)

      found_start = False
      found = False
      for i, line in enumerate(lines):
        if not found_start and 'blocks: {' in line:
          start_index = i
          found_start = True
        elif found_start and '}' in line:
          end_index = i
          found = True
          break

      if not found:
        return None

      row_content = lines[start_index + 1:end_index]
      item_list = []
      re_item_line = re.compile(r'(.*): \'(.*)\'')

      for line in row_content:
        match = re_item_line.findall(line.strip().rstrip(','))
        if match:
          item_list.append((match[0][1], match[0][0]))

      return item_list

    def FetchFromHTML(html_file_path, tag_id):
      """Returns HTML data of the tag whose id is tag_id from a HTML file.

      powertop command supports HTML/CSV output format. However, the CSV output
      cannot be easily parsed to construct a HTML table (ex: each row of the
      CSV file doesn't have the same number of fields). We need this function
      to extract data from powertop's HTML output then modify it to our own
      style.

      Args:
        html_file_path: Path to HTML generated by PowerTOP.
        tag_id: A string used to identify which tag to find.

      Returns:
        A HTML format string.
      """

      lines = file_utils.ReadLines(html_file_path)
      found_tag_id = False
      content_rows = []

      for line in lines:
        if not found_tag_id:
          if 'id="%s"' % tag_id in line:
            found_tag_id = True
        else:
          if not '</div>' in line:
            content_rows.append(line.strip())
          else:
            break

      html_string = ''.join(content_rows)
      return html_string.replace('<table', '<table class="multi-column-table"')

    def GetPowerUsage(time=5):
      """Returns power usage detail."""
      f, html_file_path = tempfile.mkstemp(suffix='.html')
      subprocess.check_output(
          ['powertop', '--html=%s' % html_file_path, '--time=%d' % time])

      power_usage_main_xml = []
      power_usage_main_xml.append('<node id="power_usage">')
      power_usage_main_xml.append('<description>Power usage</description>')

      item_list = GetItemListFromPowerTOPHTML(html_file_path)

      first_item = True
      for description, tag_id in item_list:
        if first_item:
          power_usage_main_xml.append('<html_string>')
          power_usage_main_xml.append(
              saxutils.escape(FetchFromHTML(html_file_path, tag_id)))
          power_usage_main_xml.append('</html_string>')
          first_item = False
        else:
          power_usage_main_xml.append(
              DeviceNodeString(
                  tag_id, description,
                  [('html_string',
                    FetchFromHTML(html_file_path, tag_id),
                    False)]))

      power_usage_main_xml.append('</node>')

      return ''.join(power_usage_main_xml)

    # lshw provides common hardware information.
    lshw_output = subprocess.check_output(['lshw', '-xml'])
    xml_lines = [line.strip() for line in lshw_output.split('\n')]

    # Use cros-specific commands to get cros info.
    cros_output = []
    cros_output.append('<node id="cros">')
    cros_output.append('<description>Chrome OS Specific</description>')
    cros_output.append(GetBootDisk())
    cros_output.append(GetTPMStatus())
    cros_output.append(GetHWID())
    cros_output.append(GetWPStatus())
    cros_output.append(GetVersion())
    cros_output.append(GetVPD())
    cros_output.append('</node>')

    xml_lines.insert(xml_lines.index('</list>'), ''.join(cros_output))

    # Get peripheral device info.
    peripheral_output = []
    peripheral_output.append('<node id="peripheral">')
    peripheral_output.append('<description>Peripheral Devices</description>')
    peripheral_output.append(GetTouchscreenFirmwareVersion())
    peripheral_output.append(GetTouchpadFirmwareVersion())
    peripheral_output.append(GetTouchpadStatus())
    peripheral_output.append(GetPanelHDMIStatus())
    peripheral_output.append(GetModemStatus())
    peripheral_output.append('</node>')

    xml_lines.insert(xml_lines.index('</list>'), ''.join(peripheral_output))

    # Get system usage details.
    system_usage = []
    system_usage.append('<node id="usage">')
    system_usage.append('<description>System Usage</description>')
    system_usage.append(GetCPUUsage())
    system_usage.append(GetPowerUsage())
    system_usage.append(GetDiskUsage())
    system_usage.append(GetMemoryUsage())
    system_usage.append('</node>')

    xml_lines.insert(xml_lines.index('</list>'), ''.join(system_usage))

    return json.dumps(''.join(xml_lines))

  def LogStackTraces(self):
    """Logs the stack backtraces of all threads."""
    logging.info(debug_utils.DumpStackTracebacks())

  def IsUSBDriveAvailable(self):
    try:
      with factory_bug.MountUSB(read_only=True):
        return True
    except (IOError, OSError):
      return False

  def SaveLogsToUSB(self, archive_id=None):
    """Saves logs to a USB stick.

    Returns:
      [dev, archive_name, archive_size, temporary]:
        dev: The device that was mounted or used
        archive_name: The file name of the archive
        archive_size: The size of the archive
        temporary: Whether the USB drive was temporarily mounted
    """
    try:
      with factory_bug.MountUSB() as mount:
        output_file = factory_bug.SaveLogs(mount.mount_point, archive_id)
        return [mount.dev, os.path.basename(output_file),
                os.path.getsize(output_file),
                mount.temporary]
    except:
      logging.exception('Unable to save logs to USB')
      raise

  def PingShopFloorServer(self):
    """Pings the shop floor server.

    Raises:
      Exception if unable to contact shop floor server.
    """
    shopfloor.get_instance(
        detect=True, timeout=PING_SHOPFLOOR_TIMEOUT_SECS).Ping()

  def UploadFactoryLogs(self, name, serial, description):
    """Uploads logs to the shopfloor server.

    Returns:
      [archive_name, archive_size, archive_key]
        archive_name: The uploaded file name.
        archive_size: The size of the archive.
        archive_key: A "key" that may later be used to refer to the archive.
            This is just a randomly-chosen 8-digit number.
    """
    archive_key = "%08d" % random.SystemRandom().randint(0, 1e8)
    archive_id = '.'.join([re.sub('[^A-Za-z0-9.]', '_', x)
                           for x in (archive_key, name, serial, description)])
    output_file = factory_bug.SaveLogs(tempfile.gettempdir(), archive_id)
    try:
      with open(output_file) as f:
        data = f.read()
      shopfloor.get_instance(
          detect=True, timeout=UPLOAD_FACTORY_LOGS_TIMEOUT_SECS
          ).SaveAuxLog(os.path.basename(output_file),
                       shopfloor.Binary(data))
      return [os.path.basename(output_file), os.path.getsize(output_file),
              archive_key]
    finally:
      file_utils.TryUnlink(output_file)

  def UpdateSkippedTests(self):
    """Updates skipped tests based on run_if."""
    done = threading.Event()

    def Target():
      try:
        self.goofy.update_skipped_tests()
      finally:
        done.set()

    self.goofy.run_queue.put(Target)
    done.wait()

  def SyncTimeWithShopfloorServer(self):
    self.goofy.sync_time_with_shopfloor_server(True)

  def PostEvent(self, event):
    """Posts an event."""
    self.goofy.event_client.post_event(event)

  def StopTest(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Stops current tests."""
    self._InRunQueue(
        lambda: self.goofy.stop(reason='RPC call to stop tests',
                                fail=True),
        timeout_secs=timeout_secs)

  def ClearState(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Stops current tests and clear all test state."""
    def Target():
      self.goofy.stop(reason='RPC call to clear test state',
                      fail=True)
      self.goofy.clear_state()
    self._InRunQueue(Target, timeout_secs=timeout_secs)

  def RunTest(self, path, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Runs a test."""
    test = self.goofy.test_list.lookup_path(path)
    if not test:
      raise GoofyRPCException('Unknown test path %r' % path)
    test = test.get_top_level_parent_or_group()

    self._InRunQueue(lambda: self.goofy.restart_tests(root=test),
                     timeout_secs=timeout_secs)
    return self.goofy.run_id

  def RestartAllTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Restarts all tests.

    Args:
      timeout_secs: The duration in seconds after which to abort the call.
    """
    self._InRunQueue(self.goofy.restart_tests, timeout_secs=timeout_secs)
    return self.goofy.run_id

  def CancelPendingTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Cancels all pending tests."""
    self._InRunQueue(self.goofy.cancel_pending_tests,
                     timeout_secs=timeout_secs)

  def LogStartupMessages(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Logs the tail of var/log/messages and mosys and EC console logs."""
    self._InRunQueue(self.goofy.log_startup_messages,
                     timeout_secs=timeout_secs)

  def Shutdown(self, operation):
    """Starts a shutdown operation through Goofy.

    Args:
      operation: The shutdown operation to run ('halt', 'reboot',
        or 'full_reboot').
    """
    if operation not in ['halt', 'reboot', 'full_reboot']:
      raise GoofyRPCException('Invalid shutdown operation %r' % operation)
    # No timeout for shutdown as the operation can be delayed for arbitrary
    # duration by the factory test.
    self._InRunQueue(lambda: self.goofy.shutdown(operation))

  def GetLastShutdownTime(self):
    """Gets last shutdown time detected by Goofy."""
    return self.goofy.last_shutdown_time

  def UIPresenterCountdown(self, message, timeout_secs, timeout_message,
                           timeout_is_error=True):
    """Starts a countdown on the presenter UI.

    In situations like a reboot, Goofy is not available and on the UI
    presenter side, it looks like a disconnected state. To avoid confusing
    operators, this method may be used to inform the current status of Goofy
    and set a timeout by which Goofy is expected to come back alive.

    Args:
      message: The text to show while counting down.
      timeout_secs: The timeout for countdown.
      timeout_message: The text to show when countdown ends.
      timeout_is_error: True for red timeout message; False for black.
    """
    self.goofy.link_manager.StartCountdown(
        message, timeout_secs, timeout_message,
        'red' if timeout_is_error else 'black')

  def SuspendDUTMonitoring(self, interval_sec):
    """Suspends monitoring of DUT connection.

    For some tests, DUT is expected to go offline for a short period without
    rebooting. In this case, we don't want the presenter to reload the UI;
    otherwise, we lose the UI of the current running tests. By suspending
    monitoring, the link manager on the presenter side knows to ignore
    connection failure for a given amount of time.

    Args:
      interval_sec: Number of seconds to suspend.
    """
    self.goofy.link_manager.SuspendMonitoring(interval_sec)

  def ResumeDUTMonitoring(self):
    """Immediately resume suspended monitoring of DUT connection."""
    self.goofy.link_manager.ResumeMonitoring()

  def _GetTests(self):
    """Helper method to get a list of all tests and their states."""
    paths_to_run = set([t.path for t in self.goofy.tests_to_run])
    ret = []
    states = self.goofy.state_instance.get_test_states()
    for t in self.goofy.test_list.walk(in_order=True):
      test_state = states.get(t.path)
      ret.append(dict(path=t.path,
                      parent=(t.subtests != []),
                      pending=t.path in paths_to_run,
                      **test_state.__dict__))
    return ret

  def IsReadyForUIConnection(self):
    """Checks whether the Goofy backend is ready for UI connection.

    Returns:
      A boolean indicating whether the Goofy backend is ready for UI connection.
    """
    return self.goofy.ready_for_ui_connection

  def GetTests(self, timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Returns a list of all tests and their states.

    Args:
      timeout_secs: The duration in seconds after which to abort the call.
    """
    return self._InRunQueue(self._GetTests, timeout_secs=timeout_secs)

  def GetTestLists(self):
    """Returns available test lists.

    Returns:
      An array of test lists, each a dict containing:
        id: An identifier for the test list (empty for the default test list).
        name: A human-readable name of the test list.
        enabled: Whether this is the current-enabled test list.
    """
    ret = []
    for k, v in self.goofy.test_lists.iteritems():
      ret.append(
        dict(id=k, name=v.label_en,
             enabled=(k == self.goofy.test_list.test_list_id)))

    # Sort by name.
    ret.sort(key=lambda x: x['name'].lower())

    return ret

  def GetGoofyStatus(self):
    """Returns a dictionary containing Goofy status information.

    Returns:
      A dict with the following elements:
        uuid: A UUID identifying the current goofy run.
        test_list_id: The active test_list ID.
        status: The current status of Goofy.
    """
    return {'uuid': self.goofy.uuid,
            'test_list_id': (
                self.goofy.test_list.test_list_id if self.goofy.test_list
                else None),
            'run_id': self.goofy.run_id,
            'status': self.goofy.status}

  def GetActiveRunID(self):
    """Gets the id of the current active test run."""
    return self.goofy.run_id

  def GetTestRunStatus(self, run_id,
                       timeout_secs=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Returns the status of a given test run.

    The given run id must match the last run id stored in Goofy to get the
    status.

    Args:
      run_id: The id of a test run or None to get current test run status in
        Goofy.
      timeout_secs: The duration in seconds after which to abort the call.

    Returns:
      A dict with the following elements:
        status: The status of the given run of factory tests.

          - UNINITIALIZED: No run has been scheduled yet.
          - STARTING: Goofy just went through a reboot and the latest test run
                      state has not been restored.
          - NOT_ACTIVE_RUN: If the given run is not the current active one.
          - RUNNING: Goofy is running the scheduled tests of the given run.
          - FINISHED: Goofy has finished running the scheduled tests of the
                      given run.

        If status is RUNNING or FINISHED, the following elements are also
        included:

        run_id: The id of the current active run.
        scheduled_tests: A list of factory tests that were scheduled for
          the active run and their status.
    """
    def Target(run_id):
      if not run_id:
        run_id = self.goofy.run_id

      ret_val = {}
      if self.goofy.run_id is None:
        if self.goofy.state_instance.get_shared_data('run_id', optional=True):
          # A run ID is present in shared data but hasn't been restored.
          ret_val['status'] = RunState.STARTING
        else:
          # No test run has ever been scheduled.
          ret_val['status'] = RunState.UNINITIALIZED
      elif run_id != self.goofy.run_id:
        ret_val['status'] = RunState.NOT_ACTIVE_RUN
      else:
        tests = self._GetTests()
        scheduled_tests_status = [t for t in tests if t['path'] in
                                  self.goofy.scheduled_run_tests]
        ret_val['run_id'] = self.goofy.run_id,
        ret_val['scheduled_tests'] = scheduled_tests_status

        if (self.goofy.tests_to_run or
            any(t['status'] == factory.TestState.ACTIVE
                for t in scheduled_tests_status)):
          ret_val['status'] = RunState.RUNNING
        else:
          ret_val['status'] = RunState.FINISHED
      return ret_val

    return self._InRunQueue(lambda: Target(run_id), timeout_secs=timeout_secs)

  def SwitchTestList(self, test_list_id, automation_mode='none'):
    """Switches test lists.

    Args:
      test_list_id: The test list ID.
      automation_mode: The automation mode to enable.  Valid values are:
        ('none', 'partial', 'full').

    Raises:
      TestListError: The test list does not exist.
    """
    # Have goofy throw an error if the test list ID is invalid.
    self.goofy.GetTestList(test_list_id)
    SetActiveTestList(test_list_id)

    if utils.in_chroot():
      raise GoofyRPCException(
          'Cannot switch test in chroot; please manually restart Goofy')
    else:
      # Restart Goofy and clear state.
      process_utils.Spawn(
          ['nohup ' +
           os.path.join(factory.FACTORY_PATH, 'bin', 'factory_restart') +
           ' --automation-mode %s -a &' % automation_mode],
          shell=True, check_call=True)
      # Wait for a while.  This process should be killed long before
      # 60 seconds have passed.
      time.sleep(60)
      # This should never be reached, but not much we can do but
      # complain to the caller.
      raise GoofyRPCException('Factory did not restart as expected')

  def CallExtension(self, name, timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS,
                    **kwargs):
    """Invokes a RPC call to Factory Test Chrome Extension.

    Blocks until a return value is retrieved or if timeout is reached.

    Args:
      name: The name of extension RPC function to execute.
      timeout: Seconds to wait before RPC timeout.
      kwargs: Arguments to pass to the extension; they will be
        available in an "args" dict within the execution context.

    Returns:
      An object representing RPC call return value.

    Raises:
      utils.TimeoutError: if no response until timeout reached.
    """
    # To support timeout (and to avoid race condition), we need a dedicated
    # event client.
    rpc_id = str(uuid.uuid4())
    rpc_event = Event(Event.Type.EXTENSION_RPC, name=name, is_response=False,
                      rpc_id=rpc_id, args=kwargs)
    result = EventClient().request_response(
        rpc_event,
        lambda e: (e.type == rpc_event.type and e.rpc_id == rpc_id and
                   e.is_response),
        timeout)
    if result is None:
      raise utils.TimeoutError('Failed calling Extension RPC <%r>', name)
    return result.args

  def GetDisplayInfo(self, timeout=DEFAULT_GOOFY_RPC_TIMEOUT_SECS):
    """Returns output display information (by calling extension RPC).

    Args:
      timeout: Seconds to wait before RPC timeout.

    Returns:
      A list of objects for current display. See Chrome Extension API
          chrome.system.display for the details.

    Raises:
      utils.TimeoutError: if no response until timeout.
    """
    return self.CallExtension('GetDisplayInfo', timeout=timeout)

  def TakeScreenshot(self, output_file=None):
    """Takes a screenshot through Telemetry tab.Screenshot API.

    Args:
      output_file: The output file path to store the captured image file.
          If not given, screenshot is saved to /var/log/screenshot_<TIME>.png.
    """
    if not output_file:
      output_file = ('/var/log/screenshot_%s.png' %
                     time.strftime("%Y%m%d-%H%M%S"))
    subprocess.check_call('xwd -d :0 -root | convert - "%s"' % output_file,
                          shell=True)


def main():
  parser = argparse.ArgumentParser(
      description="Sends an RPC to Goofy.")
  parser.add_argument(
      'command',
      help=('The command to run (as a Python expression), e.g.: '
            """RunTest('RunIn.Stress.BadBlocks')"""))
  args = parser.parse_args()

  goofy = factory.get_state_instance()
  logging.basicConfig(level=logging.INFO)

  if '(' not in args.command:
    parser.error('Expected parentheses in command, e.g.: '
                 """RunTest('RunIn.Stress.BadBlocks')""")

  logging.info('Evaluating expression: %s', args.command)
  ret = eval(args.command, {},
             dict((x, getattr(goofy, x))
                  for x in GoofyRPC.__dict__.keys()
                  if not x.startswith('_')))
  if ret is not None:
    print yaml.safe_dump(ret)


if __name__ == '__main__':
  main()
