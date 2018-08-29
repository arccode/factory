// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {
  Action,
  AnyAction,
  combineReducers,
  Dispatch as ReduxDispatch,
  MiddlewareAPI,
  Reducer,
} from 'redux';
import {createAction, getType} from 'typesafe-actions';

import {APP_STATE_ROOT} from '@app/constants';
import {RootState} from '@app/types';

export interface OptimisticUpdateActionMetadata {
  meta: {
    isOptimistic: boolean | null,
  };
}

const withOptimisticUpdateMiddlewareFactory = () => {
  let optimisticUpdating: boolean | null = null;
  return {
    setOptimisticUpdating: (updating: boolean | null) => {
      optimisticUpdating = updating;
    },
    middleware: (store: MiddlewareAPI) => (next: ReduxDispatch) =>
      (action: AnyAction) => {
        if (action.meta === undefined) {
          action.meta = {};
        }
        action.meta.isOptimistic = optimisticUpdating;
        return next(action);
      },
  };
};

const {
  setOptimisticUpdating,
  middleware,
} = withOptimisticUpdateMiddlewareFactory();

export {setOptimisticUpdating, middleware};

export const resetOptimisticUpdate = createAction('RESET_OPTIMISTIC_UPDATE');

export const filterOptimisticUpdateAction = <
  S,
  A extends OptimisticUpdateActionMetadata & Action
>(reducer: Reducer<S, A>, display: boolean) => (
  state: S | undefined,
  action: A,
) => {
  if (state !== undefined &&
    action.meta.isOptimistic !== null &&
    action.meta.isOptimistic !== display) {
    return state;
  }
  return reducer(state, action);
};

interface StateWithOptimisticUpdate<S> {
  display: S;
  real: S;
}

export const wrapReducer = <
  S,
  A extends OptimisticUpdateActionMetadata & Action,
>(reducer: Reducer<S, A>): Reducer<StateWithOptimisticUpdate<S>, A> => {
  const combined = combineReducers({
    display: filterOptimisticUpdateAction(reducer, true),
    real: filterOptimisticUpdateAction(reducer, false),
  });
  return (state: StateWithOptimisticUpdate<S> | undefined, action: A) => {
    if (state !== undefined && action.type === getType(resetOptimisticUpdate)) {
      return {real: state.real, display: state.real};
    }
    return combined(state, action);
  };
};

export const displayedState = (state: RootState) =>
  state[APP_STATE_ROOT].display;
