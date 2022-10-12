# -*- coding: utf-8 -*-
{
    'name': "xPurchase discount",
    'summary': """Registro de descuentos en Compras""",
    'description': """
    Permite digitar descuentos de forma porcentual o por monto concedidos por el proveedor para
    aplicar en la orden de compra.
    """,
    'category': 'Extra',    
    'version': '14',
    'author': "PROINTEC",
    'license': 'LGPL-3',
    'website': "http://www.prointeccr.com",
    'depends': ['base','stock','purchase', 'FAE_app'],
    'data': [
        'views/purchase_order_views.xml',
        'report/purchase_order_template.xml',        
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
}
