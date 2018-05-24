// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Enum from '../utils/enum';

export default Enum([
  'LOGIN_SUCCEED',
  'LOGIN_FAILED',
  'LOGOUT',

  'START_UPDATING_CONFIG',
  'FINISH_UPDATING_CONFIG',
  'RECIEVE_CONFIG',

  'SET_ERROR_MESSAGE',
  'SHOW_ERROR_DIALOG',
  'HIDE_ERROR_DIALOG',

  'SWITCH_PROJECT',
  'SWITCH_APP',

  // projects action
  'ADD_PROJECT',
  'DELETE_PROJECT',
  'RECEIVE_PROJECTS',
  'UPDATE_PROJECT',

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
  'UPDATE_BUNDLE',
  'EXPAND_BUNDLE',
  'COLLAPSE_BUNDLE',

  // service action
  'RECEIVE_SERVICE_SCHEMATA',
  'RECEIVE_SERVICES',
  'UPDATE_SERVICE',
]);
