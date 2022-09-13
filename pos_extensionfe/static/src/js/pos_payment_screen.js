odoo.define('pos_extensionfe.pos_payment_screen', function(require) {
    'use strict';

    const { Gui } = require('point_of_sale.Gui');
    const ProductScreen = require('point_of_sale.ProductScreen');
    const Registries = require('point_of_sale.Registries');

    const PosPaymentScreen = ProductScreen =>
        class extends ProductScreen {
        _onClickPay() {
                var self = this;
                if(!this.env.pos.config.x_deny_payments){
                    self.showScreen('PaymentScreen');
                }
                else{
                    // Gui.showPopup('ErrorPopup',{
                    //                 'title': 'Operación deshabilitada',
                    //                 'body': 'La opción de pago está deshabilitada para este Punto de venta',
                    //             });
                }
            }
        };

    Registries.Component.extend(ProductScreen, PosPaymentScreen);

    return ProductScreen;
});
