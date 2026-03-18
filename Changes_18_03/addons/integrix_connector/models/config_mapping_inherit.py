from odoo import models, fields

class IntegrixConfig(models.Model):
    _inherit = 'integrix.config'

    mapping_ids = fields.One2many(
        'integrix.field.map', 'config_id',
        string='Field Mapping'
    )
