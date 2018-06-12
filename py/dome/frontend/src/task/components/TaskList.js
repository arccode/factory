// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import {Card, CardActions, CardHeader} from 'material-ui/Card';
import IconButton from 'material-ui/IconButton';
import {grey700} from 'material-ui/styles/colors';
import DismissIcon from 'material-ui/svg-icons/action/check-circle';
import DeleteIcon from 'material-ui/svg-icons/action/delete';
import CollapseIcon from 'material-ui/svg-icons/navigation/expand-less';
import ExpandIcon from 'material-ui/svg-icons/navigation/expand-more';
import PropTypes from 'prop-types';
import React from 'react';
import {connect} from 'react-redux';

import * as actions from '../actions';
import {isCancellable, isRunning, TaskStates} from '../constants';

import Task from './Task';

class TaskList extends React.Component {
  static propTypes = {
    collapsed: PropTypes.bool.isRequired,
    setCollapsed: PropTypes.func.isRequired,

    tasks: PropTypes.instanceOf(Immutable.OrderedMap).isRequired,
    cancelWaitingTaskAfter: PropTypes.func.isRequired,
    dismissTask: PropTypes.func.isRequired,
    retryTask: PropTypes.func.isRequired,
  };

  cancelAllWaitingTasks = (event) => {
    event.stopPropagation();
    this.props.cancelWaitingTaskAfter(this.props.tasks.keySeq().first());
  };

  dismissAllSucceededTasks = (event) => {
    event.stopPropagation();
    this.props.tasks
        .filter((task) => task.get('state') === TaskStates.SUCCEEDED)
        .keySeq()
        .forEach((id) => this.props.dismissTask(id));
  };

  mouseEnterDeleteButton = (index) => {
    this.setState({mouseOnDeleteIconIndex: parseInt(index)});
  };

  mouseLeaveDeleteButton = () => {
    this.setState({mouseOnDeleteIconIndex: -1});
  };

  render() {
    const {tasks, cancelWaitingTaskAfter, dismissTask, retryTask} = this.props;

    const counts =
        tasks.groupBy((t) => t.get('state')).map((tasks) => tasks.count());
    const running = tasks.count((task) => isRunning(task.get('state')));
    const hasCancellableTask =
        tasks.some((task) => isCancellable(task.get('state')));

    const taskSummary = `${counts.get(TaskStates.WAITING, 0)} waiting, ` +
        `${running} running, ` +
        `${counts.get(TaskStates.SUCCEEDED, 0)} succeeded, ` +
        `${counts.get(TaskStates.FAILED, 0)} failed`;

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
                <>
                  <IconButton
                    tooltip={'cancel all waiting tasks'}
                    onClick={this.cancelAllWaitingTasks}
                    style={{marginRight: 0}}
                    iconStyle={{fill: grey700}}
                    disabled={!hasCancellableTask}
                  >
                    <DeleteIcon />
                  </IconButton>
                  <IconButton
                    tooltip={'dismiss all finished tasks'}
                    onClick={this.dismissAllSucceededTasks}
                    style={{marginRight: 0}}
                    iconStyle={{fill: 'green'}}
                  >
                    <DismissIcon />
                  </IconButton>
                  <IconButton
                    tooltip={'collapse'}
                    style={{marginRight: 0}}
                  >
                    <CollapseIcon />
                  </IconButton>
                </>
              }
              {this.props.collapsed &&
                <>
                  {/* two padding blank icons */}
                  <div style={{
                    display: 'inline-block', width: 48, height: 1,
                    marginRight: 0,
                  }}></div>
                  <div style={{
                    display: 'inline-block', width: 48, height: 1,
                    marginRight: 0,
                  }}></div>
                  <IconButton
                    tooltip={'expand'}
                    style={{marginRight: 0}}
                  >
                    <ExpandIcon />
                  </IconButton>
                </>
              }
            </CardActions>
          </div>
        }

        {/* task list */}
        {!this.props.collapsed &&
          tasks.map((task, taskID) => {
            return (
              <Task
                key={taskID}
                state={task.get('state')}
                description={task.get('description')}
                progress={task.get('progress')}
                cancel={() => cancelWaitingTaskAfter(taskID)}
                dismiss={() => dismissTask(taskID)}
                retry={() => retryTask(taskID)}
              />
            );
          }).valueSeq()}
      </Card>
    );
  }
}

const mapStateToProps = (state) => {
  return {
    tasks: state.getIn(['task', 'tasks']),
  };
};

const mapDispatchToProps = (dispatch) => {
  return {
    cancelWaitingTaskAfter: (taskID) => (
      dispatch(actions.cancelWaitingTaskAfter(taskID))
    ),
    dismissTask: (taskID) => dispatch(actions.dismissTask(taskID)),
    retryTask: (taskID) => console.warn('not implemented yet'),
  };
};

export default connect(mapStateToProps, mapDispatchToProps)(TaskList);
