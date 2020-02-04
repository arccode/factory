// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const getDeviceId = async (device_name) => {
  if (!device_name) {
    return null;
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  for (const device of devices) {
    if (device.label === device_name) return device.deviceId;
  }
  throw new Error("Unable to find device: " + device_name);
};

const getConstraintFromId = (device_id) => {
  if (device_id == null) {
    return true;
  }
  return { deviceId: { exact: device_id } };
};

const getConstraintFromName = async (device_name) => {
  return getConstraintFromId(await getDeviceId(device_name));
};

const getMediaStream = async (audio_name, video_name) => {
  const constraints = {
    audio: await getConstraintFromName(audio_name),
    video: await getConstraintFromName(video_name)
  };
  return await navigator.mediaDevices.getUserMedia(constraints);
};

const setVideoSource =
      async (video_file, audio_name, video_name, time_limit) => {
  const video_tag = document.getElementById('v');
  if (video_file) {
    video_tag.src = video_file;
  } else {
    video_tag.srcObject = await getMediaStream(audio_name, video_name);
  }
};

const init =
      (video_file, audio_name, video_name, loop, time_limit, control_ui) => {
  const video_tag = document.getElementById('v');
  video_tag.loop = loop;
  video_tag.controls = control_ui;

  setVideoSource(video_file, audio_name, video_name, time_limit)
      .then(() => {
        setTimeout(() => window.test.pass(), time_limit * 1000);
        video_tag.play();
      })
      .catch((error) => window.test.fail(error.message));
};

const exports = {
  init
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
