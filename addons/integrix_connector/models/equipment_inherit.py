from odoo import api, fields, models, _
from odoo.exceptions import UserError
from urllib.parse import quote

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    x_integrix_external_id = fields.Char(string='Integri-x External ID', index=True, copy=False)
    x_criticality = fields.Char(string='Criticality')
    x_manufacturer = fields.Char(string='Manufacturer')
    x_model = fields.Char(string='Model (Integri-x)')
    x_uom = fields.Char(string='UoM')
    x_cost_center = fields.Char(string='Cost Center')

    integrix_linked_count = fields.Integer(string="Linked", compute="_compute_integrix_linked_count")

    @api.depends('x_integrix_external_id')
    def _compute_integrix_linked_count(self):
        for rec in self:
            rec.integrix_linked_count = 1 if (rec.x_integrix_external_id or '').strip() else 0

    def _ix_get_base_url(self):
        cfg = self.env['integrix.config'].sudo().search([], limit=1)
        return (cfg.base_url or 'https://api.integri-x.com/').rstrip('/')

    def _ix_url_for_equipment(self):
        self.ensure_one()
        base = self._ix_get_base_url()
        if not base:
            return ""
        ext = (self.x_integrix_external_id or '').strip()
        return f"{base}/?externalId={quote(ext)}" if ext else base

    def action_link_integrix(self):
        for rec in self:
            if not (rec.x_integrix_external_id or '').strip():
                rec.x_integrix_external_id = (rec.serial_no or '').strip() or str(rec.id)
        # миттєво оновлюємо форму
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_unlink_integrix(self):
        self.write({'x_integrix_external_id': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_open_integrix(self):
        self.ensure_one()
        url = self._ix_url_for_equipment()
        if not url:
            raise UserError(_("Base URL is not configured in Integri-x Settings."))
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def action_sync_integrix(self):
        self.ensure_one()
        res = self.env["integrix.push"].push_equipment(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Integri-x"), "message": _("Pushed to Integri-x: %(n)s asset(s).") % {"n": res.get("pushed", 0)}, "type": "success", "sticky": False},
        }
