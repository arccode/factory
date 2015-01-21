// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * Tone generator used to examine DUT's audio quality
 * at different frequencies.
 */
var toneGen = {};

/**
 * Initializes tone generator.
 * @param {int} freq the default frequency in Hz
 * @param {int} freq_max the default max frequency in Hz
 */
toneGen.init = function(freq, freq_max) {
  this.freq_bar = document.getElementById('freq_bar');
  this.setFreqBarVal(this.freq_bar.max * freq / freq_max);
  this.setFreq(freq);
  this.setFreqMax(freq_max);
  this.setToneType('sine');
  this.audioContext = new AudioContext();
  this.gainLeft = this.audioContext.createGain();
  this.gainRight = this.audioContext.createGain();
  this.splitter = this.audioContext.createChannelSplitter(2);
  this.merger = this.audioContext.createChannelMerger(2);
  this.splitter.connect(this.gainLeft);
  this.splitter.connect(this.gainRight);
  this.gainLeft.connect(this.merger, 0, 0);
  this.gainRight.connect(this.merger, 0, 1);
  this.gainLeft.gain.value = 0.5;
  this.gainRight.gain.value = 0.5;
  this.merger.connect(this.audioContext.destination);
}

/**
 * Sets value to the left gain of tonegen.
 * @param {int} value of the gain slider, max 20.
 */
function leftGain(val) {
  toneGen.gainLeft.gain.value = val / 20;
}

/**
 * Sets value to the right gain of tonegen.
 * @param {int} value of the gain slider, max 20.
 */
function rightGain(val) {
  toneGen.gainRight.gain.value = val / 20;
}

/**
 * Sets frequency to tone generator and UI.
 * @param {int} freq in Hz
 */
toneGen.setFreq = function(freq) {
  this.freq = freq;
  document.getElementById('freq_curr').innerText = freq;
  if (this.osc) {
    this.osc.frequency.value = freq;
  }
}

/**
 * Sets the value for frequency bar on UI.
 * @param {int} value
 */
toneGen.setFreqBarVal = function(value) {
  if (value < 1)
    value = 1;
  this.freq_bar.value = value;
}

/**
 * Sets the max frequency to tone generator and UI.
 * @param {int} freq_max in Hz
 */
toneGen.setFreqMax = function(freq_max) {
  this.freq_max = freq_max;
  document.getElementById('freq_max_label').innerText = freq_max;
  document.getElementById('freq_max_edit').value = freq_max;
  if (freq_max < this.freq) {
    this.setFreq(freq_max);
    this.setFreqBarVal(this.freq_bar.max);
  }
}

/**
 * Sets the tone type to tone generator.
 * @param {string} type of 'sine', 'square' or 'triangle'
 */
toneGen.setToneType = function(type) {
  toneGen.tone_type = type;
  if (this.osc) {
    this.osc.type = type;
  }
}

/**
 * Plays tone with given frequency, type and delay.
 * @param {int} freq in Hz
 * @param {string} type of 'sine', 'square' or 'triangle'
 * @param {int} delay in seconds
 */
toneGen.playTone = function(freq, type, delay) {
  this.osc = this.audioContext.createOscillator();
  this.osc.type = type;
  this.osc.frequency.value = freq;
  this.osc.connect(this.splitter);
  this.osc.start(delay);
}

/**
 * Returns if the tone generator is playing.
 */
toneGen.isPlaying = function() {
  return this.osc
      && this.osc.playbackState == this.osc.PLAYING_STATE;
}

/**
 * Stops the tone generator
 * @param {int} delay in seconds.
 */
toneGen.stopTone = function(delay) {
  this.osc.stop(delay);
}

/* Audio loopback used to examine audio capture quality. */
var loopback = {};

/**
 * Initializes audio loopback.
 * @param {Object} stream the input media stream
 */
loopback.init = function(stream) {
  this.audioContext = new AudioContext();
  this.src = this.audioContext.createMediaStreamSource(stream);
}

