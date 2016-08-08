// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import Immutable from 'immutable';
import React from 'react';
import ReactDOM from 'react-dom';
import injectTapEventPlugin from 'react-tap-event-plugin';
import {createStore, applyMiddleware} from 'redux';
import {Provider} from 'react-redux';
import thunkMiddleware from 'redux-thunk';
import createLogger from 'redux-logger';
import getMuiTheme from 'material-ui/styles/getMuiTheme';
import MuiThemeProvider from 'material-ui/styles/MuiThemeProvider';

// Needed for onTouchTap, see:
// http://www.material-ui.com/#/get-started/installation
injectTapEventPlugin();

const store = createStore(
  state => state,  // dummy redudcer for now
  Immutable.Map(),  // initial state will be determined by each reducer
  applyMiddleware(
    thunkMiddleware,
    createLogger({
      // Transform immutable state to plain object or it will be hard to read.
      stateTransformer: s => Immutable.Iterable.isIterable(s) ? s.toJS() : s
    })  // logger middleware
  )
);

const DomeApp = () => <div>DomeApp</div>;

const App = () => (
  <MuiThemeProvider muiTheme={getMuiTheme()}>
    <Provider store={store}>
      <DomeApp />
    </Provider>
  </MuiThemeProvider>
);

ReactDOM.render(
  <App />,
  document.getElementById('app')
);
