// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export const SWITCH_BOARD = 'SWITCH_BOARD';
export const SWITCH_APP = 'SWITCH_APP';
export const RECEIVE_BOARDS = 'RECEIVE_BOARDS';

// form actions
export const OPEN_FORM = 'OPEN_FORM';
export const CLOSE_FORM = 'CLOSE_FORM';

// uploading task actions
export const CREATE_UPLOADING_TASK = 'CREATE_UPLOADING_TASK';
export const CHANGE_UPLOADING_TASK_STATE = 'CHANGE_UPLOADING_TASK_STATE';
export const REMOVE_UPLOADING_TASK = 'REMOVE_UPLOADING_TASK';

// bundles actions
export const REQUEST_BUNDLES = 'REQUEST_BUNDLES';
export const RECEIVE_BUNDLES = 'RECEIVE_BUNDLES';

export default {
  SWITCH_BOARD, SWITCH_APP, RECEIVE_BOARDS,
  OPEN_FORM, CLOSE_FORM,
  CREATE_UPLOADING_TASK, CHANGE_UPLOADING_TASK_STATE, REMOVE_UPLOADING_TASK,
  REQUEST_BUNDLES, RECEIVE_BUNDLES
};
