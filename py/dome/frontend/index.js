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
import {reducer as formReducer} from 'redux-form/immutable';
import {combineReducers} from 'redux-immutable';
import {createLogger} from 'redux-logger';
import thunkMiddleware from 'redux-thunk';

import DomeApp from './components/DomeApp';
import bundlesReducer from './reducers/bundlesreducer';
import domeReducer from './reducers/domereducer';
import serviceReducer from './reducers/servicereducer';
import taskReducer from './reducers/taskreducer';

const THEME = {
  palette: {
    primary1Color: indigo500,
  },
};

const store = createStore(
    combineReducers({
      dome: domeReducer,
      bundles: bundlesReducer,
      service: serviceReducer,
      task: taskReducer,
      form: formReducer,
    }),
    Immutable.Map(), // initial state will be determined by each reducer
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
