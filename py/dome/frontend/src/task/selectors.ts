// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {RootState} from '@app/types';

import {NAME} from './constants';
import {TaskState} from './reducer';
import {Task} from './types';

export const localState = (state: RootState): TaskState => state[NAME];

export const getAllTasks =
  (state: RootState): Task[] => localState(state).tasks;
