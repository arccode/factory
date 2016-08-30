// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import ActionTypes from '../constants/ActionTypes';

const receiveBoards = boards => ({
  type: ActionTypes.RECEIVE_BOARDS,
  boards
});

// TODO(littlecvr): similar to fetchBundles, refactor code if possible
const fetchBoards = () => (dispatch, getState) => {
  fetch('/boards.json').then(response => {
    response.json().then(json => {
      dispatch(receiveBoards(json));
    }, error => {
      // TODO(littlecvr): better error handling
      console.log('error parsing board list response');
      console.log(error);
    });
  }, error => {
    // TODO(littlecvr): better error handling
    console.log('error fetching board list');
    console.log(error);
  });
};

const switchBoard = nextBoard => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_BOARD,
  prevBoard: getState().getIn(['dome', 'board']),
  nextBoard
});

const switchApp = nextApp => (dispatch, getState) => dispatch({
  type: ActionTypes.SWITCH_APP,
  prevApp: getState().getIn(['dome', 'app']),
  nextApp
});

export default {
  fetchBoards, switchBoard, switchApp
};
