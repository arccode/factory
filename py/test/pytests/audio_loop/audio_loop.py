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

Here are some test list examples for different test cases::

    # Audiofuntest for all mics of input_dev and all speakers of output_dev.
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

    # Audiofuntest on 'mlb' mics of input_dev and speaker channel 0 of
    # output_dev.
    OperatorTest(
        id='Speaker0DMicMlb',
        label_zh=u'喇叭0/MLB麦克风',
        pytest_name='audio_loop',
        dargs={'require_dongle': False,
               'check_dongle': True,
               'output_volume': 10,
               'initial_actions': [('1', 'init_speakerdmic')],
               'mic_source': 'mlb',
               'input_dev': ('Audio Card', '0'),
               'output_dev': ('Audio Card', '0'),
               'tests_to_conduct': [{'type': 'audiofun',
                                     'capture_rate': 16000,
                                     'output_channels': [0],
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
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.device.audio import base
from cros.factory.device import device_utils
from cros.factory.test import event as test_event
from cros.factory.test import factory
from cros.factory.test import test_ui
from cros.factory.test import ui_templates
from cros.factory.test.utils import audio_utils
from cros.factory.utils.arg_utils import Arg
from cros.factory.utils import process_utils
from cros.factory.utils import type_utils

# Default setting
_DEFAULT_FREQ_HZ = 1000

# the duration(secs) for sine tone to playback.
# it must be long enough for record process.
_DEFAULT_SINEWAV_DURATION = 10

# Regular expressions to match audiofuntest message.
_AUDIOFUNTEST_MIC_CHANNEL_RE = re.compile(r'.*Microphone channels:\s*(.*)$')
_AUDIOFUNTEST_SUCCESS_RATE_RE = re.compile(
    r'.*channel\s*=\s*([0-9]*),.*rate\s*=\s*(.*)$')
_AUDIOFUNTEST_RUN_START_RE = re.compile('^carrier')

# Default minimum success rate of audiofun test to pass.
_DEFAULT_AUDIOFUN_TEST_THRESHOLD = 50
# Default iterations to do the audiofun test.
_DEFAULT_AUDIOFUN_TEST_ITERATION = 10
# Default duration to do the sinewav test, in seconds.
_DEFAULT_SINEWAV_TEST_DURATION = 2
# Default frequency tolerance, in Hz.
_DEFAULT_SINEWAV_FREQ_THRESHOLD = 50
# Default duration to do the noise test, in seconds.
_DEFAULT_NOISE_TEST_DURATION = 1
# Default RMS thresholds when checking recorded file.
_DEFAULT_SOX_RMS_THRESHOLD = (0.08, None)
# Default Amplitude thresholds when checking recorded file.
_DEFAULT_SOX_AMPLITUDE_THRESHOLD = (None, None)
# Default channels of the input_dev to be tested.
_DEFAULT_AUDIOFUN_TEST_INPUT_CHANNELS = [0, 1]
# Default channels of the output_dev to be tested.
_DEFAULT_AUDIOFUN_TEST_OUTPUT_CHANNELS = [0, 1]
# Default capture sample rate used for audiofuntest.
_DEFAULT_AUDIOFUN_TEST_SAMPLE_RATE = 48000
# Default duration in seconds to trim in the beginning of recorded file.
_DEFAULT_TRIM_SECONDS = 0.5

_UI_HTML = """
<h1 id="message" style="position:absolute; top:45%">
<center style="font-size: 20pt">
    <div id="test_title">
    </div>
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

MicSource = type_utils.Enum(['external', 'panel', 'mlb'])


class AudioLoopTest(unittest.TestCase):
  """Audio Loop test to test two kind of situations.
  1. Speaker to digital microphone.
  2. Headphone out to headphone in.
  """
  ARGS = [
      Arg('audio_conf', str, 'Audio config file path', None, optional=True),
      Arg('initial_actions', list, 'List of tuple (card, actions)', []),
      Arg('input_dev', tuple,
          'Input ALSA device. (card_name, sub_device).'
          'For example: ("audio_card", "0").', ('0', '0')),
      Arg('num_input_channels', int,
          'Number of input channels.', default=2),
      Arg('output_dev', tuple,
          'Onput ALSA device. (card_name, sub_device).'
          'For example: ("audio_card", "0").', ('0', '0')),
      Arg('output_volume', (int, list),
          'An int of output volume or a list of'
          ' output volume candidates', 10),
      Arg('autostart', bool, 'Auto start option', False),
      Arg('require_dongle', bool, 'Require dongle option', False),
      Arg('check_dongle', bool,
          'Check dongle status whether match require_dongle', False),
      Arg('check_cras', bool, 'Do we need to check if CRAS is running',
          True),
      Arg('cras_enabled', bool, 'Whether cras should be running or not',
          False),
      Arg('mic_source', str, 'Microphone source: external, panel, mlb',
          'external'),
      Arg('test_title', str,
          'Title on the test screen.'
          'It can be used to tell operators the test info'
          'For example: "LRGM Mic", "LRMG Mic"', ''),
      Arg('mic_jack_type', str, 'Microphone jack Type: nocheck, lrgm, lrmg',
          'nocheck'),
      Arg('audiofuntest_run_delay', (int, float),
          'Delay between consecutive calls to audiofuntest',
          default=None, optional=True),
      Arg('tests_to_conduct', list,
          'A list of dicts. A dict should contain at least one key named\n'
          '**type** indicating the test type, which can be **audiofun**,\n'
          '**sinewav**, or **noise**.\n'
          '\n'
          'If type is **audiofun**, the dict can optionally contain:\n'
          '  - **iteration**: Iterations to run the test.\n'
          '  - **threshold**: The minimum success rate to pass the test.\n'
          '  - **input_channels**: A list of input channels to be tested.\n'
          '  - **output_channels**: A list of output channels to be tested.\n'
          '  - **capture_rate**: The capturing sample rate use for testing.\n'
          '\n'
          'If type is **sinewav**, the dict can optionally contain:\n'
          '  - **duration**: The test duration, in seconds.\n'
          '  - **freq_threshold**: Acceptable frequency margin.\n'
          '  - **rms_threshold**: A tuple of **(min, max)** that will make\n'
          '        sure the following inequality is true: *min <= recorded\n'
          '        audio RMS (root mean square) value <= max*, otherwise,\n'
          '        fail the test.  Both of **min** and **max** can be set to\n'
          '        None, which means no limit.\n'
          '  - **amplitude_threshold**: A tuple of (min, max) and it will\n'
          '        make sure the inequality is true: *min <= minimum measured\n'
          '        amplitude <= maximum measured amplitude <= max*,\n'
          '        otherwise, fail the test.  Both of **min** and **max** can\n'
          '        be set to None, which means no limit.\n'
          '\n'
          'If type is **noise**, the dict can optionally contain:\n'
          '  - **duration**: The test duration, in seconds.\n'
          '  - **rms_threshold**: A tuple of **(min, max)** that will make\n'
          '        sure the following inequality is true: *min <= recorded\n'
          '        audio RMS (root mean square) value <= max*, otherwise,\n'
          '        fail the test.  Both of **min** and **max** can be set to\n'
          '        None, which means no limit.\n'
          '  - **amplitude_threshold**: A tuple of (min, max) and it will\n'
          '        make sure the inequality is true: *min <= minimum measured\n'
          '        amplitude <= maximum measured amplitude <= max*,\n'
          '        otherwise, fail the test.  Both of **min** and **max** can\n'
          '        be set to None, which means no limit.', optional=False)]

  def setUp(self):
    self._dut = device_utils.CreateDUTInterface()
    if self.args.audio_conf:
      self._dut.audio.ApplyConfig(self.args.audio_conf)

    # Tansfer input and output device format
    self._in_card = self._dut.audio.GetCardIndexByName(self.args.input_dev[0])
    self._in_device = self.args.input_dev[1]
    self._out_card = self._dut.audio.GetCardIndexByName(self.args.output_dev[0])
    self._out_device = self.args.output_dev[1]

    # Backward compatible for non-porting case, which use ALSA device name.
    # only works on chromebook device
    # TODO(mojahsu) Remove them later.
    self._alsa_input_device = 'hw:%s,%s' % (self._in_card, self._in_device)
    self._alsa_output_device = 'hw:%s,%s' % (self._out_card, self._out_device)

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

    self._mic_source = {
        'external': MicSource.external,
        'panel': MicSource.panel,
        'mlb': MicSource.mlb
    }[self.args.mic_source]

    self._mic_jack_type = {
        'nocheck': None,
        'lrgm': base.MicJackType.lrgm,
        'lrmg': base.MicJackType.lrmg
    }[self.args.mic_jack_type]

    for card, action in self.args.initial_actions:
      if card.isdigit() is False:
        card = self._dut.audio.GetCardIndexByName(card)
      self._dut.audio.ApplyAudioConfig(action, card)

    self._current_test_args = None

    # Setup HTML UI
    self._ui = test_ui.UI()
    self._ui_template = ui_templates.OneSection(self._ui)
    self._ui_template.SetState(_UI_HTML)

    if self.args.check_cras:
      # Check cras status
      if self.args.cras_enabled:
        cras_status = 'start/running'
      else:
        cras_status = 'stop/waiting'
      if cras_status not in self._dut.CallOutput(['status', 'cras']):
        self._ui.Fail('cras status is wrong (expected status: %s). '
                      'Please make sure that you have appropriate setting for '
                      '"disable_services=[\'cras\']" in the test item.' %
                      cras_status)
    self._dut_temp_dir = self._dut.temp.mktemp(True, '', 'audio_loop')

  def tearDown(self):
    self._dut.audio.RestoreMixerControls()
    self._dut.CheckCall(['rm', '-rf', self._dut_temp_dir])

  def runTest(self):
    # If autostart, JS triggers start_run_test event.
    # Otherwise, it binds start_run_test with 's' key pressed.
    self._ui.CallJSFunction('init',
                            self.args.require_dongle, self.args.test_title)
    if self.args.autostart:
      self._ui.RunJS('document.getElementById("message").innerHTML = "";')
      self._ui.AddEventHandler('start_run_test', self.StartRunTest)
      self._ui.PostEvent(test_event.Event(test_event.Event.Type.TEST_UI_EVENT,
                                          subtype='start_run_test'))
    else:
      self._ui.BindKey('S', self.StartRunTest, once=True)
    self._ui.Run()

  def AppendErrorMessage(self, error_message):
    """Sets the test result to fail and append a new error message."""
    self._test_results[self._output_volume_index] = False
    self._test_message.append(
        'Under output volume %r' % self._output_volumes[
            self._output_volume_index])
    self._test_message.append(error_message)
    factory.console.error(error_message)

  def _MatchPatternLines(self, in_stream, re_pattern, num_lines=None):
    """Try to match the re pattern in the given number of lines.

    Try to read lines one-by-one from input stream and perform re matching.
    Stop when matching successes or reaching the number of lines limit.

    Args:
      in_stream: input stream to read from.
      re_pattern: re pattern used for matching.
      num_lines: maximum number of lines to stop for matching.
          None for read until end of input stream.
    """
    num_read = 0
    while True:
      line = in_stream.readline()
      if not line:
        return None
      num_read += 1
      m = re_pattern.match(line)
      if m is not None:
        return m
      if num_lines is not None and num_read >= num_lines:
        return None

  def _ParseSingleRunOutput(self, audiofun_output, num_mic_channel):
    """Parse a single run output from audiofuntest

    Sample single run output:
    O: channel =  0, success =   1, fail =   0, rate = 100.0
    X: channel =  1, success =   0, fail =   1, rate = 0.0

    Args:
      audiofun_output: output stream of audiofuntest to parse from
      num_mic_channel: number of mics
    """

    all_channel_rate = []
    for expected_channel in range(0, num_mic_channel):
      m = self._MatchPatternLines(
          audiofun_output, _AUDIOFUNTEST_SUCCESS_RATE_RE, 1)
      if m is None or int(m.group(1)) != expected_channel:
        self.AppendErrorMessage(
            'Failed to get expected %d channel output from audiofuntest'
            % expected_channel)
        return None
      all_channel_rate.append(float(m.group(2)))
    return all_channel_rate

  def AudioFunTestWithOutputChannel(self, capture_rate, input_channels,
                                    output_channel):
    """Runs audiofuntest program to get the frequency from microphone
    immediately according to speaker and microphone setting.

    Sample audiofuntest message:
    Config values.
            Player parameter: aplay -r 48000 -f s16 -t raw -c 2 -B 0 -
            Recorder parameter: arecord -r 48000 -f s16 -t raw -c 2 -B 0 -
            Player FIFO name:
            Recorder FIFO name:
            Number of test rounds: 20
            Pass threshold: 3
            Allowed delay: 1200(ms)
            Sample rate: 48000
            FFT size: 2048
            Microphone channels: 2
            Speaker channels: 2
            Microphone active channels: 0, 1,
            Speaker active channels: 0, 1,
            Tone length (in second): 3.00
            Volume range: 1.00 ~ 1.00
    carrier = 119
    O: channel =  0, success =   1, fail =   0, rate = 100.0
    X: channel =  1, success =   0, fail =   1, rate = 0.0
    carrier = 89
    O: channel =  0, success =   2, fail =   0, rate = 100.0
    X: channel =  1, success =   1, fail =   1, rate = 50.0

    Args:
      output_channel: output device channel used for testing
    """

    factory.console.info('Test output channel %d', output_channel)

    iteration = self._current_test_args.get(
        'iteration', _DEFAULT_AUDIOFUN_TEST_ITERATION)

    player_cmd = 'aplay -D %s -r %d -f s16 -t raw -c 2 -B 0 -' % (
        self._alsa_output_device, capture_rate)
    recorder_cmd = 'arecord -D %s -r %d -f s16 -t raw -c %d -B 0 -' % (
        self._alsa_input_device, capture_rate,
        self.args.num_input_channels)

    process = self._dut.Popen(
        [audio_utils.AUDIOFUNTEST_PATH,
         '-P', player_cmd,
         '-R', recorder_cmd,
         '-r', '%d' % capture_rate,
         '-T', '%d' % iteration,
         '-a', '%d' % output_channel,
         '-c', '%d' % self.args.num_input_channels],
        stdout=process_utils.PIPE, stderr=process_utils.PIPE)

    m = self._MatchPatternLines(process.stdout, _AUDIOFUNTEST_MIC_CHANNEL_RE)

    if m is None:
      self.AppendErrorMessage(
          'Number of channels not found from audiofuntest')
      process.terminate()
      return

    num_mic = int(m.group(1))

    last_success_rate = None
    while self._MatchPatternLines(process.stdout,
                                  _AUDIOFUNTEST_RUN_START_RE) is not None:
      last_success_rate = self._ParseSingleRunOutput(process.stdout, num_mic)
      if last_success_rate is None:
        self.AppendErrorMessage('Failed to parse audiofuntest output')
        return
      rate_msg = ', '.join(
          'Mic %d: %.1f%%' %
          (channel, rate) for channel, rate in enumerate(last_success_rate))
      self._ui.CallJSFunction('testInProgress', rate_msg)

    threshold = self._current_test_args.get(
        'threshold', _DEFAULT_AUDIOFUN_TEST_THRESHOLD)
    if any(rate < threshold and channel in input_channels
           for channel, rate in enumerate(last_success_rate)):
      self.AppendErrorMessage(
          'For output device channel %s, the success rate is "'
          '%s", too low!' % (output_channel, rate_msg))
      self._ui.CallJSFunction('testFailResult', rate_msg)
    time.sleep(1)

  def AudioFunTest(self):
    """Setup speaker and microphone test pairs and run audiofuntest program."""

    factory.console.info('Run audiofuntest from %r to %r',
                         self._alsa_output_device, self._alsa_input_device)

    input_channels = self._current_test_args.get(
        'input_channels', _DEFAULT_AUDIOFUN_TEST_INPUT_CHANNELS)
    output_channels = self._current_test_args.get(
        'output_channels', _DEFAULT_AUDIOFUN_TEST_OUTPUT_CHANNELS)
    capture_rate = self._current_test_args.get(
        'capture_rate', _DEFAULT_AUDIOFUN_TEST_SAMPLE_RATE)
    for output_channel in output_channels:
      self.AudioFunTestWithOutputChannel(capture_rate, input_channels,
                                         output_channel)
      if self.args.audiofuntest_run_delay is not None:
        time.sleep(self.args.audiofuntest_run_delay)

  def TestLoopbackChannel(self, num_channels):
    """Tests loopback on all channels.

    Args:
      num_channels: Number of channels to test
    """
    # TODO(phoenixshen): Support quad channels here.
    # This test assumes number of input channels == number of output channels,
    # and ID of valid channels should be the same,
    # Need to redesign the args to provide more flexbility.
    duration = self._current_test_args.get('duration',
                                           _DEFAULT_SINEWAV_TEST_DURATION)

    for channel in xrange(num_channels):
      # file path in host
      record_file_path = '/tmp/record-%d-%d-%s.raw' % (
          self._output_volumes[self._output_volume_index],
          channel, time.time())
      sine_wav_path = '/tmp/%d_%d.wav' % (self._freq, channel)
      dut_sine_wav_path = self._dut.path.join(self._dut_temp_dir,
                                              'sine_%d.wav' % channel)
      factory.console.info('DUT sine wav path %s', dut_sine_wav_path)

      # Generate sine .wav file locally and push it to the DUT.
      # It's hard to estimate the overhead in audio record thing of different
      # platform, To make sure we can record the whole sine tone in the record
      # duration, we will playback a long period sine tone, and stop the
      # playback process after we finish recording.
      cmd = audio_utils.GetGenerateSineWavArgs(sine_wav_path, channel,
                                               self._freq,
                                               _DEFAULT_SINEWAV_DURATION)
      process_utils.Spawn(cmd.split(' '), log=True, check_call=True)
      self._dut.link.Push(sine_wav_path, dut_sine_wav_path)

      self._dut.audio.PlaybackWavFile(dut_sine_wav_path, self._out_card,
                                      self._out_device, False)
      self.RecordFile(duration, record_file_path)
      self._dut.audio.StopPlaybackWavFile()

      sox_output = audio_utils.SoxStatOutput(record_file_path, channel)
      self.CheckRecordedAudio(sox_output)

      os.unlink(record_file_path)

  def SinewavTest(self):
    self._ui.CallJSFunction('testInProgress', None)

    # Playback sine tone and check the recorded audio frequency.
    self.TestLoopbackChannel(audio_utils.DEFAULT_NUM_CHANNELS)

  def NoiseTest(self):
    self._ui.CallJSFunction('testInProgress', None)
    # Record the noise file.
    duration = self._current_test_args.get(
        'duration', _DEFAULT_NOISE_TEST_DURATION)
    noise_file_path = '/tmp/noise-%s.wav' % time.time()
    # Do not trim because we want to check all possible noises and artifacts.
    self.RecordFile(duration, noise_file_path, None)

    # Since we have actually only 1 channel, we can just give channel=0 here.
    sox_output = audio_utils.SoxStatOutput(noise_file_path, 0)
    self.CheckRecordedAudio(sox_output)
    os.unlink(noise_file_path)

  def RecordFile(self, duration, file_path, trim=_DEFAULT_TRIM_SECONDS):
    """Records file for *duration* seconds.

    The caller is responsible for removing the file at last.

    Args:
      duration: Recording duration, in seconds.
      file_path: The file path to recorded file in host.
      trim: If not None, the number of seconds in the beginning to trim.
    """
    factory.console.info('RecordFile : %s.', file_path)
    record_path = (tempfile.NamedTemporaryFile(delete=False).name if trim
                   else file_path)
    with self._dut.temp.TempFile() as dut_record_path:
      self._dut.audio.RecordRawFile(dut_record_path, self._in_card,
                                    self._in_device, duration, 2, 48000)
      self._dut.link.Pull(dut_record_path, record_path)

    if trim:
      audio_utils.TrimAudioFile(in_path=record_path, out_path=file_path,
                                start=trim, end=None, num_channel=2)
      os.unlink(record_path)

  def CheckRecordedAudio(self, sox_output):
    rms_value = audio_utils.GetAudioRms(sox_output)
    factory.console.info('Got audio RMS value: %f.', rms_value)
    rms_threshold = self._current_test_args.get(
        'rms_threshold', _DEFAULT_SOX_RMS_THRESHOLD)
    if rms_threshold[0] is not None and rms_threshold[0] > rms_value:
      self.AppendErrorMessage('Audio RMS value %f too low. Minimum pass is %f.'
                              % (rms_value, rms_threshold[0]))
    if rms_threshold[1] is not None and rms_threshold[1] < rms_value:
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
      factory.console.info('Extected frequency %r +- %d',
                           self._freq, freq_threshold)
      if freq is None or (abs(freq - self._freq) > freq_threshold):
        self.AppendErrorMessage('Test Fail at frequency %r' % freq)
      else:
        factory.console.info('Got frequency %d', freq)

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

  def CheckDongleStatus(self):
    # When audio jack detection feature is ready on a platform, we can
    # enable check_dongle option to check jack status matches we expected.
    if self.args.check_dongle:
      mic_status = self._dut.audio.GetMicJackStatus(self._in_card)
      headphone_status = self._dut.audio.GetHeadphoneJackStatus(self._out_card)
      plug_status = mic_status or headphone_status
      # We've encountered false positive running audiofuntest tool against
      # audio fun-plug on a few platforms; so it is suggested not to run
      # audiofuntest with HP/MIC jack
      if plug_status is True:
        if any((t['type'] == 'audiofun') for t in self.args.tests_to_conduct):
          factory.console.info('Audiofuntest does not require dongle.')
          raise ValueError('Audiofuntest does not require dongle.')
        if self.args.require_dongle is False:
          factory.console.info('Dongle Status is wrong, don\'t need dongle.')
          raise ValueError('Dongle Status is wrong.')

      # for require dongle case, we need to check both microphone and headphone
      # are all detected.
      if self.args.require_dongle:
        if (mic_status and headphone_status) is False:
          factory.console.info('Dongle Status is wrong. mic %s, headphone %s',
                               mic_status, headphone_status)
          raise ValueError('Dongle Status is wrong.')

    if self._mic_jack_type:
      mictype = self._dut.audio.GetMicJackType(self._in_card)
      if mictype != self._mic_jack_type:
        factory.console.info('Mic Jack Type is wrong. need %s, but %s',
                             self._mic_jack_type,
                             mictype)
        raise ValueError('Mic Jack Type is wrong.')

  def SetupAudio(self):
    # Enable/disable devices according to require_dongle.
    # We don't use plug_status because plug_status may not be ready at early
    # stage.
    if self.args.require_dongle:
      self._dut.audio.DisableSpeaker(self._out_card)
      self._dut.audio.EnableHeadphone(self._out_card)
    else:
      self._dut.audio.DisableHeadphone(self._out_card)
      self._dut.audio.EnableSpeaker(self._out_card)

    self._dut.audio.DisableAllAudioInputs(self._in_card)
    if self._mic_source == MicSource.external:
      self._dut.audio.EnableExtmic(self._in_card)
    elif self._mic_source == MicSource.panel:
      self._dut.audio.EnableDmic(self._in_card)
    elif self._mic_source == MicSource.mlb:
      self._dut.audio.EnableMLBDmic(self._in_card)

  def StartRunTest(self, event):
    del event  # Unused.
    self.CheckDongleStatus()
    self.SetupAudio()

    # Run each tests to conduct under each output volume candidate.
    for self._output_volume_index, output_volume in enumerate(
        self._output_volumes):
      if self.args.require_dongle:
        self._dut.audio.SetHeadphoneVolume(output_volume, self._out_card)
      else:
        self._dut.audio.SetSpeakerVolume(output_volume, self._out_card)

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
