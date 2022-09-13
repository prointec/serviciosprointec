odoo.define('pos_extensionfe.CreatePOSDraftButton', function(require) {
    "use strict";

    const PosComponent = require('point_of_sale.PosComponent');
    const ProductScreen = require('point_of_sale.ProductScreen');
    const { useListener } = require('web.custom_hooks');
    const Registries = require('point_of_sale.Registries');

    var core = require('web.core');
    var _t = core._t;

    class CreatePOSDraftButton extends PosComponent {
        constructor() {
            super(...arguments);
            useListener('click', this.onClick);
        }
        async onClick() {
            var order = this.env.pos.get_order();
            var orderlines = order.get_orderlines();
            var partner_id = order.get_client();
            var document_type = order.get_document_type();
            var name_to_print = order.get_name_to_print()

            if (partner_id && document_type == '-') {
                docment_type = 'FE';
                order.x_document_type = document_type
            }
            if (document_type == '-') {
                await this.showPopup('ErrorPopup', {
                    title: this.env._t('Tipo de documento'),
                    body: this.env._t('Debe seleccionar el tipo de documento antes de continuar.'),
                });
                return;
            } else if (document_type == 'FE' && !partner_id) {
                await this.showPopup('ErrorPopup', {
                    title: this.env._t('Tipo de documento'),
                    body: this.env._t('Cuando se emite una factura electrónica es necesario seleccionar un cliente'),
                });
                return;                
            }

            if (!partner_id && !name_to_print) {
                await this.showPopup('ErrorPopup', {
                    title: this.env._t('Nombre de Cliente'),
                    body: this.env._t('Debe seleccionar un cliente o ingresar un nombre para imprimir en el documento.'),
                });
                return;
            }

            if (orderlines.length == 0) {
                await this.showPopup('ErrorPopup', {
                    title: this.env._t('Empty Order'),
                    body: this.env._t('There must be at least one product in your order before it can be validated.'),
                });
                return;
            }

            let syncedOrderBackendIds = [];
            order.x_amount_due = order.get_due();
            order.x_is_partial = true;
            order.finalize();

            try {
                syncedOrderBackendIds = await this.env.pos.push_single_order(order);
            } catch (error) {
                if (error instanceof Error) {
                    throw error;
                } else {
                    await order._handlePushOrderError(error); //this._handlePushOrderError(error);
                }
            }
            if (syncedOrderBackendIds.length && order.wait_for_push_order()) {
                const result = await this._postPushOrderResolve(
                    order,
                    syncedOrderBackendIds
                );
                if (!result) {
                    await this.showPopup('ErrorPopup', {
                        title: 'Error: no internet connection.',
                        body: error,
                    });
                }
            }
            this.env.pos.add_new_order()
            //this.showScreen('ProductScreen');
            //this.showScreen(this.nextScreen);
        }
    }
    CreatePOSDraftButton.template = 'CreatePOSDraftButton';

    ProductScreen.addControlButton({
        component: CreatePOSDraftButton,
        condition: function() {
            return true; 
        },
    });

    Registries.Component.add(CreatePOSDraftButton);

    return CreatePOSDraftButton;
});
