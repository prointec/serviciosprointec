# -*- coding: utf-8 -*-
{
    'name': "servicios_purchase_update",
    'summary': """
        Modificaciones al modulo de compras, se agrega columna de fecha """,
    'description': """
        Modificaciones al modulo de compras
    """,
    'author': "Prointec",
    'website': "http://www.prointeccr.com",
    'category': 'Varios',
    'version': '14',
    'depends': ['base', 'purchase',],
    'data': [
        'views/purchase_order_views.xml',
    ],
}
