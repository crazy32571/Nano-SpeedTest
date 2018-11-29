import React from 'react';
import { BrowserRouter, Route, Switch } from 'react-router-dom';
import HomePage from './components/HomePage';
import UserResultsPage from './components/UserResultsPage';
import HistoricalDataView from './components/HistoricalData/HistoricalDataView';
import MoreInfoPage from './components/MoreInfoPage';
import NotFoundPage from './components/NotFoundPage';
import BuildAd from './components/BuildAd';
import ScrollToTop from 'components/ScrollToTop';

export default() => (
    <BrowserRouter>
        <ScrollToTop>
            <Switch>
                <Route path='/' component={HomePage} exact={true} />
                <Route path='/Stats' component={HistoricalDataView}/>
                <Route path='/Results' component={UserResultsPage}/>
                <Route path='/Info' component={MoreInfoPage}/>
                <Route path='/BuildAd' component={BuildAd}/>
                <Route component={NotFoundPage}/>
            </Switch>
        </ScrollToTop>
    </BrowserRouter>
);