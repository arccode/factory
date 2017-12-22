// Copyright 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

class ToneGenerator {
  /**
   * Initializes tone generator.
   * @param {number} freq the default frequency in Hz
   * @param {number} freqMax the default max frequency in Hz
   */
  constructor(freq, freqMax) {
    this.osc = null;
    this.toneType = null;

    this.freqBar = document.getElementById('freq-bar');
    this.setFreqBarVal(this.freqBar.max * freq / freqMax);
    this.setFreq(freq);
    this.setFreqMax(freqMax);
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
    this.gainLeft.gain.setValueAtTime(0.5, 0);
    this.gainRight.gain.setValueAtTime(0.5, 0);
    this.merger.connect(this.audioContext.destination);
    this.started = false;
  }

  /**
   * Sets frequency to tone generator and UI.
   * @param {number} freq in Hz
   */
  setFreq(freq) {
    this.freq = freq;
    document.getElementById('freq-curr').innerText = freq;
    if (this.osc) {
      this.osc.frequency.setValueAtTime(freq, this.audioContext.currentTime);
    }
  }

  /**
   * Sets the value for frequency bar on UI.
   * @param {number} value
   */
  setFreqBarVal(value) {
    if (value < 1) {
      value = 1;
    }
    this.freqBar.value = value;
  }

  /**
   * Sets the max frequency to tone generator and UI.
   * @param {number} freqMax in Hz
   */
  setFreqMax(freqMax) {
    this.freqMax = freqMax;
    document.getElementById('freq-max-label').innerText = freqMax;
    document.getElementById('freq-max-edit').value = freqMax;
    if (freqMax < this.freq) {
      this.setFreq(freqMax);
      this.setFreqBarVal(this.freqBar.max);
    }
  }

  /**
   * Sets the tone type to tone generator.
   * @param {string} type of 'sine', 'square' or 'triangle'
   */
  setToneType(type) {
    this.toneType = type;
    if (this.osc) {
      this.osc.type = type;
    }
  }

  /**
   * Plays tone with given frequency, type and delay.
   * @param {number} freq in Hz
   * @param {string} type of 'sine', 'square' or 'triangle'
   * @param {number} delay in seconds
   */
  playTone(freq, type, delay) {
    this.osc = this.audioContext.createOscillator();
    this.osc.type = type;
    this.osc.frequency.setValueAtTime(freq, this.audioContext.currentTime);
    this.osc.connect(this.splitter);
    this.osc.start(delay);
    this.started = true;
  }

  /**
   * Stops the tone generator
   * @param {number} delay in seconds.
   */
  stopTone(delay) {
    this.osc.stop(delay);
    this.started = false;
  }
}

class Loopback {
  /**
   * Initializes audio loopback.
   * @param {MediaStream} stream the input media stream
   */
  constructor(stream) {
    this.audioContext = new AudioContext();
    this.src = this.audioContext.createMediaStreamSource(stream);
    this.started = false;
  }

  /**
   * Starts audio loopback.
   */
  start() {
    this.src.connect(this.audioContext.destination);
    this.started = true;
  }

  /**
   * Stops audio loopback.
   */
  stop() {
    this.src.disconnect();
    this.started = false;
  }
}

class Recorder {
  /**
   * Initializes recorder.
   * @param {MediaStream} stream the input media stream
   */
  constructor(stream) {
    this.audioContext = new AudioContext();
    this.src = this.audioContext.createMediaStreamSource(stream);
    this.processor = this.audioContext.createScriptProcessor(1024, 1, 1);
    this.buffers = [];
    this.recording = false;
    this.playing = false;
    this.playBufIndex = 0;
    this.playBufOffset = 0;

    this.processor.onaudioprocess = (e) => {
      this.process(e);
    };

    this.src.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
  }

  /**
   * Processes data to buffer when asked for recording, or plays the
   * stored data. This is the main callback of audio process event.
   * @param {Object} e the audio process event.
   */
  process(e) {
    if (this.recording) {
      const inBuf = e.inputBuffer.getChannelData(0);
      const tmp = new Float32Array(inBuf.length);
      tmp.set(inBuf, 0);
      this.buffers.push(tmp);
    } else if (this.playing) {
      const outBuf = e.outputBuffer.getChannelData(0);
      let playBuf = this.buffers[this.playBufIndex];

      for (let i = 0; i < outBuf.length; i++) {
        outBuf[i] = playBuf[this.playBufOffset++];
        if (this.playBufOffset >= playBuf.length) {
          this.playBufIndex++;
          this.playBufOffset = 0;
          if (this.playBufIndex >= this.buffers.length) {
            this.playBufIndex = 0;
            this.play(false);
            document.getElementById('record-playback-btn').className =
                'btn-off';
            break;
          } else {
            playBuf = this.buffers[this.playBufIndex];
          }
        }
      }
    }

    // Clean up buffer when not playing, to prevent short loop of audio.
    if (!this.playing) {
      const outBuf = e.outputBuffer.getChannelData(0);
      for (let i = 0; i < outBuf.length; i++) {
        outBuf[i] = 0;
      }
    }
  }

  /**
   * Configures the recording function on or off.
   * @param {boolean} on true to start recording, off otherwise.
   */
  record(on) {
    if (on) {
      this.buffers = [];
      this.recording = true;
    } else {
      this.recording = false;
    }
  }

