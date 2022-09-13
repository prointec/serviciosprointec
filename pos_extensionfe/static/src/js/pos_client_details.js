odoo.define('pos_extensionfe.pos_client_details', function(require) {

    const ClientDetailsEdit = require('point_of_sale.ClientDetailsEdit');
    const Registries = require('point_of_sale.Registries');
    var rpc = require('web.rpc');

    const pos_ClientDetailsEdit = ClientDetailsEdit => class extends ClientDetailsEdit {
        constructor(){
				super(...arguments);
				this.intFields.push('x_country_county_id');
				this.intFields.push('x_country_district_id');
				this.intFields.push('x_identification_type_id');
			}

        captureChange(event) {
            this.changes[event.target.name] = event.target.value;
            var self = this;

            if (event.target.name === 'country_id'){
                rpc.query({
                    model: 'res.country.state',
                    method: 'search_read',
                    fields: ['name', 'country_id'],
                    args: [[['country_id', '=', parseInt(event.target.value)]]],
                })
                .then(function (states) {
                    self.env.pos.states = states;
                    self.render();
                });
            }
            else if (event.target.name === 'state_id'){
                rpc.query({
                    model: 'xcountry.county',
                    method: 'search_read',
                    fields: ['name', 'country_state_id'],
                    args: [[['country_state_id', '=', parseInt(event.target.value)]]],
                })
                .then(function (counties) {
                    self.env.pos.counties = counties;
                    self.render();
                });
            }
            else if (event.target.name === 'x_country_county_id'){
                rpc.query({
                    model: 'xcountry.district',
                    method: 'search_read',
                    fields: ['name', 'country_county_id'],
                    args: [[['country_county_id', '=', parseInt(event.target.value)]]],
                })
                .then(function (districts) {
                    self.env.pos.districts = districts
                    self.render();
                });
            }
        }

        saveChanges() {
            let processedChanges = {};
            for (let [key, value] of Object.entries(this.changes)) {
                if (this.intFields.includes(key)) {
                    processedChanges[key] = parseInt(value) || false;
                } else {
                    processedChanges[key] = value;
                }
            }

            if ((!this.props.partner.name && !processedChanges.name) ||
						processedChanges.name === '' ){
						return this.showPopup('ErrorPopup', {
							title: _('A Customer Name Is Required'),
						});
				}
            processedChanges.id = this.props.partner.id || false;
            this.trigger('save-changes', { processedChanges });
         }
    };

    Registries.Component.extend(ClientDetailsEdit, pos_ClientDetailsEdit);
    return ClientDetailsEdit;
});
