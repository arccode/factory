/* Copyright 2019 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

class AudioGraph {
  constructor(stream) {
    this.audioContext = new window.AudioContext();
    this.source = this.audioContext.createMediaStreamSource(stream);
    this.connectLinks();
    this.visualize();
  }

  connectLinks() {
    const audioContext = this.audioContext;
    const recorderChannel = [];
    const recorderGain = [];
    this.recorderGain = recorderGain;

    const sourceSplitter = audioContext.createChannelSplitter(2);
    const sourceMerger = audioContext.createChannelMerger(2);
    const recordStream = audioContext.createMediaStreamDestination();

    // Since we want to enable/disable left/right channel separately,
    // we first split audio source and connect them to two "gain" node.
    //
    // Analyser node is used to display waveform on the screen.
    //
    // source -> splitter ----> gain --> analyser ----> merger -> recordStream
    //                     `--> gain --> analyser --/
    this.source.connect(sourceSplitter);
    for (let i = 0; i < 2; i++) {
      const analyser = audioContext.createAnalyser();
      const gain = audioContext.createGain();
      recorderChannel.push(analyser);
      recorderGain.push(gain);
      sourceSplitter.connect(gain, i);
      gain.connect(analyser);
      analyser.connect(sourceMerger, 0, i);
    }
    sourceMerger.connect(recordStream);
    this.recordStream = recordStream;

    this.recorderChannel = recorderChannel;

    // Set up player
    // Similar to recorder, we split player signal so we can enable/disable
    // left/right channels separately.
    const playerSource = audioContext.createAnalyser();
    const playerGain = [];
    this.playerGain = playerGain;

    const playerSplitter = audioContext.createChannelSplitter(2);
    const playerMerger = audioContext.createChannelMerger(2);

    playerSource.connect(playerSplitter);
    for (let i = 0; i < 2; i++) {
      const gain = audioContext.createGain();
      playerGain.push(gain);
      playerSplitter.connect(gain, i);
      gain.connect(playerMerger, 0, i);
    }
    playerMerger.connect(audioContext.destination);

    this.playerSource = playerSource;
  }

  visualize() {
    const pairs = [
      {
        'canvas': document.getElementById('channel_l'),
        'analyser': this.recorderChannel[0]
      },
      {
        'canvas': document.getElementById('channel_r'),
        'analyser': this.recorderChannel[1]
      },
    ];

    const draw = () => {
      this.animationRequestId = requestAnimationFrame(draw);
      for (const {canvas, analyser} of pairs) {
        const canvasContext = canvas.getContext('2d');

        analyser.fftSize = 2048;
        const bufferSize = analyser.frequencyBinCount;
        const buffer = new Uint8Array(bufferSize);

        // Since we are using percentage for width and height, make it the real
        // value.
        canvas.width = canvas.clientWidth;
        canvas.height = canvas.clientHeight;

        const width = canvas.clientWidth;
        const height = canvas.clientHeight;

        analyser.getByteTimeDomainData(buffer);
        canvasContext.fillStyle = 'rgb(200, 200, 200)';
        canvasContext.fillRect(0, 0, width, height);
        canvasContext.lineWidth = 2;
        canvasContext.strokeStyle = 'rgb(0, 0, 0)';

        canvasContext.beginPath();

        const dx = width * 1.0 / bufferSize;

        for (let i = 0; i < bufferSize; i++) {
          const v = buffer[i] / 128.0;
          const y = v * height / 2;
          const x = i * dx;

          if (i === 0) {
            canvasContext.moveTo(x, y);
          } else {
            canvasContext.lineTo(x, y);
          }
        }

        canvasContext.lineTo(width, height / 2);
        canvasContext.stroke();
      }
    }

    if (this.animationRequestId) {
      window.cancelAnimationFrame(this.animationRequestId);
    }
    draw();
  }

  enableRecorder(id, enable) {
    this.recorderGain[id].gain.value = enable ? 1 : 0;
  }

  enablePlayer(id, enable) {
    this.playerGain[id].gain.value = enable ? 1 : 0;
  }
};

class Recorder {
  constructor(audioGraph) {
    this.audioGraph = audioGraph;
    this.recordedChunk = [];

    let stream = this.audioGraph.recordStream;
    if (stream instanceof MediaStreamAudioDestinationNode) {
      stream = stream.stream;
    }

    const mediaRecorder = new MediaRecorder(stream, {mimeType: 'audio/webm'});
    mediaRecorder.addEventListener('dataavailable', (e) => {
      console.log(e.data.size);
      if (e.data.size > 0)
        this.recordedChunk.push(e.data);
    });
    mediaRecorder.addEventListener('stop', (e) => {
      console.log(e);

      const blob = new Blob(this.recordedChunk, {'type': 'audio/webm'});
      const audioUrl = URL.createObjectURL(blob);
      console.log(audioUrl);

      const recordedAudio = document.getElementById('recorded_audio');
      recordedAudio.href = audioUrl;
    });
    this.mediaRecorder = mediaRecorder;
  }

  onRecordButtonClick(event) {
    if (this.mediaRecorder.state === 'recording') {
      console.log('stop recording');
      event.target.style.filter = '';
      // stop recording
      this.recording = false;
      this.mediaRecorder.stop();
    } else {
      console.log('start recording');
      event.target.style.filter = 'invert(100)';
      this.recording = true;
      this.recordedChunk = [];
      this.mediaRecorder.start();
    }
  }

  onPlayButtonClick(event) {
    if (this.recordedChunk.length === 0) {
      console.log('Nothing recorded, stop');
      return;
    }

    const fileReader = new FileReader();
    fileReader.onloadend = () => {
      const arrayBuffer = fileReader.result;
      this.audioGraph.audioContext.decodeAudioData(
        arrayBuffer,

        (buffer) => {
          console.log('recordedChunk decoded');
          const source = this.audioGraph.audioContext.createBufferSource();
          source.buffer = buffer;
          const playerSource = this.audioGraph.playerSource;
          source.connect(playerSource);

          source.onended = (endedEvent) => {
            console.log(endedEvent);
            event.target.style.filter = '';
          };

          event.target.style.filter = 'invert(100)';
          source.start(0);
        },

        (error) => {
          console.log(`failed to decode: ${error}`);
        }
      );
    };

    fileReader.readAsArrayBuffer(this.recordedChunk[0]);
  }
};

function onCheckboxChanged(e, audioGraph) {
  console.log(e);
  const checked = e.target.checked;
  const id = e.target.value;

  if (e.target.id.endsWith('mic')) {
    audioGraph.enableRecorder(id, checked);
  } else if (e.target.id.endsWith('spk')) {
    audioGraph.enablePlayer(id, checked);
  }
}

function patchBrowser() {
  // Older browsers might not implement mediaDevices at all, so we set an empty
  // object first
  if (navigator.mediaDevices === undefined) {
    navigator.mediaDevices = {};
  }

  // Some browsers partially implement mediaDevices. We can't just assign an
  // object with getUserMedia as it would overwrite existing properties.  Here,
  // we will just add the getUserMedia property if it's missing.
  if (navigator.mediaDevices.getUserMedia === undefined) {
    navigator.mediaDevices.getUserMedia = function(constraints) {

      // First get ahold of the legacy getUserMedia, if present
      var getUserMedia = (navigator.webkitGetUserMedia ||
                          navigator.mozGetUserMedia);

      // Some browsers just don't implement it - return a rejected promise with
      // an error to keep a consistent interface
      if (!getUserMedia) {
        return Promise.reject(
          new Error('getUserMedia is not implemented in this browser'));
      }

      // Otherwise, wrap the call to the old navigator.getUserMedia with a
      // Promise
      return new Promise(function(resolve, reject) {
        getUserMedia.call(navigator, constraints, resolve, reject);
      });
    }
  }
}

async function init() {
  console.log('init');
  patchBrowser();

  try {
    const constraints = {
      'audio': {
        'autoGainControl': false,
        'echoCancellation': false,
        'noiseSuppression': false,
      }
    };
    const stream = await navigator.mediaDevices.getUserMedia(constraints);

    const audioGraph = new AudioGraph(stream);
    const recorder = new Recorder(audioGraph);

    const buttonRecord = document.getElementById('record');
    buttonRecord.addEventListener(
        'click', (e) => recorder.onRecordButtonClick(e));

    const buttonSave = document.getElementById('save');
    buttonSave.addEventListener(
      'click', (e) => {
        const recordedAudio = document.getElementById('recorded_audio');
        if (recordedAudio.href) {
          recordedAudio.click();
        }
      });

    const buttonPlay = document.getElementById('play');
    buttonPlay.addEventListener(
      'click', (e) => recorder.onPlayButtonClick(e));

    ['enable_l_mic', 'enable_r_mic', 'enable_l_spk', 'enable_r_spk'].forEach(
      (id) => {
        const element = document.getElementById(id);
        element.addEventListener(
            'change', (e) => onCheckboxChanged(e, audioGraph));
      });
  } catch (err) {
    console.log(`Failed to get media. ${err}`);
  }
}

init();
