// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';

interface HiddenFileSelectProps {
  multiple: boolean;
  onChange: (files: FileList | null) => void;
}

export class HiddenFileSelect extends React.Component<HiddenFileSelectProps> {
  fileInputRef: React.RefObject<HTMLInputElement>;

  constructor(props: HiddenFileSelectProps) {
    super(props);
    this.fileInputRef = React.createRef();
  }

  componentDidMount() {
    if (this.fileInputRef.current) {
      this.fileInputRef.current.click();
    }
  }

  componentWillUnmount() {
    this.props.onChange(null);
  }

  handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    event.preventDefault();
    if (event.target.files) {
      this.props.onChange(event.target.files);
    }
  }

  render() {
    return (
      <input
        className="hidden"
        type="file"
        onChange={this.handleChange}
        ref={this.fileInputRef}
        multiple={this.props.multiple}
      />);
  }
}
