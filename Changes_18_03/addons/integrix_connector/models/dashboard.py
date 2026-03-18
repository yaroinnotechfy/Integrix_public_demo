# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class IntegrixDashboard(models.Model):
    _name = "integrix.dashboard"
    _description = "Integri-x Sync Dashboard"
    _rec_name = "name"

    key = fields.Char(default="singleton", readonly=True, index=True)
    name = fields.Char(default="Integri-x Sync Dashboard", required=True)

    connection_status = fields.Selection(
        [("ok", "OK"), ("fail", "FAIL"), ("na", "N/A")],
        string="Connection",
        compute="_compute_info",
        store=False,
    )
    base_url = fields.Char(readonly=True, compute="_compute_info", store=False)
    api_version = fields.Char(readonly=True, compute="_compute_info", store=False)
    tenant = fields.Char(readonly=True, compute="_compute_info", store=False)
    last_sync = fields.Datetime(readonly=True, compute="_compute_info", store=False)

    _sql_constraints = [
        ('integrix_dashboard_singleton_unique', 'unique(key)', 'Only one Integri-x Dashboard record is allowed.')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if self.search_count([]) > 0:
            raise ValidationError(_("Only one Integri-x Dashboard is allowed."))
        for v in vals_list:
            v.setdefault('key', 'singleton')
            v.setdefault('name', 'Integri-x Sync Dashboard')
        return super().create(vals_list)

    @api.depends()
    def _compute_info(self):
        ICP = self.env["ir.config_parameter"].sudo()
        for rec in self:
            ping = (ICP.get_param("integrix_connector.ping_status") or "").upper()
            rec.connection_status = "ok" if ping == "OK" else ("fail" if ping == "FAIL" else "na")
            rec.base_url = ICP.get_param("integrix_connector.base_url") or ""
            rec.api_version = ICP.get_param("integrix_connector.api_version") or ""
            rec.tenant = ICP.get_param("integrix_connector.ping_tenant") or ""
            val = ICP.get_param("integrix_connector.last_sync_dt") or ""
            rec.last_sync = fields.Datetime.from_string(val) if val else False
