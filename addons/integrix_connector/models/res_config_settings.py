from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ssot = fields.Selection(
        [("integrix", "Integri-x is source of truth"),
         ("odoo", "Odoo is source of truth")],
        default="integrix",
        string="Single Source of Truth (SSOT)",
        help="Who wins on conflicts and during initial sync.",
        config_parameter="integrix_connector.ssot",
    )

    sync_direction = fields.Selection(
        [("ix_to_odoo", "Integri-x → Odoo"),
         ("odoo_to_ix", "Odoo → Integri-x"),
         ("two_way", "Two-way (advanced)")],
        default="ix_to_odoo",
        string="Sync Direction",
        help="Default direction for scheduled jobs. Two-way requires conflict resolver.",
        config_parameter="integrix_connector.sync_direction",
    )
