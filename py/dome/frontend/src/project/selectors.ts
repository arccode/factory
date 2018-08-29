// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createSelector} from 'reselect';

import {RootState} from '@app/types';

import {displayedState} from '@common/optimistic_update';

import {NAME} from './constants';
import {ProjectState} from './reducer';
import {ProjectMap} from './types';

export const localState = (state: RootState): ProjectState =>
  displayedState(state)[NAME];

export const getProjects =
  (state: RootState): ProjectMap => localState(state).projects;
export const getCurrentProject =
  (state: RootState): string => localState(state).currentProject;
export const getCurrentProjectObject = createSelector(
  [getProjects, getCurrentProject],
  (projects, name) => name === '' ? null : projects[name]);
