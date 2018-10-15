// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export type FormSchema =
    BasicFormSchema |
    ListFormSchema |
    DictFormSchema |
    EnumFormSchema |
    JSONFormSchema;

export interface BasicFormSchema {
  type: 'NONE' | 'BOOL' | 'INT' | 'FLOAT' | 'STR';
}

export interface ListFormSchema {
  type: 'LIST';
  listSchema: FormSchema;
}

export interface DictFormSchema {
  type: 'DICT';
  dictSchema: {
    [name: string]: {
      schema: FormSchema,
      optional?: boolean,
    },
  };
}

export interface EnumFormSchema {
  type: 'ENUM';
  enumSchema: string[];
}

export interface JSONFormSchema {
  type: 'JSON';
  jsonSchema?: 'LIST' | 'DICT';
}
