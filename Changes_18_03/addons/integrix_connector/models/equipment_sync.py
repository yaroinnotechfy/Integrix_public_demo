from odoo import models, _
from odoo.exceptions import UserError

class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    def action_import_from_integrix(self):
        # запускаємо сервіс, показуємо нотифікацію
        res = self.env["integrix.sync"].run_import_once()
        msg = _("Import finished — created: %(c)s, updated: %(u)s, skipped: %(s)s") % {
            "c": res.get("created", 0), "u": res.get("updated", 0), "s": res.get("skipped", 0)
        }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Integri-x"), "message": msg, "type": "success", "sticky": False},
        }