/**
 * Starts audio loopback.
 */
loopback.start = function() {
  this.src.connect(this.audioContext.destination);
  this.started = true;
}

/**
 * Stops audio loopback.
 */
loopback.stop = function() {
  this.src.disconnect();
  this.started = false;
}

/* Recorder for manual record and playback */
var recorder = {};


/**
 * Initializes recorder.
 * @param {Object} stream the input media stream
 */
recorder.init = function(stream) {
  this.audioContext = new AudioContext();
  this.src = this.audioContext.createMediaStreamSource(stream);
  this.processor = this.audioContext.createScriptProcessor(1024, 1, 1);
  this.buffers = [];
  this.recording = false;
  this.playing = false;
  this.play_buf_index = 0;
  this.play_buf_offset = 0;

  var self = this;
  this.processor.onaudioprocess = function(e) {
    self.process(e);
  };

  this.src.connect(this.processor);
  this.processor.connect(this.audioContext.destination);
}

/**
 * Processes data to buffer when asked for recording, or plays the
 * stored data. This is the main callback of audio process event.
 * @param {Object} e the audio process event.
 */
recorder.process = function(e) {
  if (this.recording) {
    var in_buf = e.inputBuffer.getChannelData(0);
    var tmp = new Float32Array(in_buf.length);
    tmp.set(in_buf, 0);
    this.buffers.push(tmp);
  } else if (this.playing) {
    var out_buf = e.outputBuffer.getChannelData(0);
    var play_buf = this.buffers[this.play_buf_index];

    for (var i = 0; i < out_buf.length; i++) {
      out_buf[i] = play_buf[this.play_buf_offset++];
      if (this.play_buf_offset >= play_buf.length) {
        this.play_buf_index++;
        this.play_buf_offset = 0;
        if (this.play_buf_index >= this.buffers.length) {
          this.play_buf_index = 0;
          this.play(false);
          document.getElementById('record_playback_btn').className ='btn-off';
          break;
        } else {
          play_buf = this.buffers[this.play_buf_index];
        }
      }
    }
  }

  // Clean up buffer when not playing, to prevent short loop of audio.
  if (!this.playing) {
    var out_buf = e.outputBuffer.getChannelData(0);
    for (var i = 0; i < out_buf.length; i++) {
      out_buf[i] = 0;
    }
  }
}

/**
 * Configrues the recording function on or off.
 * @param {boolean} on true to start recording, off otherwise.
 */
recorder.record = function(on) {
  if (on) {
    this.buffers = [];
    this.recording = true;
  } else {
    this.recording = false;
  }
}

/**
 * Configrues the playback function on or off.
 * @param {boolean} on true to start playback, off otherwise.
 */
recorder.play = function(on) {
  this.play_buf_index = 0;
  this.play_buf_offset = 0;
  if (on) {
    this.playing = true;
  } else {
    this.playing = false;
  }
}

/* Callback functions from UI */

/**
 * Initializes client code and UI.
 */
function init() {
  // Init tone generator
  toneGen.init(1000, 10000);

  // Init audio loopback
  var onErr = function() {
    alert('Loopback failed to initialize');
  }
  navigator.webkitGetUserMedia({audio:true}, gotStream, onErr);
}

/**
 * Handles the event when a media stream is acquired by
 * navigator.webkitGetUserMedia().
 * @param {Object} stream the input media stream
 */
function gotStream(stream) {
  loopback.init(stream);
  recorder.init(stream);
}

/**
 * Handles the event tone generator type is changed on UI.
 */
function toneTypeChanged() {
  var toneTypeSelector = document.getElementById('tone_type');
  toneGen.setToneType(
      toneTypeSelector.options[toneTypeSelector.selectedIndex].value);
}

/**
 * Handles the event value of frequency bar is changed.
 * @param {int} value the value of the frequency bar
 */
