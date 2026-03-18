from odoo import models, fields

class IntegrixFieldMap(models.Model):
    _name = 'integrix.field.map'
    _description = 'Integri-x ⇆ Odoo Field Mapping'
    _order = 'sequence, id'

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    # до чого належить
    config_id = fields.Many2one('integrix.config', required=True, ondelete='cascade')

    # мінімальний набір полів для мапінгу
    ix_field = fields.Char(string='Integri-x Field', required=True)
    odoo_field = fields.Char(string='Odoo Field', required=True)
