# -*- coding: utf-8 -*-
{
    'name': "xSale price by Margin",
    'summary':
        """
        .Precio de venta basado en margen sobre el costo (actualiza 2 listas de precios)
        .En ordenes de venta tanto de pos como normales si el precio es igual o menos a costo no se permite
        """,
    'version': '14.0',
    'category': 'Extra Tools',
    'author': "PROINTEC",
    'website': "http://www.prointeccr.com",
    'license': 'AGPL-3',

    'depends': ['base', 'stock', 'sale', 'purchase_discount'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/product_views.xml',
        'views/purchase_order_views.xml',
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
}
