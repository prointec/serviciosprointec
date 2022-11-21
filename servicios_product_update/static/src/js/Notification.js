/** @odoo-module **/
odoo.define("servicios_product_update.po_notification", function(require) {
    const AbstractService = require('web.AbstractService');
    const { serviceRegistry, _t } = require('web.core');
    
    let interval = null;

    const PONotification = AbstractService.extend({
        dependencies: ['notification'],
        permission: false,
        async start() {
            await this._super.apply(this, arguments);

            (interval) && window.clearInterval(interval);
            
            const data = await this.getNotifyConfig();
            
            this.notify(); 
            interval = setInterval(() => this.notify(), (data?.time) ? (data.time * 1000) : 30_000);
            
            Notification.requestPermission()
                .then((result) => this.permission = result === "granted"); 
        },
        async getNotifyConfig() {
            return this._rpc({
                model: "res.company",
                method: "get_notification_config",
                args: [[this.env.session.company_id]],
            });
        },
        async notify() {
            const purchaseIds = await this._rpc({
                model: "purchase.order",
                method: "search_read",
                kwargs: {
                    domain: [
                        ["can_notify","=",true],
                        ["notified","=",false],
                    ],
                    fields: ['id'],
                },
            })

            if(!purchaseIds || !purchaseIds.length) return;
            
            let body = `Se han creado ${purchaseIds.length} nuevas PO para reabastecimiento`;

            const data = await this.getNotifyConfig();

            if(data?.msg) {
                body = data.msg.replace("%d", String(purchaseIds.length));
            }

            const title = _t("Compra");

            (this.permission) && new Notification(title, { body });
            this.do_notify(title, body);

            this._rpc({
                model: "purchase.order",
                method: "write",
                args: [purchaseIds.map(({ id }) => id), { notified: true }]
            });
        },
        destroy() {
            (interval) && window.clearInterval(interval);
            return this._super.apply(this, arguments);
        }
    });
    
    serviceRegistry.add('po-notification', PONotification);
    
    return PONotification;
});