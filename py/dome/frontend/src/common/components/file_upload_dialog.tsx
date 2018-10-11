// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Button from '@material-ui/core/Button';
import Dialog from '@material-ui/core/Dialog';
import DialogActions from '@material-ui/core/DialogActions';
import DialogContent from '@material-ui/core/DialogContent';
import DialogTitle from '@material-ui/core/DialogTitle';
import React from 'react';

import {HiddenFileSelect} from './hidden_file_select';

export type SelectProps<T = {}> = {
  multiple: true,
  onSubmit: (values: T & {files: FileList}) => void,
} | {
  multiple: false,
  onSubmit: (values: T & {file: File}) => void,
};

type FileUploadDialogProps<T> = {
  children: JSX.Element;
  open: boolean;
  title: string;
  submitForm: () => void;
  onCancel: () => void;
} & SelectProps<T>;

interface FileUploadDialogState {
  files: FileList | null;
}

export default class FileUploadDialog<T = {}> extends React.Component<
  FileUploadDialogProps<T>, FileUploadDialogState> {

  static defaultProps = {
    multiple: false,
  };

  state: FileUploadDialogState = {
    files: null,
  };

  handleFileChange = (files: FileList | null) => {
    this.setState({files});
  }

  handleSubmit = (values: T) => {
    const files = this.state.files;
    if (files == null) {
      throw new Error(
        'Files are null in FileUploadDialog, but handleSubmit is called.');
    }
    // TODO(pihsun): We probably can use the spread operator after
    // https://github.com/Microsoft/TypeScript/issues/10727 is resolved.
    if (this.props.multiple) {
      this.props.onSubmit(Object.assign({files}, values));
    } else {
      const file = files[0];
      this.props.onSubmit(Object.assign({file}, values));
    }
  }

  componentWillUnmount() {
    // When the component is unmounted, call the onCancel so the file select
    // dialog won't immediately pop-up when the component is mounted next time.
    const {open, onCancel} = this.props;
    if (open) {
      onCancel();
    }
  }

  render() {
    const {children, open, title, onCancel, submitForm} = this.props;
    const {files} = this.state;
    const openDialog = open && files != null;
    return (
      <>
        {open &&
          <HiddenFileSelect
            onChange={this.handleFileChange}
            multiple={this.props.multiple}
          />}
        <Dialog open={openDialog} onClose={onCancel}>
          <DialogTitle>{title}</DialogTitle>
          <DialogContent>
            {React.cloneElement(children, {onSubmit: this.handleSubmit})}
          </DialogContent>
          <DialogActions>
            <Button color="primary" onClick={submitForm}>confirm</Button>
            <Button onClick={onCancel}>cancel</Button>
          </DialogActions>
        </Dialog>
      </>
    );
  }
}
