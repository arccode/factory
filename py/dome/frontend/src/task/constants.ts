// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {TaskState} from './types';

export const NAME = 'task';

// TODO(pihsun): Pass the whole "task" object into TaskComponent.tsx, so helper
// functions like this can have task as argument instead of state.
export const isCancellable = (state: TaskState): boolean => {
  return state === 'WAITING' || state === 'FAILED';
};

export const isRunning = (state: TaskState): boolean => {
  return state === 'RUNNING_UPLOAD_FILE' || state === 'RUNNING_WAIT_RESPONSE';
};

export class CancelledTaskError extends Error {
  constructor() {
    super('Task cancelled');
    Object.setPrototypeOf(this, CancelledTaskError.prototype);
  }
}
