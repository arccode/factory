// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Dialog from 'material-ui/Dialog';
import PropTypes from 'prop-types';
import React from 'react';

class HiddenFileSelect extends React.Component {
  static propTypes = {
    onChange: PropTypes.func.isRequired,
  };

  constructor(props) {
    super(props);
    this.fileInputRef = React.createRef();
  }

  componentDidMount() {
    this.fileInputRef.current.click();
  }

  componentWillUnmount() {
    this.props.onChange(null);
  }

  handleChange = (event) => {
    event.preventDefault();
    this.props.onChange(event.target.files[0]);
  }

  render() {
    return (
      <input
        className="hidden"
        type="file"
        onChange={this.handleChange}
        ref={this.fileInputRef}
      />);
  }
}

// TODO(pihsun): Refactor the code structure, group code by topic instead of
// type, and move this into "forms" topic.
class FileUploadDialog extends React.Component {
  static propTypes = {
    ...Dialog.propTypes,
    children: PropTypes.element.isRequired,
    onSubmit: PropTypes.func.isRequired,
  };

  state = {
    file: null,
  };

  handleFileChange = (file) => {
    this.setState({file});
  }

  handleSubmit = (values) => {
    this.props.onSubmit({file: this.state.file, ...values});
  }

  componentWillUnmount() {
    // When the component is unmounted, call the onRequestClose so the file
    // select dialog won't immediately pop-up when the component is mounted
    // next time.
    const {open, onRequestClose} = this.props;
    if (open && onRequestClose) {
      onRequestClose(null);
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

export default FileUploadDialog;
