// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {createAction} from 'typesafe-actions';

import error from '@app/error';
import {Dispatch} from '@app/types';
import {authorizedAxios} from '@common/utils';

import {downloadMessage} from './types';

export const setDefaultDownloadDate =
  createAction('SET_DEFAULT_DOWNLOAD_DATE', (resolve) =>
    (defaultDownloadDate: string) => resolve({defaultDownloadDate}));
export const showLogDialog = createAction('SHOW_LOG_DIALOG');
export const hideLogDialog = createAction('HIDE_LOG_DIALOG');

export const basicActions = {
  setDefaultDownloadDate,
  showLogDialog,
  hideLogDialog,
};

export const exportLog = (projectName: string,
                          logType: string,
                          archiveSize: number,
                          archiveUnit: string,
                          startDate: string,
                          endDate: string) =>
  async (dispatch: Dispatch) => {
    let response;
    try {
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
    } catch (axiosError) {
      const message = axiosError.response.data.detail;
      dispatch(error.actions.setAndShowErrorDialog(
          `error compressing log\n\n${message}`));
      return;
    }

    const logPaths = response.data.logPaths;
    const tmpDir = response.data.tmpDir;
    const downloads = logPaths.map(
      async (logPath: string) =>
        downloadLog(projectName, tmpDir, logPath));
    await Promise.all(downloads);
    dispatch(setDefaultDownloadDate(endDate));
  };

const downloadLog = async (projectName: string,
                           tmpDir: string,
                           logPath: string): Promise<downloadMessage> => {
  try {
    const response = await authorizedAxios().get(
        `projects/${projectName}/log/download/`, {
      responseType: 'blob',
      params: {
        log_file: logPath,
        tmp_dir: tmpDir,
      },
    });
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(response.data);
    link.download = `${projectName}-${logPath}`;
    link.click();
    window.URL.revokeObjectURL(link.href);
    return {
      logPath,
      success: true,
    };
  } catch (axiosError) {
    return {
      logPath,
      success: false,
    };
  }
};
