// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import 'babel-polyfill';
import 'isomorphic-fetch';

import Immutable from 'immutable';
import React from 'react';
import ReactDOM from 'react-dom';
import injectTapEventPlugin from 'react-tap-event-plugin';
import {createStore, applyMiddleware} from 'redux';
import {combineReducers} from 'redux-immutable';
import {indigo500} from 'material-ui/styles/colors';
import {Provider} from 'react-redux';
import thunkMiddleware from 'redux-thunk';
import createLogger from 'redux-logger';
import getMuiTheme from 'material-ui/styles/getMuiTheme';
import MuiThemeProvider from 'material-ui/styles/MuiThemeProvider';

import DomeApp from './components/DomeApp';
import BundlesReducer from './reducers/bundlesreducer';
import DomeReducer from './reducers/domereducer';

// Needed for onTouchTap, see:
// http://www.material-ui.com/#/get-started/installation
injectTapEventPlugin();

const THEME = {
  palette: {
    primary1Color: indigo500
  }
};

const store = createStore(
  combineReducers({
    dome: DomeReducer,
    bundles: BundlesReducer
  }),
  Immutable.Map(),  // initial state will be determined by each reducer
  applyMiddleware(
    thunkMiddleware,
    createLogger({
      // Transform immutable state to plain object or it will be hard to read.
      stateTransformer: s => Immutable.Iterable.isIterable(s) ? s.toJS() : s
    })  // logger middleware
  )
);

const App = () => (
  <MuiThemeProvider muiTheme={getMuiTheme(THEME)}>
    <Provider store={store}>
      <DomeApp />
    </Provider>
  </MuiThemeProvider>
);

ReactDOM.render(
  <App />,
  document.getElementById('app')
);
