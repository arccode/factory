// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {indigo500} from 'material-ui/styles/colors';
import getMuiTheme from 'material-ui/styles/getMuiTheme';
import MuiThemeProvider from 'material-ui/styles/MuiThemeProvider';
import React from 'react';
import ReactDOM from 'react-dom';
import {Provider} from 'react-redux';
import {applyMiddleware, combineReducers, createStore} from 'redux';
import {reducer as reduxFormReducer} from 'redux-form';
import {createLogger} from 'redux-logger';
import thunkMiddleware from 'redux-thunk';

import auth from '@app/auth';
import bundle from '@app/bundle';
import config from '@app/config';
import domeApp from '@app/domeApp';
import DomeApp from '@app/domeApp/components/DomeApp';
import error from '@app/error';
import formDialog from '@app/formDialog';
import project from '@app/project';
import service from '@app/service';
import task from '@app/task';

const THEME = {
  palette: {
    primary1Color: indigo500,
  },
};

export const rootReducer = combineReducers({
  [auth.constants.NAME]: auth.reducer,
  [bundle.constants.NAME]: bundle.reducer,
  [config.constants.NAME]: config.reducer,
  [domeApp.constants.NAME]: domeApp.reducer,
  [error.constants.NAME]: error.reducer,
  [formDialog.constants.NAME]: formDialog.reducer,
  form: reduxFormReducer,
  [project.constants.NAME]: project.reducer,
  [service.constants.NAME]: service.reducer,
  [task.constants.NAME]: task.reducer,
});

const store = createStore(
  rootReducer,
  applyMiddleware(thunkMiddleware, createLogger()));

class App extends React.Component {
  componentDidMount() {
    // check if user's using Chrome/Chromium
    if (!navigator.userAgent.includes('Chrome')) {
      window.alert(`Warning!!
To visit Dome, please use Chrome/Chromium to avoid unnecessary issues.`);
    }
  }

  render() {
    return (
      <MuiThemeProvider muiTheme={getMuiTheme(THEME)}>
        <Provider store={store}>
          <DomeApp />
        </Provider>
      </MuiThemeProvider>
    );
  }
}

ReactDOM.render(
  <App />,
  document.getElementById('app'),
);
