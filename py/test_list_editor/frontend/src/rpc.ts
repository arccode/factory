// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import * as common from './common';

const call = async (method: string, ...params: any[]) => {
  const input =
      process.env.NODE_ENV !== 'development' ? '/' : 'http://localhost:4013/';
  const init = {
    method: 'POST',
    body: JSON.stringify({jsonrpc: '2.0', id: 1, method, params}),
  };
  const res = await fetch(input, init);
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  const json = await res.json();
  if (json.error) {
    throw new Error(`JSON-RPC ${json.error.code} ${json.error.message}`);
  }
  return json.result;
};

// For the detailed description and implementation of these RPC functions,
// see 'factory/py/test_list_editor/backend/rpc.py'.

export const GetTestListSchema = (): Promise<string> =>
    call('GetTestListSchema');

export const LoadFiles = (): Promise<common.FileSystemState> =>
    call('LoadFiles');

export const SaveFiles =
    (requests: {[filepath: string]: string}): Promise<void> =>
    call('SaveFiles', requests);
