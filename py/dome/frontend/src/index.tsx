// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {indigo500} from 'material-ui/styles/colors';
import getMuiTheme from 'material-ui/styles/getMuiTheme';
import MuiThemeProvider from 'material-ui/styles/MuiThemeProvider';
import React from 'react';
import ReactDOM from 'react-dom';
import {Provider} from 'react-redux';
import {applyMiddleware, createStore} from 'redux';
import {createLogger} from 'redux-logger';
import thunkMiddleware from 'redux-thunk';

import DomeApp from '@app/dome_app/components/dome_app';

import rootReducer from './root_reducer';

const THEME = {
  palette: {
    primary1Color: indigo500,
  },
};

const configureStore = () => {
  const s = createStore(
    rootReducer,
    applyMiddleware(thunkMiddleware, createLogger()));

  if (module.hot) {
    module.hot.accept('./root_reducer', () => {
      const nextRootReducer = require('./root_reducer').default;
      s.replaceReducer(nextRootReducer);
    });
  }

  return s;
};

const store = configureStore();

ReactDOM.render(
  <MuiThemeProvider muiTheme={getMuiTheme(THEME)}>
    <Provider store={store}>
      <DomeApp />
    </Provider>
  </MuiThemeProvider>,
  document.getElementById('app'),
);
