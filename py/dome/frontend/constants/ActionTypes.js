// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Enum from '../utils/enum';

export default Enum([
  'SWITCH_BOARD',
  'SWITCH_APP',

  // boards action
  'ADD_BOARD',
  'DELETE_BOARD',
  'RECEIVE_BOARDS',
  'UPDATE_BOARD',

  // form actions
  'OPEN_FORM',
  'CLOSE_FORM',

  // task actions
  'CREATE_TASK',
  'CHANGE_TASK_STATE',
  'REMOVE_TASK',

  // bundles action
  'ADD_BUNDLE',
  'DELETE_BUNDLE',
  'RECEIVE_BUNDLES',
  'REORDER_BUNDLES',
  'UPDATE_BUNDLE'
]);
