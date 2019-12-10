# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""A plugin that shows device information on the UI."""

import json
import logging
import os
import re
import subprocess
import time
from xml.sax import saxutils

from cros.factory.goofy.plugins import plugin
from cros.factory.test.i18n import _
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
from cros.factory.utils import sys_utils
from cros.factory.utils import time_utils
from cros.factory.utils import type_utils


class DeviceManager(plugin.Plugin):
  """A Goofy plugin that supports a variety of debug information."""

  def GetVarLogMessages(self):
    """Returns the last n bytes of /var/log/messages.

    Args:
      See sys_utils.GetVarLogMessages.
    """
    return plugin.MenuItem.ReturnData(
        action=plugin.MenuItem.Action.SHOW_IN_DIALOG,
        data=sys_utils.GetVarLogMessages())

  def GetVarLogMessagesBeforeReboot(self):
    """Returns the last few lines in /var/log/messages before current boot.

    Args:
      See sys_utils.GetVarLogMessagesBeforeReboot.
    """
    log = sys_utils.GetVarLogMessagesBeforeReboot()
    if not log:
      log = 'Unable to find log message indicating reboot.'

    return plugin.MenuItem.ReturnData(
        action=plugin.MenuItem.Action.SHOW_IN_DIALOG, data=log)

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
      return (time_utils.TimeString(boot_time + float(match.group(1))) + ' ' +
              match.group(0))

    return plugin.MenuItem.ReturnData(
        action=plugin.MenuItem.Action.SHOW_IN_DIALOG,
        data=re.sub(r'^\[\s*([.\d]+)\]', FormatTime, dmesg,
                    flags=re.MULTILINE))

  def ShowDeviceManagerWindow(self):
    return plugin.MenuItem.ReturnData(
        action=plugin.MenuItem.Action.RUN_AS_JS,
        data='this.deviceManager.showWindow();')

  @type_utils.Overrides
  def GetMenuItems(self):
    return [plugin.MenuItem(text=_('View /var/log/messages'),
                            callback=self.GetVarLogMessages,
                            eng_mode_only=True),
            plugin.MenuItem(text=_('View /var/log/messages before last reboot'),
                            callback=self.GetVarLogMessages,
                            eng_mode_only=True),
            plugin.MenuItem(text=_('View dmesg'),
                            callback=self.GetDmesg,
                            eng_mode_only=True),
            plugin.MenuItem(text=_('Device manager'),
                            callback=self.ShowDeviceManagerWindow,
                            eng_mode_only=True)]

  @plugin.RPCFunction
  def GetDeviceInfo(self, reload_function_array=None):
    """Returns system hardware info in XML format.

    Since the commands can be separated into two categories, faster ones and
    slower ones, we get our info in two stages. First, we execute the faster
    commands and return their results. Then we will enter the second stage when
    the frontend device manager needs the other ones.

    Args:
      reload_function_array: An array containing functions to be loaded. If
        the array includes nothing, it means that we are in first stage, where
        we need to execute all fast commands. Otherwise, we will only spawn the
        functions inside the array.

    Returns:
      A string including system hardware info.
    """

    def DeviceNodeString(
        node_id, node_description, tag_list, slow_command=None):
      """Returns a XML format string of a specific device.

      Args:
        node_id: An id attribute to identify the device in XML document.
        node_description: A human readable name of the device.
        tag_list: A list of more detailed information of the device. Each
          element, including (tag_name, tag_text, split_multiline), represents
          a tag, which is a child node of the device node.
        slow_command: If it is set, it means the command takes longer time and
          we wish to execute it later. Therefore the method will return a
          string without data but indicating the device needs to be executed
          again. The value, which is the name of the method is stored in an
          attribute of the device node.

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
            '<line>%s</line>' % saxutils.escape(l) for l in lines.splitlines())

      result = []
      result.append('<node id=%s' % saxutils.quoteattr(node_id))
      if not slow_command:
        result.append('>')
      else:
        result.append(' slow_command=%s>' % saxutils.quoteattr(slow_command))

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

    def SlowCommandDeviceNodeString(node_id, node_description, function_name):
      """Returns a XML string of a device which needs longer time to get info.

      Args:
        node_id: An id attribute to identify the device in XML document.
        node_description: A human readable name of the device.
        function_name: The name of the method which is slow.

      Return:
        A string with XML format, including only the description of the node.
      """
      return DeviceNodeString(
          node_id, node_description, [], slow_command=function_name)

    def GetBootDisk():
      """Returns boot disk info."""
      boot_device = process_utils.CheckOutput(['rootdev', '-s', '-d']).strip()

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
      tpm_root = '/sys/class/tpm/tpm0/device'
      legacy_tpm_root = '/sys/class/misc/tpm0/device'
      # TPM device path has been changed in kernel 3.18.
      if not os.path.exists(tpm_root):
        tpm_root = legacy_tpm_root
      tpm_status = (open(os.path.join(tpm_root, 'enabled')).read(),
                    open(os.path.join(tpm_root, 'owned')).read())
      tpm_stat = (
          ('Enabled: %s\nOwned: %s\n' % tpm_status) +
          process_utils.CheckOutput('crossystem | grep tpm_owner', shell=True))

      return DeviceNodeString(
          'tpm', 'TPM status', [('status', tpm_stat, True)])

    def GetHWID():
      """Returns HWID."""
      hwid = process_utils.CheckOutput(['crossystem', 'hwid'])

      return DeviceNodeString('hwid', 'HWID', [('hwid', hwid, False)])

    def GetWPStatus():
      """Returns current write protection status info."""
      host_wp_stat = (
          process_utils.CheckOutput(['flashrom', '-p', 'host', '--wp-status']))

      try:
        ec_wp_stat = (
            process_utils.CheckOutput(['flashrom', '-p', 'ec', '--wp-status']))
      except subprocess.CalledProcessError:
        ec_wp_stat = 'EC not available.'

      return DeviceNodeString(
          'wp', 'Current write protection status',
          [('host', host_wp_stat, True), ('ec', ec_wp_stat, True)])

    def GetVersion():
      """Returns EC/BIOS/Image version info."""
      fw_version = (
          process_utils.CheckOutput(['crossystem', 'fwid']) +
          process_utils.CheckOutput(['crossystem', 'ro_fwid']))

      try:
        ec_version = process_utils.CheckOutput(['ectool', 'version'])
      except subprocess.CalledProcessError:
        ec_version = 'EC not available.'

      image_version = ''.join(open('/etc/lsb-release', 'r').readlines())

      return DeviceNodeString(
          'version', 'AP Firmware(BIOS)/EC/Image Version',
          [('fw', fw_version, True), ('ec', ec_version, True),
           ('image', image_version, True)])

    def GetVPD():  # pylint: disable=unused-variable
      """Returns RO VPD and RW VPD info."""
      ro_vpd = process_utils.CheckOutput(['vpd', '-i', 'RO_VPD', '-l'])
      rw_vpd = process_utils.CheckOutput(['vpd', '-i', 'RW_VPD', '-l'])

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
      try:
        touchpad_stat = process_utils.CheckOutput(
            ['/opt/google/touchpad/tpcontrol_xinput', 'status'])
        lines = (
            [re.sub(r'\s\s+', '', line) for line in touchpad_stat.splitlines()])
      except Exception:
        logging.exception('Failed to get touchpad status')
        lines = ['Unknown']

      return DeviceNodeString(
          'touchpad_status', 'Touchpad status',
          [('status', '\n'.join(lines), True)])

    def GetPanelHDMIStatus():
      """Returns panel and HDMI status."""
      try:
        panel_hdmi_stat = process_utils.CheckOutput(['xrandr', '-d', ':0'])
      except Exception:
        panel_hdmi_stat = 'Unknown'
        logging.exception('Failed to get touchpad status')

      return DeviceNodeString(
          'panel_hdmi_stat', 'Panel/HDMI status',
          [('status', panel_hdmi_stat, True)])

    def GetModemStatus():
      """Returns modem status."""
      modem_stat = process_utils.CheckOutput(['modem', 'status'])

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
      cpu_usage_output = process_utils.CheckOutput(['top', '-n', '1', '-b'])
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
      disk_usage_output = process_utils.CheckOutput(['df', '-h'])

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

    def GetPowerUsage(fetch_time=20):  # pylint: disable=unused-variable
      """Returns power usage detail.

      Args:
        fetch_time: A number indicating how long powertop should fetch data.
          The default time is 20 seconds.
      """
      with file_utils.UnopenedTemporaryFile(suffix='.html') as html_file_path:
        process_utils.CheckOutput(['powertop', '--html=%s' % html_file_path,
                                   '--time=%d' % fetch_time])

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

    # In first stage, we execute faster commands first.
    if reload_function_array is None:
      # lshw provides common hardware information.
      lshw_output = process_utils.CheckOutput(['lshw', '-xml'])
      xml_lines = [line.strip() for line in lshw_output.splitlines()]

      # Use cros-specific commands to get cros info.
      cros_output = []
      cros_output.append('<node id="cros">')
      cros_output.append('<description>Chrome OS Specific</description>')
      cros_output.append(GetBootDisk())
      cros_output.append(GetTPMStatus())
      cros_output.append(GetHWID())
      cros_output.append(GetWPStatus())
      cros_output.append(GetVersion())
      cros_output.append(
          SlowCommandDeviceNodeString('vpd', 'RO/RW VPD', 'GetVPD()'))
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
      system_usage.append(
          SlowCommandDeviceNodeString(
              'power_usage', 'Power usage', 'GetPowerUsage()'))
      system_usage.append(GetDiskUsage())
      system_usage.append(GetMemoryUsage())
      system_usage.append('</node>')

      xml_lines.insert(xml_lines.index('</list>'), ''.join(system_usage))

      return ''.join(xml_lines)

    # In second stage, we execute slower commands and return their results.
    result = []
    for reload_function in json.loads(reload_function_array):
      result.append(eval(reload_function))  # pylint: disable=eval-used

    return json.dumps(result)
