odoo.define('pos_extensionfe.CreatePOSNameToPrintButton', function(require) {
	"use strict";

    const PosComponent = require('point_of_sale.PosComponent');    //	var popups = require('point_of_sale.popups');
	const ProductScreen = require('point_of_sale.ProductScreen');  //var screens = require('point_of_sale.screens');
    const { useListener } = require('web.custom_hooks');
    const Registries = require('point_of_sale.Registries');
    const { Gui } = require('point_of_sale.Gui');

    var core = require('web.core');

    class CreatePOSNameToPrintButton extends PosComponent {
        constructor() {
            super(...arguments);
            useListener('click', this.onClick);
        }
        async onClick() {
            var order = this.env.pos.get_order();
            if (!order) return;
            
            var document_type = order.get_document_type()
            if (!document_type) document_type = ''

            var name_to_print = order.get_name_to_print()
            if (!name_to_print) {
                var partner_id = order.get_client();
                name_to_print = partner_id ? partner_id.name : '';
                document_type = partner_id ? 'FE' : document_type;
            }

            var note = order.get_note()
            if (!note) note = ''
            
            Gui.showPopup('NotesWidget',{order: order, name: name_to_print, document_type: document_type, note: note});
		}
    }
    CreatePOSNameToPrintButton.template = 'CreatePOSNameToPrintButton';

    ProductScreen.addControlButton({
        component: CreatePOSNameToPrintButton,
        condition: function() {
            return true;
        },
    });

    Registries.Component.add(CreatePOSNameToPrintButton);

    return CreatePOSNameToPrintButton;
});
