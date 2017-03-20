# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# pylint: disable=C0301,W0613,W0622


"""The creation of generic FATP test list.

This file implements FATP method to create FATP test list.
"""


import factory_common  # pylint: disable=unused-import
from cros.factory.goofy.plugins import plugin
from cros.factory.test.i18n import _
from cros.factory.test.test_lists.test_lists import AutomatedSequence
from cros.factory.test.test_lists.test_lists import FactoryTest
from cros.factory.test.test_lists.test_lists import OperatorTest
from cros.factory.test.test_lists.test_lists import Passed
from cros.factory.test.test_lists.test_lists import RebootStep
from cros.factory.test.test_lists.test_lists import TestGroup


def FATP(args):
  """Creates FATP test list.

  Args:
    args: A TestListArgs object.
  """
  with TestGroup(id='FATP'):
    OperatorTest(
        id='Start',
        label=_('Start'),
        pytest_name='start',
        never_fails=True,
        dargs=dict(
            press_to_continue=True,
            require_external_power=args.fatp_check_external_power,
            check_factory_install_complete=args.check_factory_install_complete,
            require_shop_floor='defer' if args.enable_shopfloor else False))

    # Decides if DUT is sampled for audio fixture test.
    FactoryTest(
        id='SelectForAudioFixture',
        label=_('Select For Audio Fixture'),
        pytest_name='select_for_sampling',
        dargs=dict(
            rate=args.fatp_sampling_rate['fatp_audio_fixture'].rate,
            device_data_key=args.fatp_sampling_rate[
                'fatp_audio_fixture'].key))

    # Decides if DUT is sampled for camera fixture test.
    FactoryTest(
        id='SelectForCameraFixture',
        label=_('Select For Camera Fixture'),
        pytest_name='select_for_sampling',
        dargs=dict(
            rate=args.fatp_sampling_rate['fatp_camera_fixture'].rate,
            device_data_key=args.fatp_sampling_rate[
                'fatp_camera_fixture'].key))

    # Decides if DUT is sampled for RF fixture test.
    FactoryTest(
        id='SelectForRFFixture',
        label=_('Select For RF Fixture'),
        pytest_name='select_for_sampling',
        dargs=dict(
            rate=args.fatp_sampling_rate['fatp_rf_fixture'].rate,
            device_data_key=args.fatp_sampling_rate[
                'fatp_rf_fixture'].key))

    # Decides if DUT is sampled for RF fixture test.
    # LTE Model has different sampling rate for RF fixture.
    FactoryTest(
        id='SelectForRFFixtureLTEModel',
        label=_('Select For RF Fixture LTE Model'),
        pytest_name='select_for_sampling',
        run_if=args.HasLTE,
        dargs=dict(
            rate=args.fatp_sampling_rate['fatp_rf_fixture_lte_model'].rate,
            device_data_key=args.fatp_sampling_rate[
                'fatp_rf_fixture_lte_model'].key))

    # Decides if DUT is sampled for LTE fixture test.
    FactoryTest(
        id='SelectForLTEFixture',
        label=_('Select For LTE Fixture'),
        pytest_name='select_for_sampling',
        run_if=args.HasLTE,
        dargs=dict(
            rate=args.fatp_sampling_rate['fatp_lte_fixture'].rate,
            device_data_key=args.fatp_sampling_rate[
                'fatp_lte_fixture'].key))

    # Write-protect screw should be on.
    OperatorTest(
        id='WriteProtectSwitch',
        label=_('Write Protect Switch'),
        pytest_name='write_protect_switch')

    # Tests micro USB port using on-the-go dongle and a USB key.
    OperatorTest(
        id='MicroUSBPerformance',
        label=_('Micro USB Performance'),
        pytest_name='removable_storage',
        dargs=dict(
            media='USB',
            sysfs_path='/sys/devices/s5p-ehci/usb1/1-1/1-1:1.0',
            block_size=512 * 1024,
            perform_random_test=False,
            perform_sequential_test=True,
            sequential_block_count=8))

    # Checks Lid switch signal.
    OperatorTest(
        id='LidSwitch',
        label=_('Lid Switch'),
        pytest_name='lid_switch')

    # Checks display for black dots and white dots.
    OperatorTest(
        id='DisplayPoint',
        label=_('Display Point'),
        pytest_name='display_point',
        dargs=dict(
            point_size=3,
            max_point_count=5))

    # Lets operator check display quality under different colors.
    OperatorTest(
        id='Display',
        label=_('Display'),
        pytest_name='display')

    # Lets operator check backlight brightness can be changed.
    OperatorTest(
        id='Backlight',
        label=_('Backlight'),
        pytest_name='backlight',
        dargs=dict(
            brightness_path='/sys/class/backlight/ps8622-backlight/brightness'))

    # Checks if camera is connected to USB.
    FactoryTest(
        id='CameraProbe',
        label=_('Camera Probe'),
        pytest_name='usb_probe',
        dargs=dict(
            search_string='Camera'))

    # Lets operator check camera and camera light function.
    OperatorTest(
        id='Camera',
        label=_('Camera'),
        pytest_name='camera',
        dargs=dict(
            do_capture_manual=True,
            do_led_manual=True,
            capture_resolution=(640, 480),
            resize_ratio=0.7))

    # Lets operator check LED function.
    OperatorTest(
        id='LED',
        label=_('LED'),
        pytest_name='led')

    # Lets operator check keyboard function.
    # User can use evtest command to list the input devices and get
    # keyboard_device_name.
    OperatorTest(
        id='Keyboard',
        label=_('Keyboard'),
        pytest_name='keyboard',
        dargs=dict(
            keyboard_device_name='cros-ec-i2c',
            sequential_press=True,
            skip_power_key=False))

    with AutomatedSequence(id='SIMCard', label=_('SIM Card')):
      # For 3G model only. Note that different factory can have different
      # testing sequences of 3G model. The tests set in this test list
      # are just examples.
      # SIM card and SIM card tray are inserted at this
      # station. This test checks sim card tray detection pin is low
      # in the beginning. The test asks operator to insert sim card and
      # sim card tray. Then the test checks if sim card tray detection pin
      # is high.
      OperatorTest(
          id='InsertSIMCardTray',
          label=_('Insert SIM Card Tray'),
          pytest_name='probe_sim_card_tray',
          dargs=dict(
              tray_already_present=False,
              only_check_presence=False,
              insert=True,
              remove=False),
          run_if=args.HasCellular)

      # For 3G model only. Probes SIM card information through modem manager.
      # The test checks the connection between modem and MLB, and the connection
      # between modem and SIM card.
      OperatorTest(
          id='ProbeSIM',
          label=_('Probe SIM'),
          pytest_name='probe_sim',
          run_if=args.HasCellular)

      # For 3G model only. SIM card and SIM card tray should be removed
      # at this station. They will be put back in the packing station.
      OperatorTest(
          id='CheckNoSIMCardTray',
          label=_('Check No SIM Card Tray'),
          pytest_name='probe_sim_card_tray',
          dargs=dict(tray_already_present=False),
          run_if=args.HasCellular)

      # For 3G model only. Probe modem IMEI value and log it.
      OperatorTest(
          id='ProbeIMEI',
          label=_('Probe IMEI'),
          pytest_name='probe_cellular_info',
          run_if=args.HasCellular,
          dargs=dict(probe_meid=False))

    # Basic WiFi test which just scans for any SSID.
    # If there is setup for wireless connection test, then this test can
    # be skipped.
    FactoryTest(
        id='Wifi',
        label=_('Wifi'),
        pytest_name='wireless',
        retries=args.fatp_retries_basic_wifi)

    # Uses the AP set in fatp_ap_map. The test will let DUT
    # connect to that AP, and try to access file at test_url.
    # User should replace services in dargs with a list of available tuples
    # (ssid, password) if there is no 'line' in device_data.
    OperatorTest(
        exclusive_resources=[plugin.RESOURCE.NETWORK],
        id='WirelessConnection',
        label=_('Wireless Connection'),
        pytest_name='wireless',
        dargs=dict(
            services=lambda env: [
                (args.fatp_ap_map[env.GetDeviceData()['line']]['5G'][0][0],
                 args.fatp_ap_password),
                (args.fatp_ap_map[env.GetDeviceData()['line']]['2.4G'][0][0],
                 args.fatp_ap_password)],
            test_url=('http://%s/testdata/test' % args.shopfloor_host),
            md5sum='097daa256e3a4569305db580df900d8d'))

    with TestGroup(id='RSSI', label=_('RSSI Test')):
      # DUT will switch antenna and scan for different AP based on 'line'
      # in device_data.
      OperatorTest(
          exclusive_resources=[plugin.RESOURCE.NETWORK],
          id='WirelessRSSI24G',
          label=_('Wireless RSSI 2.4G'),
          pytest_name='wireless_antenna',
          dargs=dict(
              device_name='mlan0',
              services=lambda env: [
                  args.fatp_ap_map[env.GetDeviceData()['line']]['2.4G'][0]],
              strength=(
                  lambda env:
                  args.fatp_ap_map[env.GetDeviceData()['line']]['2.4G'][1]),
              scan_count=10,
              switch_antenna_sleep_secs=1))

      OperatorTest(
          exclusive_resources=[plugin.RESOURCE.NETWORK],
          id='WirelessRSSI5G',
          label=_('Wireless RSSI 5G'),
          pytest_name='wireless_antenna',
          dargs=dict(
              device_name='mlan0',
              services=lambda env: [
                  args.fatp_ap_map[env.GetDeviceData()['line']]['5G'][0]],
              strength=(
                  lambda env:
                  args.fatp_ap_map[env.GetDeviceData()['line']]['5G'][1]),
              scan_count=10,
              switch_antenna_sleep_secs=1))

      # Prompts a message before starting RSSI tests.
      # TODO(itspeter), this should be supported by cellular_gobi_rssi and
      # lte_rssi tests.
      OperatorTest(
          id='PromptBeforeRSSI',
          label=_('Begin RSSI Test'),
          pytest_name='message',
          never_fails=True,
          run_if=lambda env: args.HasCellular(env) or args.HasLTE(env),
          dargs=dict(
              html=_('Press space to start RSSI tests.'),
              text_size='500',
              text_color='black',
              background_color='yellow'))

      # For 3G model only. Checks Received signal strength indication (RSSI)
      # for cellular module.
      OperatorTest(
          exclusive_resources=[plugin.RESOURCE.NETWORK],
          id='CellularRSSI',
          label=_('Cellular RSSI'),
          pytest_name='cellular_gobi_rssi',
          run_if=args.HasCellular,
          dargs=dict(
              modem_path='ttyUSB1',
              strength_map=[('MAIN', 'WCDMA_800', 4405, 10, -70, None),
                            ('AUX', 'WCDMA_800', 4405, 10, -70, None)],
              firmware_switching=True))

      # For LTE model only. Checks Received signal strength indication (RSSI)
      # for LTE module.
      OperatorTest(
          exclusive_resources=[plugin.RESOURCE.NETWORK],
          id='LTERSSI',
          label=_('LTE RSSI'),
          pytest_name='lte_rssi',
          run_if=args.HasLTE,
          dargs=dict(
              strength_map=[
                  ('US_700c_Upper_MAIN', 5230, 1000, 0, 3, -56, -20),
                  ('US_700c_Upper_AUX', 5230, 1000, 1, 3, -56, -20)]))

    # Checks Received signal strength indication (RSSI) for bluetooth signal.
    OperatorTest(
        id='Bluetooth',
        label=_('Bluetooth'),
        pytest_name='bluetooth',
        dargs=dict(
            expected_adapter_count=1,
            scan_devices=True,
            prompt_scan_message=True,
            average_rssi_threshold=-55.0,
            scan_counts=3,
            scan_timeout_secs=7))

    # For LTE model only. Writes parameters to LTE module.
    OperatorTest(
        exclusive_resources=[plugin.RESOURCE.NETWORK],
        id='WriteLTEChromebookSpecificParameters',
        label=_('Write LTE Chromebook Specific Parameters'),
        pytest_name='lte_smt',
        run_if=args.HasLTE,
        dargs=dict(
            write_chromebook_specific_parameters=True,
            skip_if_modem_locked=True))

    # Checks audio jack using a loopback dongle.
    OperatorTest(
        id='AudioJack',
        label=_('Audio Jack'),
        pytest_name='audio_loop',
        dargs={'require_dongle': True,
               'check_dongle': True,
               'output_volume': 15,
               'initial_actions': [('1', 'init_audiojack')],
               'input_dev': ('Audio Card', '0'),
               'output_dev': ('Audio Card', '0'),
               'tests_to_conduct': [{'type': 'sinewav',
                                     'freq_threshold': 50,
                                     'rms_threshold': (0.08, None)}]})

    # Checks speaker and digital mic.
    OperatorTest(
        id='SpeakerDMic',
        label=_('Speaker/Microphone'),
        pytest_name='audio_loop',
        dargs={'require_dongle': False,
               'check_dongle': True,
               'output_volume': 10,
               'initial_actions': [('1', 'init_speakerdmic')],
               'input_dev': ('Audio Card', '0'),
               'output_dev': ('Audio Card', '0'),
               'tests_to_conduct': [{'type': 'audiofun',
                                     'duration': 4,
                                     'threshold': 80}]})

    # Checks touchpad including one finger moving, two finger moving,
    # single clicking and double clicking.
    OperatorTest(
        id='Touchpad',
        label=_('Touchpad'),
        pytest_name='touchpad')

    # Checks touchscreen using one finger moving.
    OperatorTest(
        id='Touchscreen',
        label=_('Touchscreen'),
        pytest_name='touchscreen')

    # Checks external display. Note that the reboot might not be needed if
    # driver can support. This may be different on different boards and
    # monitors. Run ext_display test alone and checks the screen indeed
    # refresh on external display.
    OperatorTest(
        id='ExtDisplay',
        label=_('External Display'),
        pytest_name='ext_display',
        dargs=dict(
            main_display='eDP-1',
            display_info=[('uUSB HDMI Dongle', 'HDMI-1')]))

    # We groups fixture tests in this TestGroup.
    if args.enable_fixture_tests:
      with TestGroup(id='Fixtures', label=_('Fixture Test')):
        # If there is any fixture tests selected, prompts a message to ask
        # operator to take this DUT to fixture stations.
        OperatorTest(
            id='FixtureStart',
            label=_('Fixture Start'),
            pytest_name='message',
            run_if=args.SelectedForAnyFixture,
            never_fails=True,
            dargs=dict(
                html=_('This unit is selected to run fixture tests.<br>'
                       'Please move this unit to fixture stations.<br>'
                       'Press space to start fixture tests.'),
                text_size='500',
                text_color='black',
                background_color='yellow'))

        # Checks audio quality.
        OperatorTest(
            id='AudioQuality',
            label=_('Audio Quality'),
            pytest_name='audio_quality',
            run_if=args.SelectedForSampling('fatp_audio_fixture'))

        # Checks camera performance.
        OperatorTest(
            id='CameraPerformance',
            label=_('Camera Performance'),
            pytest_name='camera_fixture',
            run_if=args.SelectedForSampling('fatp_camera_fixture'),
            dargs=dict(
                unit_test=False,
                test_type='Full',
                use_als=False,
                test_chart_version='B',
                log_good_image=False,
                log_bad_image=True,
                auto_serial_number=('Alcor',
                                    r'^\s*iManufacturer\s+\S+\s+(\S+)'),
                data_method='shopfloor',
                shopfloor_directory='camera',
                shopfloor_param_file='camera.params.FATP',
                ip_addr=None))

        # WiFi model or LTE model.
        # Checks radiated signal strength for WiFi using RF fixture.
        OperatorTest(
            exclusive_resources=[plugin.RESOURCE.NETWORK],
            id='WifiRadiated',
            label=_('Wifi Radiated'),
            pytest_name='radiated_wifi',
            run_if=lambda env: (
                args.SelectedForSampling('fatp_rf_fixture')(env) and
                not args.HasCellular(env)),
            dargs=dict(
                test_name='WifiRadiated',
                category='production',
                base_directory='rf/wifi/',
                config_file='parameters.production',
                calibration_config='calibration_config',
                parameters=['calibration_config*',
                            'parameters.production'],
                blinking_pattern=[(0b001, 0.3), (0b100, 0.3)],
                static_ips=[(None, True),
                            ('192.168.132.66', True),
                            (None, True)]))

        # 3G model only. Checks radiated signal strength for WiFi and cellular
        # using RF fixture.
        OperatorTest(
            exclusive_resources=[plugin.RESOURCE.NETWORK],
            id='ComboRadiated',
            label=_('Wifi and 3G Radiated'),
            pytest_name='radiated_combo',
            run_if=lambda env: (
                args.SelectedForSampling('fatp_rf_fixture')(env) and
                args.HasCellular(env)),
            dargs=dict(
                test_name_combo=('WifiRadiated', 'CellularRadiated'),
                category='production',
                base_directory_combo=('rf/wifi/', 'rf/cellular/'),
                config_file_combo=('parameters.production',
                                   'parameters.production'),
                calibration_config_combo=('calibration_config',
                                          'calibration_config'),
                parameters_combo=(['calibration_config*',
                                   'parameters.production'],
                                  ['calibration_config*',
                                   'parameters.production']),
                blinking_pattern_combo=([(0b001, 0.3), (0b100, 0.3)],
                                        [(0b101, 0.3), (0b010, 0.3)]),
                static_ips_combo=([(None, True),
                                   ('192.168.132.66', True),
                                   (None, True)],
                                  None)))

        # LTE model only. Checks radiated signal strength for LTE
        # using RF fixture. Note that we call it lte_fixture but it is
        # actually using RF fixture to test LTE signal.
        OperatorTest(
            exclusive_resources=[plugin.RESOURCE.NETWORK],
            id='LTERadiated',
            label=_('LTE Radiated'),
            run_if=lambda env: (
                args.SelectedForSampling('fatp_lte_fixture')(env) and
                args.HasLTE(env)),
            pytest_name='radiated_lte',
            dargs=dict(
                test_name='LTERadiated',
                category='production',
                base_directory='rf/lte/',
                config_file='parameters.production',
                calibration_config='calibration_config',
                parameters=['calibration_config*',
                            'parameters.production'],
                blinking_pattern=[(0b100, 0.2), (0b010, 0.2), (0b001, 0.2)],
                use_shopfloor=True,
                static_ips=[(None, True),
                            ('192.168.132.66', True),
                            (None, True)]))

        # Barrier of all fixture tests.
        args.Barrier(
            id_suffix='Fixtures',
            run_if=args.SelectedForAnyFixture)

        # Prompts a message to ask operator to put back DUT to the line from
        # fixture stations.
        OperatorTest(
            id='FixtureEnd',
            label=_('Fixture End'),
            pytest_name='message',
            run_if=args.SelectedForAnyFixture,
            never_fails=True,
            dargs=dict(
                html=_('This unit has finished fixture tests.<br>'
                       'Please move this unit back to line.<br>'
                       'Press space to continue.'),
                text_size='500',
                text_color='black',
                background_color='#00FF00'))

    # Performs a USB performance test near micro-USB.
    # Checks the log of the test for correct sysfs path.
    # It should match the hierachy shown in 'lsusb -t' command.
    OperatorTest(
        id='USBPerformanceNearMicroUSB',
        label=_('USB Performance Near Micro USB'),
        pytest_name='removable_storage',
        dargs=dict(
            media='USB',
            sysfs_path='/sys/devices/s5p-ehci/usb1/1-2/1-2.1',
            block_size=args.fatp_usb_performance_block_size,
            perform_random_test=False,
            perform_sequential_test=True,
            sequential_block_count=args.fatp_usb_performance_sequential_block_count))

    # Performs a USB performance test near audio jack.
    # Checks the log of the test for correct sysfs path.
    # It should match the hierachy shown in 'lsusb -t' command.
    OperatorTest(
        id='USBPerformanceNearAudioJack',
        label=_('USB Performance Near Audio Jack'),
        pytest_name='removable_storage',
        dargs=dict(
            media='USB',
            sysfs_path='/sys/devices/s5p-ehci/usb1/1-2/1-2.3',
            block_size=args.fatp_usb_performance_block_size,
            perform_random_test=False,
            perform_sequential_test=True,
            sequential_block_count=args.fatp_usb_performance_sequential_block_count))

    # This takes a long time (~30s) to execute, can be moved to run-in if
    # necessary.
    with AutomatedSequence(id='MRCCache', label=_('MRCCache')):
      FactoryTest(
          id='Create',
          label=_('Create Cache'),
          pytest_name='mrc_cache',
          dargs={'mode': 'create'})

      RebootStep(
          id='Reboot',
          label=_('Reboot'),
          iterations=1)

      FactoryTest(
          id='Verify',
          label=_('Verify'),
          pytest_name='mrc_cache',
          dargs={'mode': 'verify'})

    args.Barrier('FATP')

    # Prompts a message to notify that FATP tests are finished.
    # Depends on the factory flow, some DUT may go to another test process
    # e,g. Rolling Reliability Test (RRT). Otherwise, DUT should go to
    # Google Required Tests (GRT).
    OperatorTest(
        id='Finish',
        label=_('Finish'),
        pytest_name='message',
        require_run=(Passed('FATP.BarrierFATP')
                     if args.fatp_require_run_for_finish else None),
        never_fails=True,
        dargs=dict(
            html=_('FATP tests finished. Press SPACE to run GRT,<br>'
                   'or switch test list to RRT.')))
