// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'isomorphic-fetch';

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

import DomeApp from './app/components/DomeApp';
import appReducer from './app/reducer';
import authReducer from './auth/reducer';
import bundleReducer from './bundle/reducer';
import configReducer from './config/reducer';
import errorReducer from './error/reducer';
import formDialogReducer from './formDialog/reducer';
import projectReducer from './project/reducer';
import serviceReducer from './service/reducer';
import taskReducer from './task/reducer';

const THEME = {
  palette: {
    primary1Color: indigo500,
  },
};

const store = createStore(
    combineReducers({
      app: appReducer,
      auth: authReducer,
      bundle: bundleReducer,
      config: configReducer,
      error: errorReducer,
      form: reduxFormReducer,
      formDialog: formDialogReducer,
      project: projectReducer,
      service: serviceReducer,
      task: taskReducer,
    }),
    applyMiddleware(
        thunkMiddleware,
        createLogger({
          // Transform immutable state to plain object or it will be
          // hard to read.
          stateTransformer:
              (s) => Immutable.Iterable.isIterable(s) ? s.toJS() : s,
        })));

class App extends React.Component {
  componentDidMount() {
    // check if user's using Chrome/Chromium
    if (navigator.userAgent.indexOf('Chrome') == -1) {
      window.alert('Warning!!\n\n' +
                   'To visit Dome, please use Chrome/Chromium to ' +
                   'avoid unnecessary issues.');
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
    document.getElementById('app')
);
