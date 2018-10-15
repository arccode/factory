// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {OVERRIDE_DELETE_KEY, OVERRIDE_REPLACE_KEY} from './common';

export type JSONType =
    null | boolean | number | string | JSONArray | JSONObject;

export interface JSONArray extends Array<JSONType> {
}

export interface JSONObject {
  [key: string]: JSONType;
}

export const isJSONObject = (x: JSONType): x is JSONObject =>
    x !== null && typeof x === 'object' && !Array.isArray(x);

export const prettyJSON = (obj: JSONType) => {
  const getAllKeys = (o: JSONType) => {
    const keys: string[] = [];
    if (Array.isArray(o)) {
      for (const item of o) {
        keys.push(...getAllKeys(item));
      }
    } else if (o !== null && typeof o === 'object') {
      for (const k of Object.keys(o)) {
        keys.push(k);
        keys.push(...getAllKeys(o[k]));
      }
    }
    return keys;
  };
  return JSON.stringify(obj, getAllKeys(obj).sort(), 2);
};

// C3 linearization is used for resolving test list inheritance relationship.
export const c3Linearization =
    <T>(parents: Map<T, T[]>): Map<T, T[]> => {
  const mro = new Map<T, T[]>();

  const dfs = (u: T) => {
    const savedResult = mro.get(u);
    if (savedResult !== undefined) {
      if (savedResult.length === 0) throw new Error('Cycle detected.');
      return savedResult;
    }
    mro.set(u, []);

    const uParents = parents.get(u);
    if (uParents === undefined) {
      throw new Error(`Missing parent information of '${u}'.`);
    }

    const listsToMerge = uParents.map((parent) => dfs(parent));
    listsToMerge.push(uParents);
    const num = listsToMerge.length;
    const ptrToHead: number[] = new Array(num).fill(0);
    const countInTail = new Map<T, number>();
    for (const list of listsToMerge) {
      list.forEach((val, idx) => {
        if (idx > 0) countInTail.set(val, (countInTail.get(val) || 0) + 1);
      });
    }

    const ret = [u];
    for (; ; ) {
      let next: T | undefined;
      let flag = false;
      for (let i = 0; i < num; i++) {
        if (ptrToHead[i] < listsToMerge[i].length) {
          flag = true;
          const head = listsToMerge[i][ptrToHead[i]];
          if (!countInTail.get(head)) {
            next = head;
            break;
          }
        }
      }
      if (next === undefined) {
        if (flag) throw new Error('Invalid input.');
        break;
      }
      ret.push(next);
      for (let i = 0; i < num; i++) {
        if (listsToMerge[i][ptrToHead[i]] === next) {
          if (++ptrToHead[i] < listsToMerge[i].length) {
            const head = listsToMerge[i][ptrToHead[i]];
            countInTail.set(head, countInTail.get(head)! - 1);
          }
        }
      }
    }
    mro.set(u, ret);
    return ret;
  };

  for (const [u] of parents) dfs(u);
  return mro;
};

// Equivalent to the one in 'py/utils/config_utils.py'.
export const overrideConfig = (
    base: JSONObject,
    overrides: JSONObject,
    copyOnWrite = false): JSONObject => {
  const popBoolean = (obj: JSONObject, key: string): boolean => {
    const val = obj[key];
    delete obj[key];
    if (val !== undefined && typeof val !== 'boolean') {
      throw new Error(
          `Field ${key} should be a boolean but ${JSON.stringify(val)} found.`);
    }
    return !!val;
  };

  let changed = false;
  const res = copyOnWrite ? base : {...base};
  for (const key of Object.keys(overrides)) {
    let val = overrides[key];
    if (!isJSONObject(val)) {
      res[key] = val;
      changed = true;
    } else {
      val = {...val};

      if (popBoolean(val, OVERRIDE_DELETE_KEY)) {
        if (key in res) {
          delete res[key];
          changed = true;
        }
        continue;
      }

      if (popBoolean(val, OVERRIDE_REPLACE_KEY)) {
        res[key] = overrideConfig({}, val);
        changed = true;
        continue;
      }

      const oldVal = res[key];
      if (!isJSONObject(oldVal)) {
        res[key] = overrideConfig({}, val);
      } else {
        res[key] = overrideConfig(oldVal, val, copyOnWrite);
      }
      changed = true;
    }
  }
  return changed ? res : base;
};
