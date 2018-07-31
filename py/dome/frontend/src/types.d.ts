// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {AnyAction} from 'redux';
import {ThunkDispatch} from 'redux-thunk';
import {StateType} from 'typesafe-actions';

import rootReducer from './root_reducer';

export type RootState = StateType<typeof rootReducer>;
// TODO(pihsun): Have an action type that is union of all possible action?
export type Dispatch = ThunkDispatch<RootState, {}, AnyAction>;
