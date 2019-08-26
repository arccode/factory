// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import produce from 'immer';
import {combineReducers} from 'redux';
import {ActionType, getType} from 'typesafe-actions';

import {basicActions as actions} from './actions';
import {
  ExpansionMap,
  PileMap,
} from './types';

export interface LogState {
  defaultDownloadDate: string;
  expanded: ExpansionMap;
  piles: PileMap;
}

type LogAction = ActionType<typeof actions>;

const expandReducer = produce(
  (draft: ExpansionMap, action: LogAction) => {
    switch (action.type) {
      case getType(actions.expandLogPile): {
        const {key} = action.payload;
        draft[key] = true;
        return;
      }

      case getType(actions.collapseLogPile): {
        const {key} = action.payload;
        draft[key] = false;
        return;
      }

      case getType(actions.addLogPile): {
        const {key} = action.payload;
        draft[key] = true;
        return;
      }

      case getType(actions.removeLogPile): {
        const {key} = action.payload;
        delete draft[key];
        return;
      }

      default:
        return;
    }
  }, {});

const pileReducer = produce(
  (draft: PileMap, action: LogAction) => {
    switch (action.type) {
      case getType(actions.addLogPile): {
        const {key, title, projectName} = action.payload;
        draft[key] = {
          title,
          tempDir: '',
          projectName,
          compressState: 'WAITING',
          compressReports: [],
          downloadStateMap: {},
        };
        return;
      }

      case getType(actions.removeLogPile): {
        const {key} = action.payload;
        delete draft[key];
        return;
      }

      case getType(actions.setCompressState): {
        const {key, newState} = action.payload;
        draft[key].compressState = newState;
        return;
      }

      case getType(actions.addDownloadFile): {
        const {key, file} = action.payload;
        draft[key].downloadStateMap[file] = 'PROCESSING';
        return;
      }

      case getType(actions.removeDownloadFile): {
        const {key, file} = action.payload;
        delete draft[key].downloadStateMap[file];
        return;
      }

      case getType(actions.removeDownloadFiles): {
        const {key} = action.payload;
        draft[key].downloadStateMap = {};
        return;
      }

      case getType(actions.setDownloadState): {
        const {key, file, newState} = action.payload;
        draft[key].downloadStateMap[file] = newState;
        return;
      }

      case getType(actions.setTempDir): {
        const {key, tempDir} = action.payload;
        draft[key].tempDir = tempDir;
        return;
      }

      case getType(actions.setReportMessages): {
        const {key, messages} = action.payload;
        draft[key].compressReports = messages;
        return;
      }

      default:
        return;
    }
  }, {});

export default combineReducers<LogState, LogAction>({
  defaultDownloadDate: (state = '', action) => {
    switch (action.type) {
      case getType(actions.setDefaultDownloadDate): {
        const {defaultDownloadDate} = action.payload;
        return defaultDownloadDate;
      }

      default:
        return state;
    }
  },
  expanded: expandReducer,
  piles: pileReducer,
});
