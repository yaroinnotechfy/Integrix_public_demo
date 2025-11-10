from odoo import api, models, _
from odoo.exceptions import UserError

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    @api.model
    def action_bulk_link(self):
        records = self.browse(self.env.context.get('active_ids', []))
        for rec in records:
            if not (rec.x_integrix_external_id or '').strip():
                rec.x_integrix_external_id = (rec.serial_no or '').strip() or str(rec.id)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def action_bulk_unlink(self):
        records = self.browse(self.env.context.get('active_ids', []))
        records.write({'x_integrix_external_id': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def action_bulk_sync(self):
        records = self.browse(self.env.context.get('active_ids', []))
        res = self.env["integrix.push"].push_equipment(records)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Integri-x",
                       "message": _("Pushed: %(p)s, skipped: %(s)s, errors: %(e)s") % {"p": res.get("pushed", 0), "s": res.get("skipped", 0), "e": res.get("errors", 0)},
                       "type": "success",
                       "sticky": False},
        }

    @api.model
    def action_import_from_integrix(self):
        """MVP: перевіряємо доступність API і показуємо скільки елементів приходить.
        Реальний імпорт (створення/оновлення записів) додамо в Story 1.4.
        """
        cfg = self.env['integrix.config'].sudo().search([], limit=1)
        if not cfg:
            raise UserError(_("Configure Integri-x Settings first."))
        if not (cfg.base_url and cfg.api_email and cfg.api_password and cfg.company_id):
            raise UserError(_("Please fill Base URL, API Email, API Password and Company ID in Integri-x Settings."))

        probe_path = (cfg.probe_path or "").strip() or "api/companies/{companyId}/CompanyAssets"

        client = self.env['integrix.client']
        ok, result = client.probe_company_assets(
            cfg.base_url, cfg.api_email, cfg.api_password, cfg.company_id, probe_path
        )
        if not ok:
            # result = error string
            raise UserError(_(str(result)))

        body = result.get("body")
        count = len(body) if isinstance(body, list) else (1 if body else 0)
        msg = _("API reachable. Assets visible: %s. Full import will be implemented in Story 1.4.") % count

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Integri-x"), "message": msg, "type": "success", "sticky": False},
        }
