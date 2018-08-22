// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {JSONType} from './utils';

export const DEV_BACKEND_URL = 'http://localhost:4013/';

// Special key names for 'overrideConfig'.
export const OVERRIDE_DELETE_KEY = '__delete__';
export const OVERRIDE_REPLACE_KEY = '__replace__';

export interface FileSystemState {
  dirs: Array<{name: string, path: string, filelist: string[]}>;
  files: {[basename: string]: string};
}

export interface PytestInfo {
  src: string;
  args?: {[name: string]: PytestArgInfo};
}

export interface PytestArgInfo {
  type: PytestArgType[];
  help: string;
  default?: JSONType;
}

export type PytestArgType = PytestArgBasicType | PytestArgEnumType;

export enum PytestArgBasicType {NONE, BOOL, INT, FLOAT, STR, LIST, DICT}

export type PytestArgEnumType = string[];

export type I18nType = string | I18nObject;

export interface I18nObject {
  [locale: string]: string;
}
