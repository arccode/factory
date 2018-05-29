// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {CardText} from 'material-ui/Card';
import IconButton from 'material-ui/IconButton';
import {grey700} from 'material-ui/styles/colors';
import RunningIcon from 'material-ui/svg-icons/action/autorenew';
import DismissIcon from 'material-ui/svg-icons/action/check-circle';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import ErrorIcon from 'material-ui/svg-icons/alert/error';
import PropTypes from 'prop-types';
import React from 'react';

import TaskStates from '../constants/TaskStates';

class Task extends React.Component {
  static propTypes = {
    state: PropTypes.oneOf(Object.values(TaskStates)),
    description: PropTypes.string.isRequired,

    dismiss: PropTypes.func.isRequired,
    retry: PropTypes.func.isRequired,
    cancel: PropTypes.func.isRequired,
  };

  render() {
    const {state, description, cancel, dismiss, retry} = this.props;

    // TODO(littlecvr): refactor style attributes, use className if possible.

    return (
      <CardText style={{display: 'table-row'}}>
        <div
          style={{
            display: 'table-cell',
            verticalAlign: 'middle',
            padding: 12,
          }}
        >
          {description}
        </div>
        <div style={{
          display: 'table-cell', textAlign: 'right', verticalAlign: 'middle',
        }}>
          <IconButton
            tooltip={'cancel'}
            onClick={cancel}
            iconStyle={{fill: grey700}}
            disabled={
              state != TaskStates.WAITING && state != TaskStates.FAILED
            }
          >
            <DeleteIcon />
          </IconButton>
          {state == TaskStates.WAITING &&
            <IconButton tooltip={'waiting'}>
              <RunningIcon />
            </IconButton>
          }
          {state == TaskStates.RUNNING &&
            <IconButton className='spin'>
              <RunningIcon />
            </IconButton>
          }
          {state == TaskStates.SUCCEEDED &&
            <IconButton
              tooltip={'dismiss'}
              onClick={dismiss}
              iconStyle={{fill: 'green'}}
            >
              <DismissIcon />
            </IconButton>
          }
          {state == TaskStates.FAILED &&
            <IconButton
              tooltip={'retry'}
              onClick={retry}
              iconStyle={{fill: 'red'}}
            >
              <ErrorIcon />
            </IconButton>
          }
          <div style={{
            display: 'inline-block', width: 48, height: 1, marginRight: 0,
          }}></div>
        </div>
      </CardText>
    );
  }
}

export default Task;
