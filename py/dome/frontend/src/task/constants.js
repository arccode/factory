// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Enum from '../common/enum';

export const TaskStates = Enum([
  'WAITING',
  'RUNNING_UPLOAD_FILE',
  'RUNNING_WAIT_RESPONSE',
  'SUCCEEDED',
  'FAILED',
]);
