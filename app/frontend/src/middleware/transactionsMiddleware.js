import {
    setTransactionFetchStatus,
    setTimingFetchStatus,
} from '../actions/transactions';

import {
    FETCH_TRANSACTION,
    ADD_TRANSACTIONS,
    ADD_TIMING_DATA
} from '../actions/table';

import {appendPastResults} from 'actions/pastResults';

// 'Listens' for actions and will dispatch others while they are occurring
const transactionsMiddleware = store => next => action => {
    switch(action.type) {
        case FETCH_TRANSACTION:
            store.dispatch(setTransactionFetchStatus(true));
            break;
        case ADD_TRANSACTIONS:
            store.dispatch(setTransactionFetchStatus(false));
            store.dispatch(setTimingFetchStatus(true));
            break;
        case ADD_TIMING_DATA:
            store.dispatch(setTimingFetchStatus(false));
            store.dispatch(appendPastResults(action.timingData));
            break;
        default:
            break;
    }
    next(action);
};

export default transactionsMiddleware;