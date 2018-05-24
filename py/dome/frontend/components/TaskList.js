// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import {Card, CardActions, CardHeader} from 'material-ui/Card';
import IconButton from 'material-ui/IconButton';
import {black, grey700} from 'material-ui/styles/colors';
import DismissIcon from 'material-ui/svg-icons/action/check-circle';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import CollapseIcon from 'material-ui/svg-icons/navigation/expand-less';
import ExpandIcon from 'material-ui/svg-icons/navigation/expand-more';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import DomeActions from '../actions/domeactions';
import TaskStates from '../constants/TaskStates';
import TaskUtils from '../utils/task';

import Task from './Task';

class TaskList extends React.Component {
  static propTypes = {
    collapsed: PropTypes.bool.isRequired,
    setCollapsed: PropTypes.func.isRequired,

    tasks: PropTypes.instanceOf(Immutable.Map).isRequired,
    cancelTask: PropTypes.func.isRequired,
    dismissTask: PropTypes.func.isRequired,
    retryTask: PropTypes.func.isRequired,
  };

  state = {
    // If negative, the mouse is not on any delete button; otherwise, this
    // value is the index of task in task list that holds the delete button
    // the mouse is currently on, 0 means the mouse is on the title bar's
    // delete button.
    mouseOnDeleteIconIndex: -1,
  };

  cancelAllWaitingTasks = (event) => {
    event.stopPropagation();
    const minWaitingTaskIDs = this.props.tasks.filter((t) => (
      t.get('state') == TaskStates.WAITING ||
      t.get('state') == TaskStates.FAILED
    )).keySeq().min();
    this.props.cancelTask(minWaitingTaskIDs);
  };

  dismissAllSucceededTasks = (event) => {
    event.stopPropagation();
    this.props.tasks.map((task, taskID) => {
      if (task.get('state') == TaskStates.SUCCEEDED) {
        this.props.dismissTask(taskID);
      }
    });
  };

  mouseEnterDeleteButton = (index) => {
    this.setState({mouseOnDeleteIconIndex: parseInt(index)});
  };

  mouseLeaveDeleteButton = () => {
    this.setState({mouseOnDeleteIconIndex: -1});
  };

