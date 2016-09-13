// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionAutorenew from 'material-ui/svg-icons/action/autorenew';
import ActionCheckCircle from 'material-ui/svg-icons/action/check-circle';
import AlertError from 'material-ui/svg-icons/alert/error';
import {CardText} from 'material-ui/Card';
import IconButton from 'material-ui/IconButton';
import React from 'react';

import TaskStates from '../constants/TaskStates';

var Task = React.createClass({
  propTypes: {
    state: React.PropTypes.oneOf(Object.values(TaskStates)),
    description: React.PropTypes.string.isRequired,
    dismiss: React.PropTypes.func.isRequired,
    retry: React.PropTypes.func.isRequired
  },

  render() {
    const {state, description, cancel, dismiss, retry} = this.props;

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
        <div style={{display: 'table-cell', verticalAlign: 'middle'}}>
          {state == TaskStates.WAITING &&
            <IconButton tooltip={'cancel all tasks below'} onTouchTap={cancel}>
              <ActionAutorenew />
            </IconButton>
          }
          {state == TaskStates.RUNNING &&
            <IconButton className="spin">
              <ActionAutorenew />
            </IconButton>
          }
          {state == TaskStates.SUCCEEDED &&
            <IconButton
              tooltip={'dismiss'}
              onTouchTap={dismiss}
              iconStyle={{fill: 'green'}}
            >
              <ActionCheckCircle />
            </IconButton>
          }
          {state == TaskStates.FAILED &&
            <IconButton
              tooltip={'retry'}
              onTouchTap={retry}
              iconStyle={{fill: 'red'}}
            >
              <AlertError />
            </IconButton>
          }
        </div>
      </CardText>
    );
  }
});

export default Task;
