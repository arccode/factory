// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import axios from 'axios';
import {createAction} from 'typesafe-actions';

import {Dispatch} from '@app/types';

import {AppName, DomeInfo} from '@app/dome_app/types';

export const switchApp = createAction('SWITCH_APP', (resolve) =>
  (nextApp: AppName) => resolve({nextApp}));

export const setDomeInfo = createAction('SET_DOME_INFO', (resolve) =>
  (domeInfo: DomeInfo) => resolve({domeInfo}));

export const basicActions = {switchApp, setDomeInfo};

export const fetchDomeInfo = () => async (dispatch: Dispatch) => {
  try {
    const response = await axios.get<DomeInfo>('/info');
    dispatch(setDomeInfo(response.data));
  } catch (err) {
    console.error('Can not get Dome info...');
  }
};
