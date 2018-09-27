// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

export type Omit<T, K extends keyof T> = Pick<T, Exclude<keyof T, K>>;
export type Unionize<T> = T[keyof T];

type ArgumentTypes<T> = T extends (...args: infer U) => any ? U : never;
type DispatchProp<T> = (...args: ArgumentTypes<T>) => void;
export type DispatchProps<M> = {
  [K in keyof M]: DispatchProp<M[K]>;
};
