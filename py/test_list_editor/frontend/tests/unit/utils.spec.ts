// Copyright 2019 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {c3Linearization} from '@/utils';

test('C3 Linearization should return correct order', () => {
  const inheritOrder = new Map<string, string[]>([
    ['A', []],
    ['B', ['A']],
    ['C', ['A']],
    ['D', ['A']],
    ['E', ['B', 'C']],
    ['F', ['C', 'D']],
    ['G', ['E', 'F']],
  ]);

  const expectedOrder = new Map<string, string[]>([
    ['A', ['A']],
    ['B', ['B', 'A']],
    ['C', ['C', 'A']],
    ['D', ['D', 'A']],
    ['E', ['E', 'B', 'C', 'A']],
    ['F', ['F', 'C', 'D', 'A']],
    ['G', ['G', 'E', 'B', 'F', 'C', 'D', 'A']],
  ]);

  const res = c3Linearization(inheritOrder);
  expect(res).toEqual(expectedOrder);
});
