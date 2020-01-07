// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {indigo} from '@material-ui/core/colors';
import CssBaseline from '@material-ui/core/CssBaseline';
import {
  createMuiTheme,
  MuiThemeProvider,
} from '@material-ui/core/styles';
import React from 'react';
import ReactDOM from 'react-dom';
import {Provider} from 'react-redux';
import {applyMiddleware, createStore} from 'redux';
import {createLogger} from 'redux-logger';
import thunkMiddleware from 'redux-thunk';

import DomeApp from '@app/dome_app/components/dome_app';
import task from '@app/task';

import {
  middleware as optimisticUpdateMiddleware,
} from '@common/optimistic_update';

import rootReducer from './root_reducer';

const THEME = {
  palette: {
    primary: indigo,
  },
  typography: {
    useNextVariants: true,
  },
};

const configureStore = () => {
  const s = createStore(
    rootReducer,
    applyMiddleware(
      thunkMiddleware,
      optimisticUpdateMiddleware,
      createLogger(),
    ));

  if (module.hot) {
    module.hot.accept('./root_reducer', () => {
      const nextRootReducer = require('./root_reducer').default;
      s.replaceReducer(nextRootReducer);
    });
  }

  return s;
};

const store = configureStore();

window.addEventListener('unhandledrejection', (event) => {
  const error = (event as PromiseRejectionEvent).reason;
  if (error instanceof task.constants.CancelledTaskError) {
    return;
  }
  console.error(error);
});

ReactDOM.render(
  <>
    <CssBaseline />
    <MuiThemeProvider theme={createMuiTheme(THEME)}>
      <Provider store={store}>
        <DomeApp />
      </Provider>
    </MuiThemeProvider>
  </>,
  document.getElementById('app'),
);
