// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {CardText} from 'material-ui/Card';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import DismissIcon from 'material-ui/svg-icons/action/check-circle';
import ErrorIcon from 'material-ui/svg-icons/alert/error';
import IconButton from 'material-ui/IconButton';
import React from 'react';
import RunningIcon from 'material-ui/svg-icons/action/autorenew';

import TaskStates from '../constants/TaskStates';

var Task = React.createClass({
  propTypes: {
    state: React.PropTypes.oneOf(Object.values(TaskStates)),
    description: React.PropTypes.string.isRequired,

    dismiss: React.PropTypes.func.isRequired,
    retry: React.PropTypes.func.isRequired,
    cancel: React.PropTypes.func.isRequired,

    mouseEnterDeleteButton: React.PropTypes.func.isRequired,
    mouseLeaveDeleteButton: React.PropTypes.func.isRequired,

    // TODO(littlecvr): directly passing color attribute seems weird here
    deleteIconColor: React.PropTypes.string.isRequired
  },

  render() {
    const {state, description, cancel, dismiss, retry} = this.props;

    // TODO(littlecvr): refactor style attributes, use className if possible.

    return (
      <CardText style={{display: 'table-row'}}>
        <div
          style={{
            display: 'table-cell',
            verticalAlign: 'middle',
            padding: 12
          }}
        >
          {description}
        </div>
        <div style={{
          display: 'table-cell', textAlign: 'right', verticalAlign: 'middle'
        }}>
          <span
            onMouseEnter={this.props.mouseEnterDeleteButton}
            onMouseLeave={this.props.mouseLeaveDeleteButton}
          >
            <IconButton
              tooltip={'cancel'}
              onTouchTap={cancel}
              iconStyle={{fill: this.props.deleteIconColor}}
              disabled={
                state != TaskStates.WAITING && state != TaskStates.FAILED
              }
            >
              <DeleteIcon />
            </IconButton>
          </span>
          {state == TaskStates.WAITING &&
            <IconButton tooltip={'waiting'}>
              <RunningIcon />
            </IconButton>
          }
          {state == TaskStates.RUNNING &&
            <IconButton className="spin">
              <RunningIcon />
            </IconButton>
          }
          {state == TaskStates.SUCCEEDED &&
            <IconButton
              tooltip={'dismiss'}
              onTouchTap={dismiss}
              iconStyle={{fill: 'green'}}
            >
              <DismissIcon />
            </IconButton>
          }
          {state == TaskStates.FAILED &&
            <IconButton
              tooltip={'retry'}
              onTouchTap={retry}
              iconStyle={{fill: 'red'}}
            >
              <ErrorIcon />
            </IconButton>
          }
          <div style={{
            display: 'inline-block', width: 48, height: 1, marginRight: 0
          }}></div>
        </div>
      </CardText>
    );
  }
});

export default Task;
