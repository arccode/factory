import {StateType} from 'typesafe-actions';

import {rootReducer} from './index';

export type RootState = StateType<typeof rootReducer>;
