// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionDone from 'material-ui/svg-icons/action/done';
import {CardText} from 'material-ui/Card';
import React from 'react';

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
    retry: React.PropTypes.func.isRequired
  },

  render() {
    const {state, description, dismiss, retry} = this.props;

    return (
      <CardText style={{display: 'table-row'}}>
        <div style={{display: 'table-cell', verticalAlign: 'middle'}}>
          {description}
        </div>
        <div style={{display: 'table-cell', verticalAlign: 'middle'}}>
          {state == TaskStates.TASK_SUCCEEDED &&
            <span
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
        </div>
      </CardText>
    );
  }
});

export default Task;
