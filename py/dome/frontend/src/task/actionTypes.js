// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Enum from '../common/enum';

// TODO(pihsun): Use some library to handle this? E.g. redux-actions.
export default Enum([
  'CREATE_TASK',
  'CHANGE_TASK_STATE',
  'DISMISS_TASK',
]);
