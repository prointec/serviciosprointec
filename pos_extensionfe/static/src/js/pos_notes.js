odoo.define('pos_extensionfe.pos_notes',function(require) {
    "use strict";

    const { useState, useRef ,useSubEnv} = owl.hooks;
    const Registries = require('point_of_sale.Registries');
    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');


class NotesWidget extends AbstractAwaitablePopup {
    constructor() {
            super(...arguments);
            this.state = useState({ inputValue: this.props.startingValue });
            this.inputRef = useRef('input');
            useSubEnv({ attribute_components: [] });
        }

    click_confirm() {
            var self = this;
            var order = this.env.pos.get_order();
            var x_document_type = $('select[name="x_document_type_id"]').val();
            var name_to_print = $("#name").val();
            var notes = $("#notes").val();
            order.set_document_type(x_document_type)
            order.set_name_to_print(name_to_print)
            order.set_note(notes)
            this.trigger('close-popup');
            this.showScreen('ProductScreen')
        }
    }
    NotesWidget.template = 'NotesWidget';
    NotesWidget.defaultProps = {
        confirmText: 'Return',
        cancelText: 'Cancel',
        title: 'Confirm ?',
        body: '',
    };

    Registries.Component.add(NotesWidget);
    return NotesWidget;

});