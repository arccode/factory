// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import ActionDone from 'material-ui/svg-icons/action/done';
import Paper from 'material-ui/Paper';
import FlatButton from 'material-ui/FlatButton';

import UploadingTaskStates from '../constants/UploadingTaskStates';

var UploadingTask = React.createClass({
  propTypes: {
    state: React.PropTypes.oneOf([
      UploadingTaskStates.UPLOADING_TASK_STARTED,
      UploadingTaskStates.UPLOADING_TASK_SUCCEEDED,
      UploadingTaskStates.UPLOADING_TASK_FAILED
    ]),
    description: React.PropTypes.string.isRequired,
    dismiss: React.PropTypes.func.isRequired,
    retry: React.PropTypes.func.isRequired
  },

  render() {
    const {state, description, dismiss, retry, style} = this.props;
    return (
      <Paper zDepth={2} style={style}>
        {description}
        {state == UploadingTaskStates.UPLOADING_TASK_SUCCEEDED &&
          <span
            style={{cursor: 'pointer'}}
            onClick={dismiss}
          >
            finished.
            <ActionDone />
          </span>
        }
        {state == UploadingTaskStates.UPLOADING_TASK_FAILED &&
          <span
            style={{cursor: 'pointer'}}
            onClick={retry}
          >
            failed.
            <ActionDone />
          </span>
        }
      </Paper>
    );
  }
});

export default UploadingTask;
