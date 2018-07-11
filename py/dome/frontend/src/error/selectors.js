// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {NAME} from './constants';

export const localState = (state) => state[NAME];

export const isErrorDialogShown = (state) => localState(state).show;
export const getErrorMessage = (state) => localState(state).message;
