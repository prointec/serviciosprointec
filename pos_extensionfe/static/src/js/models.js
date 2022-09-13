odoo.define('pos_extensionfe.models', function (require) {
"use strict";

	var models = require('point_of_sale.models');
	var modules = models.PosModel.prototype.models;

	models.load_models({
        model:  'xidentification.type',
        fields: ['name'],
        loaded: function(self,identification_types){
            self.identification_types = identification_types;
            console.log('identificaction')
            console.log(identification_types)
        },
    });

    models.load_models({
        model:  'xcountry.county',
            fields: ['name', 'country_state_id'],
            loaded: function(self,counties){
                self.counties = counties;
            },
    });

    models.load_models({
        model:  'xcountry.district',
            fields: ['name', 'country_county_id'],
            loaded: function(self,districts){
                self.districts = districts;
            },
    });

    models.load_models({
        model:  'res.partner',
        label: 'load_partners',
        fields: ['name','street','city','state_id','country_id','x_country_county_id',
                 'x_country_district_id', 'x_identification_type_id', 'vat','lang',
                 'phone','zip','mobile','email','barcode','write_date',
                 'property_account_position_id','property_product_pricelist'],
        loaded: function(self,partners){
            self.partners = partners;
            self.db.add_partners(partners);
        },
    });

	for(var i=0; i<modules.length; i++){
		var model=modules[i];
		if(model.model === 'res.partner'){
			model.fields.push('x_country_county_id','x_country_district_id','x_identification_type_id');
		}
	}
});
