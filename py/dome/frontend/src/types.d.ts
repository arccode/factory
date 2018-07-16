import {AnyAction} from 'redux';
import {ThunkDispatch} from 'redux-thunk';
import {StateType} from 'typesafe-actions';

import {rootReducer} from './index';

export type RootState = StateType<typeof rootReducer>;
// TODO(pihsun): Have an action type that is union of all possible action?
export type Dispatch = ThunkDispatch<RootState, {}, AnyAction>;
