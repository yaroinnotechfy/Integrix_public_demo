from odoo import api, fields, models

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    x_is_linked = fields.Boolean(
        string='Linked?',
        compute='_compute_is_linked',
        store=False,
        search='_search_is_linked',
    )

    @api.depends('x_integrix_external_id')
    def _compute_is_linked(self):
        for rec in self:
            rec.x_is_linked = bool((rec.x_integrix_external_id or '').strip())

    def _search_is_linked(self, operator, value):
        #  домен через список id з/без trimmed value
        self.env.cr.execute("""
            SELECT id
            FROM maintenance_equipment
            WHERE COALESCE(BTRIM(x_integrix_external_id), '') <> ''
        """)
        linked_ids = [r[0] for r in self.env.cr.fetchall()]
        domain = [('id', 'in', linked_ids)]
        if (operator, value) in [('=', False), ('!=', True)]:
            domain = [('id', 'not in', linked_ids)]
        return domain
