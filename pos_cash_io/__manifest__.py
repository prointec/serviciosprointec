# -*- coding: utf-8 -*-
{
    "name" : "POS ext cash in/out",
    "version" : "14.0.0.1",
    'category': 'Point of Sale',    
    'summary': 'Agrega en registro de ingresos o egresos de caja',
    "description": """
    """,
    'author': "PROINTEC",
    'website': "http://www.prointeccr.com",    
    'depends': ['base', 'point_of_sale'],
    'data': [
        'views/cash_box_out_views.xml',
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
