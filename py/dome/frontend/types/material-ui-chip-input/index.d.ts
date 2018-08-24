// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

declare module 'material-ui-chip-input' {

  import React from 'react';

  interface ChipInputProps {
    className?: string;
    value: string[];
    onAdd(chip: string): void;
    onDelete(chip: string, index: number): void;
  }

  // A simple type for material-ui-chip-input that only have attributes that we
  // used (in particular, bundle/component/RuleTable.tsx).
  export default class ChipInput extends React.Component<ChipInputProps> {
  }
}