function freqBarChanged(value) {
  toneGen.setFreq(toneGen.freq_max * value / toneGen.freq_bar.max);
}

/**
 * Handles the event when tone generator button is clicked.
 */
function toneButtonClicked() {
  var btn = document.getElementById('tone_btn');
  if (toneGen.isPlaying()) {
    toneGen.stopTone(0);
    btn.className = 'btn-off';
  } else {
    toneGen.playTone(toneGen.freq, toneGen.tone_type, 0);
    btn.className = 'btn-on';
  }
}

/**
 * Handles the event when loopback button is clicked.
 */
function loopbackButtonClicked() {
  var btn = document.getElementById('loopback_btn');
  if (!loopback.started) {
    loopback.start();
    btn.className = 'btn-on';
  } else {
    loopback.stop();
    btn.className = 'btn-off';
  }
}

/**
 * Handles the event when record button is clicked.
 */
function recordButtonClicked() {
  var btn;

  if (recorder.playing) {
    recorder.play(false);
    btn = document.getElementById('record_playback_btn');
    btn.className = 'btn-off';
  }
  btn = document.getElementById('record_btn');
  if (!recorder.recording) {
    recorder.record(true);
    btn.className = 'btn-on';
  } else {
    recorder.record(false);
    btn.className = 'btn-off';
  }
}

/**
 * Handles the event when playback button is clicked.
 */
function recordPlaybackButtonClicked() {
  var btn;

  if (recorder.recording) {
    recorder.record(false);
    btn = document.getElementById('record_btn');
    btn.className = 'btn-off';
  }
  btn = document.getElementById('record_playback_btn');
  if (!recorder.playing) {
    recorder.play(true);
    btn.className = 'btn-on';
  } else {
    recorder.play(false);
    btn.className = 'btn-off';
  }
}

/**
 * Handles the event when max frequency label enters or
 * leaves edit mode.
 * @param {boolean} edit_mode if frequency label is in edit mode
 */
function editMax(edit_mode) {
  console.info('Calling edit max with ' + edit_mode);
  // Display the label or edit text.
  var freq = document.getElementById('freq');
  var freq_max_edit = document.getElementById('freq_max_edit');
  freq.className = edit_mode ? 'edit-on' : 'edit-off';
  if (edit_mode)
    freq_max_edit.focus();

  var fm = parseInt(freq_max_edit.value);
  if (edit_mode || isNaN(fm)) {
    // Restore the current max frequency and show on UI right before
    // user tries to modify it or an invalid value is found.
    fm = toneGen.freq_max;
    freq_max_edit.value = toneGen.freq_max;
  }
  toneGen.setFreqMax(fm);
}

/**
 * Handles the event when fail button is clicked.
 */
function fail() {
  test.sendTestEvent('fail', {});
}

/**
 * Handles the event when pass button is clicked.
 */
function pass() {
  test.sendTestEvent('pass', {});
}

/**
 * Selects to certain cras node.
 */
function selectCrasNode(node_div) {
  test.sendTestEvent('select_cras_node', {'id': node_div.id});
}

/**
 * Shows cras nodes on UI.
 */
function showCrasNodes(dir, nodes_json) {
  console.info(nodes_json);
  nodes = eval(nodes_json);

  var panel = document.getElementById(dir + '-nodes');
  panel.innerHTML = '';

  for (var i = 0; i < nodes.length; i++) {
    var div = document.createElement('div');
    div.id = nodes[i]['node_id'];
    div.innerText = nodes[i]['name'];
    panel.appendChild(div);
  }

  for (var i = 0; i < nodes.length; i++) {
    var n = document.getElementById(nodes[i]['node_id']);
    n.className = 'cras-node';
    if (nodes[i]['name'].indexOf('*') == -1) {
      n.onclick = function() {
        selectCrasNode(this);
      }
    } else {
      n.style.fontWeight = 'bold';
    }
  }
}
