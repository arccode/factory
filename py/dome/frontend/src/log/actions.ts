// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import error from '@app/error';
import {Dispatch, RootState} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {
  getOverallDownloadStateFromStateMap,
  getPiles,
} from './selectors';
import {ComponentState} from './types';

export const removeLogPile =
  createAction('REMOVE_DOWNLOAD_PILE', (resolve) =>
    (key: string) => resolve({key}));

export const expandLogPile =
  createAction('EXPAND_DOWNLOAD_COMPONENT', (resolve) =>
    (key: string) => resolve({key}));

export const collapseLogPile =
  createAction('COLLAPSE_DOWNLOAD_COMPONENT', (resolve) =>
    (key: string) => resolve({key}));

export const removeDownloadFile =
  createAction('REMOVE_DOWNLOAD_FILE', (resolve) =>
    (key: string, file: string) => resolve({key, file}));

export const removeDownloadFiles =
  createAction('REMOVE_DOWNLOAD_FILES', (resolve) =>
    (key: string) => resolve({key}));

const setDefaultDownloadDate =
  createAction('SET_DEFAULT_DOWNLOAD_DATE', (resolve) =>
    (defaultDownloadDate: string) => resolve({defaultDownloadDate}));

const addLogPile =
  createAction('ADD_DOWNLOAD_PILE', (resolve) =>
    (key: string, title: string, projectName: string) =>
      resolve({key, title, projectName}));

const setCompressState =
  createAction('SET_COMPRESS_STATE', (resolve) =>
    (key: string, newState: ComponentState) => resolve({key, newState}));

const addDownloadFile =
  createAction('ADD_DOWNLOAD_FILE', (resolve) =>
    (key: string, file: string) => resolve({key, file}));

const setDownloadState =
  createAction('SET_DOWNLOAD_STATE', (resolve) =>
    (key: string, file: string, newState: ComponentState) =>
      resolve({key, file, newState}));

const setTempDir =
  createAction('SET_TEMP_DIR', (resolve) =>
    (key: string, tempDir: string) => resolve({key, tempDir}));

const setReportMessages =
  createAction('SET_REPORT_MESSAGES', (resolve) =>
    (key: string, messages: string[]) => resolve({key, messages}));

export const basicActions = {
  setDefaultDownloadDate,
  expandLogPile,
  collapseLogPile,
  addLogPile,
  removeLogPile,
  setCompressState,
  addDownloadFile,
  removeDownloadFile,
  removeDownloadFiles,
  setDownloadState,
  setTempDir,
  setReportMessages,
};

export const exportLog = (projectName: string,
                          logType: string,
                          archiveSize: number,
                          archiveUnit: string,
                          startDate: string,
                          endDate: string) =>
  async (dispatch: Dispatch) => {
    let response;
    const pileKey = `${logType}-${startDate}-${endDate}-${Math.random()}`;
    const dates = (startDate === endDate) ?
        startDate : `${startDate} ~ ${endDate}`;
    const title = (logType === 'csv') ? logType : `${logType} ${dates}`;
    dispatch(addLogPile(pileKey, title, projectName));
    try {
      dispatch(setCompressState(pileKey, 'PROCESSING'));
      response = await authorizedAxios().get(
          `projects/${projectName}/log/compress/`, {
        params: {
          log_type: logType,
          size: archiveSize,
          size_unit: archiveUnit,
          start_date: startDate,
          end_date: endDate,
        },
      });
      dispatch(setCompressState(pileKey, 'SUCCEEDED'));
    } catch (axiosError) {
      dispatch(setCompressState(pileKey, 'FAILED'));
      console.log(axiosError);
      const message = axiosError.response.data.detail;
      dispatch(error.actions.setAndShowErrorDialog(
          `error compressing log\n\n${message}`));
      return;
    }
    const {
      logPaths,
      tmpDir,
      messages,
    } = response.data;
    dispatch(setReportMessages(pileKey, messages));
    dispatch(setTempDir(pileKey, tmpDir));
    dispatch(downloadLogs(projectName, tmpDir, logPaths, pileKey));
    dispatch(setDefaultDownloadDate(endDate));
  };

export const downloadLogs = (projectName: string,
                             tempDir: string,
                             logPaths: string[],
                             pileKey: string) =>
  async (dispatch: Dispatch, getState: () => RootState) => {
    if (!logPaths.length) {
      deleteDirectory(projectName, tempDir);
      return;
    }
    const downloads = logPaths.map(
      async (logPath: string) =>
        dispatch(downloadLog(projectName, tempDir, logPath, pileKey)));
    await Promise.all(downloads);
    if (getOverallDownloadState(getState(), pileKey) === 'SUCCEEDED') {
      deleteDirectory(projectName, tempDir);
    }
  };

export const downloadLog = (projectName: string,
                            tempDir: string,
                            logPath: string,
                            pileKey: string) =>
  async (dispatch: Dispatch) => {
    dispatch(addDownloadFile(pileKey, logPath));
    try {
      const response = await authorizedAxios().get(
          `projects/${projectName}/log/download/`, {
        responseType: 'blob',
        params: {
          log_file: logPath,
          tmp_dir: tempDir,
        },
      });
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(response.data);
      link.download = `${projectName}-${logPath}`;
      link.click();
      window.URL.revokeObjectURL(link.href);
      dispatch(setDownloadState(pileKey, logPath, 'SUCCEEDED'));
    } catch (axiosError) {
      dispatch(setDownloadState(pileKey, logPath, 'FAILED'));
    }
  };

export const deleteDirectory = async (projectName: string,
                                      tempDir: string) => {
  await authorizedAxios().delete(
    `projects/${projectName}/log/delete/`,
    {data: {tmp_dir: tempDir}});
};

const getOverallDownloadState =
  (state: RootState, pileKey: string): ComponentState => {
    const downloadStateMap = getPiles(state)[pileKey].downloadStateMap;
    return getOverallDownloadStateFromStateMap(downloadStateMap);
  };