  /**
   * Configures the playback function on or off.
   * @param {boolean} on true to start playback, off otherwise.
   */
  play(on) {
    this.playBufIndex = 0;
    this.playBufOffset = 0;
    if (on) {
      this.playing = true;
    } else {
      this.playing = false;
    }
  }
}

/**
 * Tone generator used to examine DUT's audio quality
 * at different frequencies.
 * @type {ToneGenerator}
 */
let toneGen = null;

/**
 * Audio loopback used to examine audio capture quality.
 * @type {Loopback}
 */
let loopback = null;

/**
 * Recorder for manual record and playback
 * @type {Recorder}
 */
let recorder = null;

/*
 * Register handler for UI events that is available after toneGen, loopback and
 * recorder are initialized.
 */
const registerHandlers = () => {
  const addListener = (id, type, callback) => {
    document.getElementById(id).addEventListener(type, function(event) {
      callback(this, event);
    });
  };

  addListener('left-gain', 'change', (ele) => {
    toneGen.gainLeft.gain.setValueAtTime(
        ele.value / ele.max, toneGen.audioContext.currentTime);
  });

  addListener('right-gain', 'change', (ele) => {
    toneGen.gainRight.gain.setValueAtTime(
        ele.value / ele.max, toneGen.audioContext.currentTime);
  });

  addListener('tone-type', 'change', (ele) => {
    toneGen.setToneType(ele.selectedOptions[0].value);
  });

  addListener('freq-bar', 'change', (ele) => {
    toneGen.setFreq(toneGen.freqMax * ele.value / ele.max);
  });

  addListener('tone-btn', 'click', (ele) => {
    if (toneGen.started) {
      toneGen.stopTone(0);
      ele.className = 'btn-off';
    } else {
      toneGen.playTone(toneGen.freq, toneGen.toneType, 0);
      ele.className = 'btn-on';
    }
  });

  addListener('loopback-btn', 'click', (ele) => {
    if (!loopback.started) {
      loopback.start();
      ele.className = 'btn-on';
    } else {
      loopback.stop();
      ele.className = 'btn-off';
    }
  });

  addListener('record-btn', 'click', (ele) => {
    if (recorder.playing) {
      recorder.play(false);
      document.getElementById('record-playback-btn').className = 'btn-off';
    }
    if (!recorder.recording) {
      recorder.record(true);
      ele.className = 'btn-on';
    } else {
      recorder.record(false);
      ele.className = 'btn-off';
    }
  });

  addListener('record-playback-btn', 'click', (ele) => {
    if (recorder.recording) {
      recorder.record(false);
      document.getElementById('record-btn').className = 'btn-off';
    }
    if (!recorder.playing) {
      recorder.play(true);
      ele.className = 'btn-on';
    } else {
      recorder.play(false);
      ele.className = 'btn-off';
    }
  });

  /**
   * Handles the event when max frequency label enters or
   * leaves edit mode.
   * @param {boolean} editMode if frequency label is in edit mode
   */
  const editMax = (editMode) => {
    // Display the label or edit text.
    const freq = document.getElementById('freq');
    const freqMaxEdit = document.getElementById('freq-max-edit');
    if (editMode) {
      freq.className = 'edit-on';
      freqMaxEdit.focus();
    } else {
      freq.className = 'edit-off';
      const fm = parseInt(freqMaxEdit.value, 10);
      // Restore the current max frequency and show on UI right before
      // an invalid value is found.
      toneGen.setFreqMax(isNaN(fm) ? toneGen.freqMax : fm);
    }
  };

  addListener('freq-max-label', 'click', () => {
    editMax(true);
  });

  addListener('freq-max-edit', 'blur', () => {
    editMax(false);
  });

  addListener('freq-max-edit', 'keydown', (ele, event) => {
    if (event.key === 'Enter') {
      editMax(false);
    }
  });
};

/**
 * Initializes client code and UI.
 */
const init = async () => {
  toneGen = new ToneGenerator(1000, 10000);
  try {
    // Init audio loopback
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    loopback = new Loopback(stream);
    recorder = new Recorder(stream);
    registerHandlers();
  } catch (e) {
    window.test.fail('Loopback failed to initialize');
  }
};

document.getElementById('pass-btn').addEventListener('click', () => {
  window.test.pass();
});

document.getElementById('fail-btn').addEventListener('click', () => {
  window.test.fail('Fail with bad audio quality');
});

/**
 * Shows cras nodes on UI.
 * @param {string} dir
 * @param {Array<{node_id: number, name: string, is_active: boolean}>} nodes
 */
const showCrasNodes = (dir, nodes) => {
  const panel = document.getElementById(`${dir}-nodes`);
  panel.innerHTML = '';

  for (const node of nodes) {
    const div = document.createElement('div');
    div.id = node['node_id'];
    div.innerText = node['name'];

    div.className = 'cras-node';
    if (!node['is_active']) {
      div.addEventListener('click', function() {
        window.test.sendTestEvent('select_cras_node', {id: node['node_id']});
      });
    } else {
      div.style.fontWeight = 'bold';
    }

    panel.appendChild(div);
  }
};

const exports = {
  init,
  showCrasNodes
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
