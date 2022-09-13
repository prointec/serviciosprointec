odoo.define('pos_extensionfe.pos_button_receipt', function (require) {
    "use strict";

    var ListController = require('web.ListController');

    var includeDict = {
        renderButtons: function () {
            this._super.apply(this, arguments);
//            console.log('o_insert_receipt1')
            if (this.modelName === "pos.order"){
//                console.log('o_insert_receipt2')
                var buttonLoad = this.$buttons.find('button.o_button_receipt')
                buttonLoad.on('click', this.proxy('o_insert_receipt'))
            }
        },

        o_insert_receipt: function () {
//            console.log('o_insert_receipt')
            var self = this;
            var state = self.model.get(self.handle, {raw: true});
            var data = this.controlPanelProps.action._originalAction;
            var arr = data.split("cashier_session_id")[1];
            var cashier_session_id = arr.split("},")[0].split(":")[1];

            return self.do_action({
                name: 'Abono a Crédito',
                type: 'ir.actions.act_window',
                res_model: 'xpos.receipt',
                target: 'new',
                views: [[false, 'form']],
                view_type: 'form',
                view_mode: 'form',
                context: {'default_cashier_session_id': cashier_session_id},
                flags: {'form': {'action_buttons':true, 'options':{'mode': 'edit'}}}
            });
        }
    };

    ListController.include(includeDict);

});
