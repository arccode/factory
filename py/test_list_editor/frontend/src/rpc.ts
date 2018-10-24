// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import * as common from './common';

const call = async (method: string, ...params: any[]) => {
  const input =
      process.env.NODE_ENV !== 'development' ? '/' : common.DEV_BACKEND_URL;
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

export const loadFiles = (): Promise<common.FileSystemState> =>
    call('LoadFiles');

export const saveFiles =
    (requests: {[filepath: string]: string}): Promise<void> =>
    call('SaveFiles', requests);

export const listPytests = (): Promise<string[]> => call('ListPytests');

export const getPytestInfo =
    async (pytestName: string): Promise<common.PytestInfo> => {
  const res = await call('GetPytestInfo', pytestName);
  if (res.args) {
    for (const name of Object.keys(res.args)) {
      const types: common.PytestArgType[] = res.args[name].type.map(
          (t: string | string[]) => (
              Array.isArray(t) ?
              t : // PytestArgEnumType
              common.PytestArgBasicType[
                  t as keyof typeof common.PytestArgBasicType]));
      res.args[name].type = types;
    }
  }
  return res;
};

export const translated =
    (obj: common.I18nType, translate = true): Promise<common.I18nObject> =>
    call('Translated', obj, translate);
