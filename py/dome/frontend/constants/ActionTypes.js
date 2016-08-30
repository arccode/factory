// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// generic dome actions
export const SWITCH_BOARD = 'SWITCH_BOARD';
export const SWITCH_APP = 'SWITCH_APP';

// boards action
export const RECEIVE_BOARDS = 'RECEIVE_BOARDS';

// form actions
export const OPEN_FORM = 'OPEN_FORM';
export const CLOSE_FORM = 'CLOSE_FORM';

// task actions
export const CREATE_TASK = 'CREATE_TASK';
export const CHANGE_TASK_STATE = 'CHANGE_TASK_STATE';
export const REMOVE_TASK = 'REMOVE_TASK';

// bundles action
export const RECEIVE_BUNDLES = 'RECEIVE_BUNDLES';

export default {
  SWITCH_BOARD, SWITCH_APP,
  RECEIVE_BOARDS,
  OPEN_FORM, CLOSE_FORM,
  CREATE_TASK, CHANGE_TASK_STATE, REMOVE_TASK,
  RECEIVE_BUNDLES
};
