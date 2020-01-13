// Copyright 2020 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import '@testing-library/jest-dom/extend-expect';
import {fireEvent, render} from '@testing-library/react';
import React from 'react';

import {HiddenFileSelect} from '../common/components/hidden_file_select';

/**
 * HiddenFileSelect component test.
 */

describe('HiddenFileSelect', () => {
  let node: HTMLElement;
  let handleFileChange: (files: FileList | null) => undefined;

  beforeEach(() => {
    handleFileChange = jest.fn((files: FileList | null) => undefined);
    const {getByRole} =
      render(<HiddenFileSelect multiple onChange={handleFileChange} />);
    node = getByRole('textbox', {hidden: true});
  });

  it('verify that HiddenFileSelect dom node is correct', () => {
    expect(node).toBeDefined();
    expect(node).toHaveClass('hidden');
    expect(node).toHaveAttribute('type', 'file');
    expect(node).toHaveAttribute('multiple');
  });

  it('select file and trigger on file change', () => {
    const rows = ['chromeos', 'chrome os factory', 'chrome os factory dome'];
    const file = new File([rows.join('\n')], 'cros.csv');
    Object.defineProperty(node, 'files', {value: [file]});
    fireEvent.change(node);
    expect(handleFileChange).toHaveBeenCalledTimes(1);
    expect(handleFileChange).toHaveBeenCalledWith([file]);
  });
});
