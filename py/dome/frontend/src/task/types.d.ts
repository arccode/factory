// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {AxiosResponse} from 'axios';

export type TaskState =
  'WAITING' |
  'RUNNING_UPLOAD_FILE' |
  'RUNNING_WAIT_RESPONSE' |
  'SUCCEEDED' |
  'FAILED';

export interface TaskProgress {
  uploadedSize: number;
  totalSize: number;
  uploadedFiles: number;
  totalFiles: number;
}

export interface Task {
  taskId: string;
  state: TaskState;
  description: string;
  method: string;
  url: string;
  progress: TaskProgress;
}
