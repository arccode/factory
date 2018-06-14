// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Enum from '@common/enum';

export const NAME = 'task';

export const TaskStates = Enum([
  'WAITING',
  'RUNNING_UPLOAD_FILE',
  'RUNNING_WAIT_RESPONSE',
  'SUCCEEDED',
  'FAILED',
]);

// TODO(pihsun): Pass the whole "task" object into Task.js, so helper functions
// like this can have task as argument instead of state.
export const isCancellable = (state) => {
  return state === TaskStates.WAITING || state === TaskStates.FAILED;
};

export const isRunning = (state) => {
  return state === TaskStates.RUNNING_UPLOAD_FILE ||
      state === TaskStates.RUNNING_WAIT_RESPONSE;
};
