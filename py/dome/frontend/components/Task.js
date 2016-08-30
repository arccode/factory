// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import React from 'react';
import ActionDone from 'material-ui/svg-icons/action/done';
import Paper from 'material-ui/Paper';

import TaskStates from '../constants/TaskStates';

var Task = React.createClass({
  propTypes: {
    state: React.PropTypes.oneOf([
      TaskStates.TASK_STARTED,
      TaskStates.TASK_SUCCEEDED,
      TaskStates.TASK_FAILED
    ]),
    description: React.PropTypes.string.isRequired,
    dismiss: React.PropTypes.func.isRequired,
    retry: React.PropTypes.func.isRequired,
    style: React.PropTypes.shape
  },

  render() {
    const {state, description, dismiss, retry, style} = this.props;
    return (
      <Paper zDepth={2} style={style}>
        {description}
        {state == TaskStates.TASK_SUCCEEDED &&
          <span
            // TODO(littlecvr): should be a better way to set offset
            style={{cursor: 'pointer'}}
            onClick={dismiss}
          >
            finished.
            <ActionDone />
          </span>
        }
        {state == TaskStates.TASK_FAILED &&
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

export default Task;
