// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {DialogProps} from 'material-ui';
import Dialog from 'material-ui/Dialog';
import React from 'react';

import {Omit} from '../utils';

import {HiddenFileSelect} from './HiddenFileSelect';

interface FileUploadDialogProps<T>
  extends Omit<DialogProps, 'onSubmit' | 'open'> {
  children: JSX.Element;
  open: boolean;
  onSubmit: (values: T & {file: File | null}) => void;
}

interface FileUploadDialogState {
  file: File | null;
}

export default class FileUploadDialog<T>
  extends React.Component<FileUploadDialogProps<T>, FileUploadDialogState> {

  state = {
    file: null,
  };

  handleFileChange = (file: File | null) => {
    this.setState({file});
  }

  handleSubmit = (values: T) => {
    // TODO(pihsun): We can use the spread operator after
    // https://github.com/Microsoft/TypeScript/pull/13288 is merged.
    this.props.onSubmit(Object.assign({file: this.state.file}, values));
  }

  componentWillUnmount() {
    // When the component is unmounted, call the onRequestClose so the file
    // select dialog won't immediately pop-up when the component is mounted
    // next time.
    const {open, onRequestClose} = this.props;
    if (open && onRequestClose) {
      onRequestClose(false);
    }
  }

  render() {
    const {children, open, onSubmit: unused, ...dialogProps} = this.props;
    const openDialog = open && this.state.file != null;
    return (
      <>
        {open && <HiddenFileSelect onChange={this.handleFileChange} />}
        <Dialog {...dialogProps} open={openDialog}>
          {React.cloneElement(
            children, {onSubmit: this.handleSubmit})}
        </Dialog>
      </>
    );
  }
}
