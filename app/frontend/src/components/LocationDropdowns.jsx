import React, { Component } from 'react';
import { Field, reduxForm } from 'redux-form';
import '../styles/LocationDropdowns.css';
import { connect } from 'react-redux';


class LocationDropdowns extends Component {
    render() {
        const { nodes, settings, show } = this.props;
        return ( nodes && show &&
            <>
            <form>
                <label className='label'>Origin</label>
                <Field name='origin' component='select'>
                    {
                        nodes && nodes.filter(node => {
                            if (settings && settings.advSettings && settings.advSettings.values //grab the origin nodes value and don't show it
                                && settings.advSettings.values.destination) {
                                return settings.advSettings.values.destination.toString() !== node.id.toString();
                            } else {
                                return true;
                            }
                        }).map(node => {

                            return <option
                                key={node.id}
                                value={node.id}
                            >{node.location}</option>;
                        })
                    }
                </Field>
                <label className='label'>Destination</label>
                <Field name='destination' component='select'>
                    {
                        nodes && nodes.filter(node => {
                            if (settings && settings.advSettings && settings.advSettings.values //grab the origin nodes value and don't show it
                                && settings.advSettings.values.origin) {
                                return settings.advSettings.values.origin.toString() !== node.id.toString();
                            } else {
                                return true;
                            }
                        })
                            .map(node => {
                                return <option
                                    key={node.id}
                                    value={node.id}
                                >{node.location}</option>;
                            })
                    }
                </Field>
            </form>
            </>
        );
    }
}
// Allows form to communicate with store
LocationDropdowns = reduxForm({
    // a unique name for the form
    form: 'advSettings',
    enableReinitialize: true
})(LocationDropdowns);
// now set initialValues using data from your store state
LocationDropdowns = connect(
    state => ({
        initialValues: {
            origin: Object.keys(state.nodes).length ? state.nodes[Object.keys(state.nodes)[0]].id : undefined,
            destination: Object.keys(state.nodes).length ? state.nodes[Object.keys(state.nodes)[1]].id : undefined,
        }
    }),
)(LocationDropdowns);
export default LocationDropdowns;