from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Dashboard singleton + res_id у дії
    dash = env['integrix.dashboard'].sudo().search([], limit=1)
    if not dash:
        dash = env['integrix.dashboard'].sudo().create({'name': 'Integri-x Sync'})
    act_dash = env.ref('integrix_connector.action_integrix_dashboard', raise_if_not_found=False)
    if act_dash and act_dash.type == 'ir.actions.act_window':
        act_dash.sudo().write({'res_id': dash.id})

    # Settings singleton + res_id у дії
    cfg = env['integrix.config'].sudo().search([], limit=1)
    if not cfg:
        cfg = env['integrix.config'].sudo().create({})
    act_cfg = env.ref('integrix_connector.action_integrix_config', raise_if_not_found=False)
    if act_cfg and act_cfg.type == 'ir.actions.act_window':
        act_cfg.sudo().write({'res_id': cfg.id})
