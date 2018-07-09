// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import {indigo500} from 'material-ui/styles/colors';
import getMuiTheme from 'material-ui/styles/getMuiTheme';
import MuiThemeProvider from 'material-ui/styles/MuiThemeProvider';
import React from 'react';
import ReactDOM from 'react-dom';
import {Provider} from 'react-redux';
import {applyMiddleware, createStore} from 'redux';
import {reducer as reduxFormReducer} from 'redux-form/immutable';
import {combineReducers} from 'redux-immutable';
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

const reducerModules = [
  auth,
  bundle,
  config,
  domeApp,
  error,
  formDialog,
  project,
  service,
  task,
];

const store = createStore(
    combineReducers({
      ...reducerModules.reduce((obj, mod) => {
        obj[mod.constants.NAME] = mod.reducer;
        return obj;
      }, {}),
      form: reduxFormReducer,
    }),
    applyMiddleware(
        thunkMiddleware,
        createLogger({
          // Transform immutable state to plain object or it will be
          // hard to read.
          stateTransformer:
              (s) => Immutable.isImmutable(s) ? s.toJS() : s,
        })));

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