  render() {
    const {tasks, cancelTask, dismissTask, retryTask} = this.props;

    let waitingTaskCount = 0;
    let runningTaskCount = 0;
    let succeededTaskCount = 0;
    const failedTaskCount = 0;
    tasks.map((task) => {
      switch (task.get('state')) {
        case TaskStates.WAITING: waitingTaskCount++; break;
        case TaskStates.RUNNING: runningTaskCount++; break;
        case TaskStates.SUCCEEDED: succeededTaskCount++; break;
        case TaskStates.FAILED: waitingTaskCount++; break;
      }
    });
    const taskSummary = `${waitingTaskCount} waiting, ` +
        `${runningTaskCount} running, ` +
        `${succeededTaskCount} succeeded, ` +
        `${failedTaskCount} failed`;

    // TODO(littlecvr): refactor style attributes, use className if possible.
    let titleBarDeleteIconColor = grey700;
    let deleteIconsShouldChangeColor = false;

    if (this.state.mouseOnDeleteIconIndex == 0) {
      // if the mouse is on the delete icon on title bar, change the color of
      // all delete icons
      titleBarDeleteIconColor = black;
      deleteIconsShouldChangeColor = true;
    } else if (this.state.mouseOnDeleteIconIndex >= 1) {
      // if the mouse is on one of the delete icon (except the one on title
      // bar), determine whether to change color or not by the state of the task
      const mouseOnDeleteIconTaskState = tasks.getIn([
        TaskUtils.getSortedTaskIDs(tasks)[
            this.state.mouseOnDeleteIconIndex - 1
        ],
        'state',
      ]);
      // change when state is WAITING or FAILED because only waiting or failed
      // tasks can be deleted
      if (mouseOnDeleteIconTaskState == TaskStates.WAITING ||
          mouseOnDeleteIconTaskState == TaskStates.FAILED) {
        deleteIconsShouldChangeColor = true;
      }
    }

    return (
      <Card
        style={{position: 'fixed', right: 24, bottom: 24}}
        containerStyle={{display: 'table'}}
      >
        {/* title bar */}
        {tasks.size > 0 &&
          <div
            style={{display: 'table-row', cursor: 'pointer'}}
            onClick={() => this.props.setCollapsed(!this.props.collapsed)}
          >
            <CardHeader title={'Tasks'} subtitle={taskSummary} style={{
              display: 'table-cell', verticalAlign: 'middle', padding: 12,
            }}/>
            <CardActions style={{
              display: 'table-cell', textAlign: 'right',
              verticalAlign: 'middle', padding: 0,
            }}>
              {!this.props.collapsed &&
                <span
                  onMouseEnter={() => this.mouseEnterDeleteButton(0)}
                  onMouseLeave={this.mouseLeaveDeleteButton}
                  style={{marginRight: 0}}
                >
                  <IconButton
                    tooltip={'cancel all waiting tasks'}
                    onClick={this.cancelAllWaitingTasks}
                    iconStyle={{fill: titleBarDeleteIconColor}}
                  >
                    <DeleteIcon />
                  </IconButton>
                </span>
              }
              {!this.props.collapsed &&
                <IconButton
                  tooltip={'dismiss all finished tasks'}
                  onClick={this.dismissAllSucceededTasks}
                  style={{marginRight: 0}}
                  iconStyle={{fill: 'green'}}
                >
                  <DismissIcon />
                </IconButton>
              }
              {!this.props.collapsed &&
                <IconButton
                  tooltip={'collapse'}
                  style={{marginRight: 0}}
                >
                  <CollapseIcon />
                </IconButton>
              }
              {/* two padding blank icons */}
              {this.props.collapsed &&
                <div style={{
                  display: 'inline-block', width: 48, height: 1, marginRight: 0,
                }}></div>
              }
              {this.props.collapsed &&
                <div style={{
                  display: 'inline-block', width: 48, height: 1, marginRight: 0,
                }}></div>
              }
              {this.props.collapsed &&
                <IconButton
                  tooltip={'expand'}
                  style={{marginRight: 0}}
                >
                  <ExpandIcon />
                </IconButton>
              }
            </CardActions>
          </div>
        }

        {/* task list */}
        {!this.props.collapsed &&
          TaskUtils.getSortedTaskIDs(tasks).map((taskID, index) => {
            // make this 1-based array since 0 is reserved for the title bar
            index = index + 1;
            const task = tasks.get(taskID);
            let deleteIconColor = grey700;
            if (deleteIconsShouldChangeColor &&
                index >= this.state.mouseOnDeleteIconIndex) {
              deleteIconColor = black;
            }
            return (
              <Task
                key={taskID}
                state={task.get('state')}
                description={task.get('description')}
                deleteIconColor={deleteIconColor}
                mouseEnterDeleteButton={
                  () => this.mouseEnterDeleteButton(index)
                }
                mouseLeaveDeleteButton={this.mouseLeaveDeleteButton}
                cancel={() => cancelTask(taskID)}
                dismiss={() => dismissTask(taskID)}
                retry={() => retryTask(taskID)}
              />
            );
          }
          )}
      </Card>
    );
  }
}

function mapStateToProps(state) {
  return {
    tasks: state.getIn(['dome', 'tasks']),
  };
}

function mapDispatchToProps(dispatch) {
  return {
    cancelTask: (taskID) => (
      dispatch(DomeActions.cancelTaskAndItsDependencies(taskID))
    ),
    dismissTask: (taskID) => dispatch(DomeActions.removeTask(taskID)),
    retryTask: (taskID) => console.warn('not implemented yet'),
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(TaskList);
