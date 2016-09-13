// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {Card, CardActions, CardHeader} from 'material-ui/Card';
import CollapseIcon from 'material-ui/svg-icons/navigation/expand-less';
import {connect} from 'react-redux';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import DismissIcon from 'material-ui/svg-icons/action/check-circle';
import ExpandIcon from 'material-ui/svg-icons/navigation/expand-more';
import {black, grey700} from 'material-ui/styles/colors';
import IconButton from 'material-ui/IconButton';
import Immutable from 'immutable';
import React from 'react';

import DomeActions from '../actions/domeactions';
import Task from './Task';
import TaskStates from '../constants/TaskStates';

var TaskList = React.createClass({
  propTypes: {
    collapsed: React.PropTypes.bool.isRequired,
    setCollapsed: React.PropTypes.func.isRequired,

    tasks: React.PropTypes.instanceOf(Immutable.Map).isRequired,
    cancelTask: React.PropTypes.func.isRequired,
    dismissTask: React.PropTypes.func.isRequired,
    retryTask: React.PropTypes.func.isRequired
  },

  cancelAllWaitingTasks(event) {
    event.stopPropagation();
    var minWaitingTaskIDs = this.props.tasks.filter(t => (
        t.get('state') == TaskStates.WAITING ||
        t.get('state') == TaskStates.FAILED
    )).keySeq().min();
    this.props.cancelTask(minWaitingTaskIDs);
  },

  dismissAllSucceededTasks(event) {
    event.stopPropagation();
    this.props.tasks.map((task, taskID) => {
      if (task.get('state') == TaskStates.SUCCEEDED) {
        this.props.dismissTask(taskID);
      }
    });
  },

  mouseEnterDeleteButton(index) {
    this.setState({mouseOnDeleteIconIndex: parseInt(index)});
  },

  mouseLeaveDeleteButton() {
    this.setState({mouseOnDeleteIconIndex: -1});
  },

  getInitialState() {
    return {
      // If negative, the mouse is not on any delete button; otherwise, this
      // value is the index of task in task list that holds the delete button
      // the mouse is currently on, 0 means the mouse is on the title bar's
      // delete button.
      mouseOnDeleteIconIndex: -1
    };
  },

  render() {
    const {tasks, cancelTask, dismissTask, retryTask} = this.props;

    let waitingTaskCount = 0;
    let runningTaskCount = 0;
    let succeededTaskCount = 0;
    let failedTaskCount = 0;
    tasks.map(task => {
      switch (task.get('state')) {
        case TaskStates.WAITING: waitingTaskCount++; break;
        case TaskStates.RUNNING: runningTaskCount++; break;
        case TaskStates.SUCCEEDED: succeededTaskCount++; break;
        case TaskStates.FAILED: waitingTaskCount++; break;
      }
    });
    let taskSummary = `${waitingTaskCount} waiting, ` +
        `${runningTaskCount} running, ` +
        `${succeededTaskCount} succeeded, ` +
        `${failedTaskCount} failed`;

    // TODO(littlecvr): refactor style attributes, use className if possible.
    var titleBarDeleteIconColor = grey700;
    var deleteIconsShouldChangeColor = false;

    if (this.state.mouseOnDeleteIconIndex == 0) {
      // if the mouse is on the delete icon on title bar, change the color of
      // all delete icons
      titleBarDeleteIconColor = black;
      deleteIconsShouldChangeColor = true;
    } else if (this.state.mouseOnDeleteIconIndex >= 1) {
      // if the mouse is on one of the delete icon (except the one on title
      // bar), determine whether to change color or not by the state of the task
      var mouseOnDeleteIconTaskState = tasks.getIn([
        tasks.keySeq().sort().get(this.state.mouseOnDeleteIconIndex - 1),
        'state'
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
            onTouchTap={() => this.props.setCollapsed(!this.props.collapsed)}
          >
            <CardHeader title={'Tasks'} subtitle={taskSummary} style={{
              display: 'table-cell', verticalAlign: 'middle', padding: 12
            }}/>
            <CardActions style={{
              display: 'table-cell', textAlign: 'right',
              verticalAlign: 'middle', padding: 0
            }}>
              {!this.props.collapsed &&
                <span
                  onMouseEnter={() => this.mouseEnterDeleteButton(0)}
                  onMouseLeave={this.mouseLeaveDeleteButton}
                  style={{marginRight: 0}}
                >
                  <IconButton
                    tooltip={'cancel all waiting tasks'}
                    onTouchTap={this.cancelAllWaitingTasks}
                    iconStyle={{fill: titleBarDeleteIconColor}}
                  >
                    <DeleteIcon />
                  </IconButton>
                </span>
              }
              {!this.props.collapsed &&
                <IconButton
                  tooltip={'dismiss all finished tasks'}
                  onTouchTap={this.dismissAllSucceededTasks}
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
                  display: 'inline-block', width: 48, height: 1, marginRight: 0
                }}></div>
              }
              {this.props.collapsed &&
                <div style={{
                  display: 'inline-block', width: 48, height: 1, marginRight: 0
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
          tasks.keySeq().sort().toArray().map((taskID, index) => {
            // make this 1-based array since 0 is reserved for the title bar
            index = index + 1;
            var task = tasks.get(taskID);
            var deleteIconColor = grey700;
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
});

function mapStateToProps(state) {
  return {
    tasks: state.getIn(['dome', 'tasks'])
  };
}

function mapDispatchToProps(dispatch) {
  return {
    cancelTask: taskID =>
        dispatch(DomeActions.cancelTaskAndItsDependencies(taskID)),
    dismissTask: taskID => dispatch(DomeActions.removeTask(taskID)),
    retryTask: taskID => console.warn('not implemented yet')
  };
}

export default connect(mapStateToProps, mapDispatchToProps)(TaskList);
