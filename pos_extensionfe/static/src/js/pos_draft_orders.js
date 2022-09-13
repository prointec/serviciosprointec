odoo.define('pos_draft_orders.pos_draft_orders', function(require) {
    "use strict";
    var models = require('point_of_sale.models');
    const { Gui } = require('point_of_sale.Gui');

    var _super_order = models.Order.prototype;
    models.Order = models.Order.extend({
        initialize: function(attr,options) {
            this.x_is_partial = false;
            this.x_document_type = false;
            this.x_name_to_print = false;
            this.note = false;
            _super_order.initialize.call(this,attr,options);
        },
        set_name_to_print: function(name_to_print){
            this.x_name_to_print = name_to_print;
            this.trigger('change', this);
        },
        get_name_to_print: function(){
            return this.x_name_to_print;
        },

        set_document_type: function(document_type){
            this.x_document_type = document_type;
            this.trigger('change', this);
        },
        get_document_type: function(){
            return this.x_document_type;
        },

        set_note: function(note){
            this.note = note;
            this.trigger('change', this);
        },
        get_note: function(){
            return this.note;
        },

        export_as_JSON: function(){
            var loaded = _super_order.export_as_JSON.apply(this, arguments);
            loaded.x_is_partial = this.x_is_partial;
            loaded.x_amount_due = this.x_amount_due;
            loaded.x_name_to_print = this.x_name_to_print;
            loaded.x_document_type = this.x_document_type;
            loaded.note = this.note;
            return loaded;
        },
        init_from_JSON: function(json){
            _super_order.init_from_JSON.apply(this, arguments);
            this.x_is_partial = json.x_is_partial;
            this.x_name_to_print = json.x_name_to_print;
            this.x_document_type = json.x_document_type;
            this.note = json.note;
            // _super_order.init_from_JSON.call(this, json);
        },
    });

});
