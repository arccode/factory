# -*- coding: utf-8 -*-
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test for the audio function.

This test supports 2 loopback mode:
  1. Loop from headphone out to headphone in.
  2. Loop from speaker to digital microphone.

And 3 test scenarios:
  1. Audiofun test, which plays different tones and checks recorded frequency.
     This test can be conducted simultaneously on different devices.  This test
     can not be conducted with dongle inserted.
  2. Sinewav test, which plays simple sine wav and checks if the recorded
     frequency is in the range specified.  Optionally checks the RMS and
     amplitude thresholds.
  3. Noise test, which plays nothing and record, then checks the RMS and
     amplitude thresholds.

Since this test is sensitive to different loopback dongles, user can set a list
of output volume candidates. The test can pass if it can pass at any one of
output volume candidates.

Here are three test list examples for three test cases::

    OperatorTest(
        id='SpeakerDMic',
        label_zh=u'喇叭/麦克风',
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

    OperatorTest(
        id='Noise',
        label_zh=u'喇叭/麦克风',
        pytest_name='audio_loop',
        dargs={'require_dongle': False,
               'check_dongle': True,
               'initial_actions': [('1', 'init_speakerdmic')],
               'input_dev': ('Audio Card', '0'),
               'output_dev': ('Audio Card', '0'),
               'tests_to_conduct': [{'type': 'noise',
                                     'duration': 2,
                                     'rms_threshold': (None, 0.5),
                                     'amplitude_threshold': (-0.9, 0.9)}]})

    OperatorTest(
        id='AudioJack',
        label_zh=u'音源孔',
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
"""

from __future__ import print_function

import os
import re
import tempfile
import time
import threading
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.test.args import Arg
from cros.factory.test import audio_utils
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import Enum
from cros.factory.utils.process_utils import Spawn, SpawnOutput, PIPE

# Default setting
_DEFAULT_FREQ_HZ = 1000

# Regular expressions to match audiofuntest message.
_AUDIOFUNTEST_STOP_RE = re.compile('^Stop')
_AUDIOFUNTEST_SUCCESS_RATE_RE = re.compile('.*rate\s*=\s*(.*)$')

# Default minimum success rate of audiofun test to pass.
_DEFAULT_AUDIOFUN_TEST_THRESHOLD = 50
# Default duration to do the audiofun test, in seconds.
_DEFAULT_AUDIOFUN_TEST_DURATION = 10
# Default duration to do the sinewav test, in seconds.
_DEFAULT_SINEWAV_TEST_DURATION = 1
# Default frequency tolerance, in Hz.
_DEFAULT_SINEWAV_FREQ_THRESHOLD = 50
# Default duration to do the noise test, in seconds.
_DEFAULT_NOISE_TEST_DURATION = 1
# Default RMS thresholds when checking recorded file.
_DEFAULT_SOX_RMS_THRESHOLD = (0.08, None)
# Default Amplitude thresholds when checking recorded file.
_DEFAULT_SOX_AMPLITUDE_THRESHOLD = (None, None)
# Default AudioFun test pairs.
_DEFAULT_AUDIOFUN_TEST_PAIRS = [(0, 0), (1, 1)]

_UI_HTML = """
<h1 id="message" style="position:absolute; top:45%">
<center style="font-size: 20pt">
    <div id="require_dongle">
        <span class="goofy-label-en">Plug in audio jack dongle</span>
        <span class="goofy-label-zh">請放入音源孔測試置具</span>
    </div>
    <br/>
    <span class="goofy-label-en">Hit s to start loopback test</span>
    <span class="goofy-label-zh">请按下s键开始音源回放测试</span>
</center>
</h1>
"""

MicSource = Enum(['external', 'panel', 'mlb'])

class PlaySineThread(threading.Thread):
  """Wraps the execution of arecord in a thread."""
  def __init__(self, channel, odev, freq, seconds):
    threading.Thread.__init__(self)
    self.cmdargs = audio_utils.GetPlaySineArgs(channel, odev, freq,
        seconds)

  def run(self):
    Spawn(self.cmdargs.split(' '), check_call=True)


class AudioLoopTest(unittest.TestCase):
  """Audio Loop test to test two kind of situations.
  1. Speaker to digital microphone.
  2. Headphone out to headphone in.
  """
  ARGS = [
    Arg('initial_actions', list, 'List of tuple (card, actions)', []),
    Arg('input_dev', (str, tuple),
        'Input ALSA device for string.  (card_name, sub_device) for tuple. '
        'For example: "hw:0,0" or ("audio_card", "0").', 'hw:0,0'),
    Arg('output_dev', (str, tuple),
        'Onput ALSA device for string.  (card_name, sub_device) for tuple. '
        'For example: "hw:0,0" or ("audio_card", "0").', 'hw:0,0'),
    Arg('output_volume', (int, list), 'An int of output volume or a list of'
        ' output volume candidates', 10),
    Arg('autostart', bool, 'Auto start option', False),
    Arg('require_dongle', bool, 'Require dongle option', False),
    Arg('check_dongle', bool,
        'Check dongle status whether match require_dongle', False),
    Arg('cras_enabled', bool, 'Whether cras should be running or not',
        False),
    Arg('mic_source', str, 'Microphone source: external, panel, mlb',
        'external'),
    Arg('tests_to_conduct', list, 'A list of dicts.  A dict should contain \n'
        'at least one key named **type** indicating the test type, which can \n'
        'be **audiofun**, **sinewav**, or **noise**.\n'
        '\n'
        'If type is **audiofun**, the dict can optionally contain:\n'
        '  - **duration**: The test duration, in seconds.\n'
        '  - **threshold**: The minimum success rate to pass the test.\n'
        '  - **test_pairs**: A list of tuple to show speaker and microphone\n'
        '      channel. [(speaker_channel, microphone_channel)], 0 is left\n'
        '      and 1 is right.\n'
        '\n'
        'If type is **sinewav**, the dict can optionally contain:\n'
        '  - **duration**: The test duration, in seconds.\n'
        '  - **freq_threshold**: Acceptable frequency margin.\n'
        '  - **rms_threshold**: A tuple of **(min, max)** that will make\n'
        '      sure the following inequality is true: *min <= recorded audio\n'
        '      RMS (root mean square) value <= max*, otherwise, fail the\n'
        '      test.  Both of **min** and **max** can be set to None, which\n'
        '      means no limit.\n'
        '  - **amplitude_threshold**: A tuple of (min, max) and it will make\n'
        '      sure the inequality is true: *min <= minimum measured\n'
        '      amplitude <= maximum measured amplitude <= max*, otherwise,\n'
        '      fail the test.  Both of **min** and **max** can be set to\n'
        '      None, which means no limit.\n'
        '\n'
        'If type is **noise**, the dict can optionally contain:\n'
        '  - **duration**: The test duration, in seconds.\n'
        '  - **rms_threshold**: A tuple of **(min, max)** that will make\n'
        '      sure the following inequality is true: *min <= recorded audio\n'
        '      RMS (root mean square) value <= max*, otherwise, fail the\n'
        '      test.  Both of **min** and **max** can be set to None, which\n'
        '      means no limit.\n'
        '  - **amplitude_threshold**: A tuple of (min, max) and it will make\n'
        '      sure the inequality is true: *min <= minimum measured\n'
        '      amplitude <= maximum measured amplitude <= max*, otherwise,\n'
        '      fail the test.  Both of **min** and **max** can be set to\n'
        '      None, which means no limit.\n', optional=False),
  ]

  def setUp(self):
    # Tansfer input and output device format
    if type(self.args.input_dev) is tuple:
      self._in_card = audio_utils.GetCardIndexByName(self.args.input_dev[0])
      self._input_device = "hw:%s,%s" % (
          self._in_card, self.args.input_dev[1])
    else:
      self._input_device = self.args.input_dev
      self._in_card = self.GetCardIndex(self._input_device)

    if type(self.args.output_dev) is tuple:
      self._out_card = audio_utils.GetCardIndexByName(self.args.output_dev[0])
      self._output_device = "hw:%s,%s" % (
          self._out_card, self.args.output_dev[1])
    else:
      self._output_device = self.args.output_dev
      self._out_card = self.GetCardIndex(self._output_device)

    self._output_volumes = self.args.output_volume
    if isinstance(self._output_volumes, int):
      self._output_volumes = [self._output_volumes]
    self._output_volume_index = 0

    self._freq = _DEFAULT_FREQ_HZ

    # The test results under each output volume candidate.
    # If any one of tests to conduct fails, test fails under that output
    # volume candidate. If test fails under all output volume candidates,
    # the whole test fails.
    self._test_results = [True] * len(self._output_volumes)
    self._test_message = []

    self._mic_source = {'external': MicSource.external,
                        'panel': MicSource.panel,
                        'mlb': MicSource.mlb}[self.args.mic_source]

    self._audio_util = audio_utils.AudioUtil()
    for card, action in self.args.initial_actions:
      if card.isdigit() is False:
        card = audio_utils.GetCardIndexByName(card)
      self._audio_util.ApplyAudioConfig(action, card)

    self._current_test_args = None

    # Setup HTML UI, and event handler
    self._ui = test_ui.UI()
    self._ui.AddEventHandler('start_run_test', self.StartRunTest)
    self._ui_template = ui_templates.OneSection(self._ui)
    self._ui_template.SetState(_UI_HTML)

    # Check cras status
    if self.args.cras_enabled:
      cras_status = 'start/running'
    else:
      cras_status = 'stop/waiting'
    if cras_status not in SpawnOutput(['status', 'cras']):
      self._ui.Fail('cras status is wrong (expected status: %s). '
                    'Please make sure that you have appropriate setting for '
                    '"disable_services=[\'cras\']" in the test item.' %
          cras_status)

  def tearDown(self):
    self._audio_util.RestoreMixerControls()

  def runTest(self):
    # If autostart, JS triggers start_run_test event.
    # Otherwise, it binds start_run_test with 's' key pressed.
    self._ui.CallJSFunction('init', self.args.autostart,
        self.args.require_dongle)
    self._ui.Run()

  def AppendErrorMessage(self, error_message):
    """Sets the test result to fail and append a new error message."""
    self._test_results[self._output_volume_index] = False
    self._test_message.append(
        'Under output volume %r' % self._output_volumes[
             self._output_volume_index])
    self._test_message.append(error_message)
    factory.console.error(error_message)

  def GetCardIndex(self, device):
    """Gets the card index from given device names.

    Args:
      device: ALSA device name
    """
    dev_name_pattern = re.compile(".*?hw:([0-9]+),([0-9]+)")
    match = dev_name_pattern.match(device)
    if match:
      return match.group(1)
    else:
      raise ValueError('device name %s is incorrect' % device)

  def AudioFunTestPair(self, speaker_channel, mic_channel):
    """Runs audiofuntest program to get the frequency from microphone
    immediately according to speaker and microphone setting.

    Sample audiofuntest message:
    O: carrier = 41, delay = 6, success = 60, fail = 0, rate = 100.0
    Stop play tone
    Stop capturing data

    Args:
      speaker_channel: 0 is left channel, 1 is right channel
      mic_channel: 0 is left channel, 1 is right channel
    """
    factory.console.info('Test speaker channel %d and mic channel %d' %
        (speaker_channel, mic_channel))
    if self._mic_source == MicSource.panel:
      self._audio_util.EnableDmic(self._in_card)
      if mic_channel is 0:
        self._audio_util.MuteRightDmic(self._in_card)
      else:
        self._audio_util.MuteLeftDmic(self._in_card)
    elif self._mic_source == MicSource.mlb:
      self._audio_util.EnableMLBDmic(self._in_card)
      if mic_channel is 0:
        self._audio_util.MuteRightMLBDmic(self._in_card)
      else:
        self._audio_util.MuteLeftMLBDmic(self._in_card)

    test_result = None
    duration = self._current_test_args.get(
        'duration', _DEFAULT_AUDIOFUN_TEST_DURATION)
    process = Spawn([audio_utils.AUDIOFUNTEST_PATH,
        '-r', '48000', '-i', self._input_device, '-o', self._output_device,
        '-l', '%d' % duration, '-a', '%d' % speaker_channel],
        stderr=PIPE)
    last_success_rate = None

    while True:
      proc_output = process.stderr.readline()
      if not proc_output:
        break
      m = _AUDIOFUNTEST_SUCCESS_RATE_RE.match(proc_output)
      if m is not None:
        last_success_rate = float(m.group(1))
        self._ui.CallJSFunction('testInProgress', last_success_rate)

      m = _AUDIOFUNTEST_STOP_RE.match(proc_output)
      if m is not None:
        threshold = self._current_test_args.get(
            'threshold', _DEFAULT_AUDIOFUN_TEST_THRESHOLD)
        test_result = (last_success_rate > threshold)
        break

    # Show instant message and wait for a while
    if not test_result:
      if last_success_rate is not None:
        self._ui.CallJSFunction('testFailResult', last_success_rate)
        time.sleep(1)
        self.AppendErrorMessage(
            'For speaker channel %s and mic channel %s, The success rate is '
            '%.1f, too low!' % (speaker_channel, mic_channel, last_success_rate)
            )
      else:
        self.AppendErrorMessage('audiofuntest terminated unexpectedly')
      time.sleep(0.5)

  def AudioFunTest(self):
    """Setup speaker and microphone test pairs and run audiofuntest program."""

    factory.console.info('Run audiofuntest from %r to %r' % (
        self._output_device, self._input_device))

    test_pairs = self._current_test_args.get(
        'test_pairs', _DEFAULT_AUDIOFUN_TEST_PAIRS)
    for pair in test_pairs:
      self.AudioFunTestPair(pair[0], pair[1])

  def TestLoopbackChannel(self, output_device, noise_file_name, num_channels):
    """Tests loopback on all channels.

    Args:
      output_device: Output devices
      noise_file_name: Name of the file contains pre-recorded noise.
      num_channels: Number of channels to test
    """
    for channel in xrange(num_channels):
      reduced_file_path = "/tmp/reduced-%d-%s.wav" % (channel, time.time())
      record_file_path = "/tmp/record-%d-%s.wav" % (channel, time.time())

      # Play thread has one more second to ensure record process can record
      # entire sine tone
      duration = self._current_test_args.get('duration',
          _DEFAULT_SINEWAV_TEST_DURATION)
      playsine_thread = PlaySineThread(channel, output_device, self._freq,
          duration + 1)
      playsine_thread.start()
      time.sleep(0.5)

      self.RecordFile(duration, file_path=record_file_path)

      playsine_thread.join()

      audio_utils.NoiseReduceFile(record_file_path, noise_file_name,
          reduced_file_path)

      sox_output_reduced = audio_utils.SoxStatOutput(reduced_file_path, channel)
      self.CheckRecordedAudio(sox_output_reduced)

      os.unlink(reduced_file_path)
      os.unlink(record_file_path)

  def SinewavTest(self):
    self._ui.CallJSFunction('testInProgress', None)
    duration = self._current_test_args.get(
        'duration', _DEFAULT_SINEWAV_TEST_DURATION)
    # Record a sample of "silence" to use as a noise profile.
    noise_file = self.RecordFile(duration)

    # Playback sine tone and check the recorded audio frequency.
    self.TestLoopbackChannel(self._output_device, noise_file.name,
        audio_utils.DEFAULT_NUM_CHANNELS)
    os.unlink(noise_file.name)

  def NoiseTest(self):
    self._ui.CallJSFunction('testInProgress', None)
    # Record the noise file.
    duration = self._current_test_args.get(
        'duration', _DEFAULT_NOISE_TEST_DURATION)
    noise_file = self.RecordFile(duration)

    # Since we have actually only 1 channel, we can just give channel=0 here.
    sox_output = audio_utils.SoxStatOutput(noise_file.name, 0)
    self.CheckRecordedAudio(sox_output)
    os.unlink(noise_file.name)

  def RecordFile(self, duration, file_path=None):
    """Records file for *duration* seconds and returns the file obj.  Optionally
    renames the file to *file_path*.  The caller is responsible for removing the
    file at last.

    Args:
      duration: Recording duration, in seconds.
      file_path: If not None, name the recorded file as *file_path*.

    Return:
      The recorded file object.
    """
    if file_path is None:
      recorded_file = tempfile.NamedTemporaryFile(delete=False)
    else:
      recorded_file = open(file_path, 'w')

    rec_cmd = ['arecord', '-D', self._input_device, '-f', 'dat', '-d',
        str(duration)]
    Spawn(rec_cmd + [recorded_file.name], check_call=True)

    return recorded_file

  def CheckRecordedAudio(self, sox_output):
    rms_value = audio_utils.GetAudioRms(sox_output)
    factory.console.info('Got audio RMS value: %f.', rms_value)
    rms_threshold = self._current_test_args.get(
        'rms_threshold', _DEFAULT_SOX_RMS_THRESHOLD)
    if (rms_threshold[0] is not None and rms_threshold[0] > rms_value):
      self.AppendErrorMessage('Audio RMS value %f too low. Minimum pass is %f.'
          % (rms_value, rms_threshold[0]))
    if (rms_threshold[1] is not None and rms_threshold[1] < rms_value):
      self.AppendErrorMessage('Audio RMS value %f too high. Maximum pass is %f.'
          % (rms_value, rms_threshold[1]))

    amplitude_threshold = self._current_test_args.get(
        'amplitude_threshold', _DEFAULT_SOX_AMPLITUDE_THRESHOLD)
    min_value = audio_utils.GetAudioMinimumAmplitude(sox_output)
    factory.console.info('Got audio min amplitude: %f.', min_value)
    if (amplitude_threshold[0] is not None and
        amplitude_threshold[0] > min_value):
      self.AppendErrorMessage(
          'Audio minimum amplitude %f too low. Minimum pass is %f.' % (
              min_value, amplitude_threshold[0]))

    max_value = audio_utils.GetAudioMaximumAmplitude(sox_output)
    factory.console.info('Got audio max amplitude: %f.', max_value)
    if (amplitude_threshold[1] is not None and
        amplitude_threshold[1] < max_value):
      self.AppendErrorMessage(
          'Audio maximum amplitude %f too high. Maximum pass is %f.' % (
              max_value, amplitude_threshold[1]))

    if self._current_test_args['type'] == 'sinewav':
      freq = audio_utils.GetRoughFreq(sox_output)
      freq_threshold = self._current_test_args.get(
          'freq_threshold', _DEFAULT_SINEWAV_FREQ_THRESHOLD)
      if freq is None or (abs(freq - self._freq) > freq_threshold):
        self.AppendErrorMessage('Test Fail at frequency %r' % freq)
      else:
        factory.console.info('Got frequency %d' % freq)

  def MayPassTest(self):
    """Checks if test can pass with result of one output volume.

    Returns: True if test passes, False otherwise.
    """
    factory.console.info('Test results for output volume %r: %r',
                         self._output_volumes[self._output_volume_index],
                         self._test_results[self._output_volume_index])
    if self._test_results[self._output_volume_index]:
      self._ui.CallJSFunction('testPassResult')
      time.sleep(0.5)
      self._ui.Pass()
      return True
    return False

  def FailTest(self):
    """Fails test."""
    factory.console.info('Test results for each output volumes: %r',
                         zip(self._output_volumes, self._test_results))
    self._ui.Fail('; '.join(self._test_message))

  def StartRunTest(self, event): # pylint: disable=W0613
    jack_status = self._audio_util.GetAudioJackStatus(self._in_card)
    # When audio jack detection feature is ready on a platform, we can
    # enable check_dongle option to check jack status matches we expected.
    if self.args.check_dongle:
      # We've encountered false positive running audiofuntest tool against
      # audio fun-plug on a few platforms; so it is suggested not to run
      # audiofuntest with HP/MIC jack
      if jack_status is True:
        if any((t['type'] == 'audiofun') for t in self.args.tests_to_conduct):
          factory.console.info('Audiofuntest does not require dongle.')
          raise ValueError('Audiofuntest does not require dongle.')
      if jack_status != self.args.require_dongle:
        factory.console.info('Dongle Status is wrong.')
        raise ValueError('Dongle Status is wrong.')

    # Enable/disable devices according to require_dongle.
    # We don't use jack_status because jack_status may not be ready at early
    # stage.
    if self.args.require_dongle:
      self._audio_util.DisableSpeaker(self._out_card)
      self._audio_util.EnableHeadphone(self._out_card)
    else:
      self._audio_util.DisableHeadphone(self._out_card)
      self._audio_util.EnableSpeaker(self._out_card)

    self._audio_util.DisableDmic(self._in_card)
    self._audio_util.DisableMLBDmic(self._in_card)
    self._audio_util.DisableExtmic(self._in_card)
    if self._mic_source == MicSource.external:
      self._audio_util.EnableExtmic(self._in_card)
    elif self._mic_source == MicSource.panel:
      self._audio_util.EnableDmic(self._in_card)
    elif self._mic_source == MicSource.mlb:
      self._audio_util.EnableMLBDmic(self._in_card)

    # Run each tests to conduct under each output volume candidate.
    for self._output_volume_index, output_volume in enumerate(
        self._output_volumes):
      if self.args.require_dongle:
        self._audio_util.SetHeadphoneVolume(output_volume, self._out_card)
      else:
        self._audio_util.SetSpeakerVolume(output_volume, self._out_card)

      for test in self.args.tests_to_conduct:
        self._current_test_args = test
        if test['type'] == 'audiofun':
          self.AudioFunTest()
        elif test['type'] == 'sinewav':
          self.SinewavTest()
        elif test['type'] == 'noise':
          self.NoiseTest()
        else:
          raise ValueError('Test type "%s" not supported.' % test['type'])

      if self.MayPassTest():
        return

    self.FailTest()
