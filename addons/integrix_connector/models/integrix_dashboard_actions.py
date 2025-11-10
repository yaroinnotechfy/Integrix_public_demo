# -*- coding: utf-8 -*-
from odoo import models

class IntegrixDashboardActions(models.Model):
    _inherit = 'integrix.dashboard'

    def action_open_settings(self):
        self.ensure_one()
        cfg = self.env['integrix.config'].sudo().search([], limit=1)
        if not cfg:
            cfg = self.env['integrix.config'].sudo().create({})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Integri-x Settings',
            'res_model': 'integrix.config',
            'view_mode': 'form',
            'target': 'current',
            'res_id': cfg.id,
        }

    def action_open_wizard(self):
        action = self.env.ref('integrix_connector.action_integrix_setup_wizard', raise_if_not_found=False)
        if action:
            return action.read()[0]
        return {
            'type': 'ir.actions.act_window',
            'name': 'Integri-x Sync Dashboard',
            'res_model': 'integrix.dashboard',
            'view_mode': 'form',
            'target': 'current',
        }
