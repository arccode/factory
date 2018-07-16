// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import axios, {AxiosInstance, AxiosRequestConfig} from 'axios';

// add authentication token to header, if exists.
export const authorizedAxios = (): AxiosInstance => {
  const token = localStorage.getItem('token');
  const config: AxiosRequestConfig = {};
  if (token != null) {
    config.headers = {
      Authorization: `Token ${localStorage.getItem('token')}`,
    };
  }
  return axios.create(config);
};

export type Omit<T, K extends keyof T> = Pick<T, Exclude<keyof T, K>>;
export type Unionize<T> = T[keyof T];

export const assertNotReachable = (x: never): never => {
  throw new Error('assertNotReachable fired.');
};
