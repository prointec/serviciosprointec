odoo.define('pos_extensionfe.printReports', function (require) {
  "use strict";

  var Session = require('web.Session');

  // Session
  Session.include({
    get_file: function (options) {
        return this._super.apply(this, arguments);
    }
  });
});
