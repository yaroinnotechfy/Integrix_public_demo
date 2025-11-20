from odoo import api, fields, models, _
from odoo.exceptions import UserError
import requests

class IntegrixSetupWizardLine(models.TransientModel):
    _name = 'integrix.setup.wizard.line'
    _description = 'Integri-x Setup Wizard Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('integrix.setup.wizard', required=True, ondelete='cascade')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    ix_field = fields.Char(required=True)
    odoo_field = fields.Char(required=True)


class IntegrixSetupWizard(models.TransientModel):
    def _tz_get(self):
        import pytz
        return [(tz, tz) for tz in pytz.all_timezones]
    _name = 'integrix.setup.wizard'
    _description = 'Integri-x Setup Wizard'

    # навігація: 0 (choice) → 0a (signup) → 1..4
    step = fields.Selection([
        ('0', 'Step 0'),
        ('0a','Step 0a'),
        ('1', 'Step 1'),
        ('2', 'Step 2'),
        ('3', 'Step 3'),
        ('4', 'Step 4'),
    ], default='0')

    # --- Step 0a: Sign-up fields ---
    signup_first_name   = fields.Char(string="First name")
    signup_last_name    = fields.Char(string="Last name")
    signup_company_name = fields.Char(string="Company name")
    signup_company_type = fields.Integer(string="Company type", default=1)
    signup_phone        = fields.Char(string="Phone")
    signup_email        = fields.Char(string="Email")
    signup_password     = fields.Char(string="Password")
    signup_time_zone = fields.Selection(selection='_tz_get', string='Time zone', default=lambda self: (self.env.user.tz or 'UTC'))
    signup_company_info = fields.Char(string="Company info")
    signup_path         = fields.Char(string="Sign-up Path", default="api/Auth/external-sign-up")

    # --- Step 1: Connect ---
    base_url = fields.Char(default='https://app-winnerei-dev-1taskapp-api.azurewebsites.net/')
    api_email = fields.Char()
    api_password = fields.Char()
    company_id = fields.Char()
    probe_path = fields.Char()
    export_path = fields.Char()

    # --- Step 2: policy ---
    ssot = fields.Selection([('ix','Integri-x is source of truth'),
                             ('odoo','Odoo is source of truth')], default='odoo')
    sync_direction = fields.Selection([('ix2odoo','Integri-x → Odoo'),
                                       ('odoo2ix','Odoo → Integri-x'),
                                       ('two_way','Two-way (advanced)')], default='ix2odoo')

    # --- Step 3: mapping ---
    line_ids = fields.One2many('integrix.setup.wizard.line', 'wizard_id', string='Field Mapping')

    # Probe result
    ping_status = fields.Char(readonly=True)
    ping_tenant = fields.Char(readonly=True)
    ping_api_version = fields.Char(readonly=True)

    # Step 4
    do_initial_sync = fields.Boolean(string='Run initial sync?')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        vals.setdefault('step', '0')
        user = self.env.user.sudo()
        full_name = (user.name or '').strip()
        parts = full_name.split(None, 1)
        first = parts[0] if parts else ''
        last  = parts[1] if len(parts) > 1 else ''
        vals.setdefault('signup_first_name', first)
        vals.setdefault('signup_last_name',  last)
        vals.setdefault('signup_email', (user.email or user.login or '').strip())
        phone = (user.partner_id.mobile or user.partner_id.phone or '').strip()
        if phone:
            vals.setdefault('signup_phone', phone)
        vals.setdefault('signup_company_name', (user.company_id.name or '').strip())
        vals.setdefault('signup_time_zone', user.tz or 'UTC')
        config = self.env['integrix.config'].sudo().search([], limit=1)
        if config:
            vals.update({
                'base_url': config.base_url or vals.get('base_url'),
                'api_email': config.api_email,
                'company_id': config.company_id,
                'probe_path': config.probe_path,
                'export_path': config.export_path,
                'ssot': config.ssot or 'odoo',
                'sync_direction': config.sync_direction or 'ix2odoo',
                'ping_status': config.last_probe_status,
                'ping_tenant': config.tenant_ip,
                'ping_api_version': config.api_version,
            })
            vals['line_ids'] = [(0, 0, {
                'active': m.active,
                'sequence': m.sequence,
                'ix_field': m.ix_field,
                'odoo_field': m.odoo_field,
            }) for m in config.mapping_ids]
        else:
            defaults = [
                ('id','x_integrix_external_id'),
                ('name','name'),
                ('parent_id','parent_id'),
                ('code','serial_no'),
                ('category','category_id'),
                ('site/location_path','location_id'),
                ('criticality','x_criticality'),
                ('status','equipment_state'),
                ('manufacturer','x_manufacturer'),
                ('model','x_model'),
                ('commissioning_date','acquisition_date'),
                ('serial_number','serial_no'),
                ('uom','x_uom'),
                ('cost_center','x_cost_center'),
                ('notes','note'),
            ]
            vals['line_ids'] = [(0, 0, {'active': True, 'ix_field': ix, 'odoo_field': od}) for ix, od in defaults]
        return vals

    # ------- helpers -------
    def _fmt_url(self, base, path):
        base = (base or '').rstrip('/')
        path = (path or '').lstrip('/')
        return f"{base}/{path}" if (base or path) else ''

    def _extract_token_from_response(self, resp):
        try:
            body = resp.json() if getattr(resp, 'text', None) else {}
        except Exception:
            body = getattr(resp, 'text', '') or ''
        token = None
        if isinstance(body, dict):
            token = (body.get('bearer') or body.get('token') or body.get('accessToken') or
                     body.get('jwt') or body.get('jwtToken'))
            if not token:
                sub = body.get('data') or body.get('result') or body.get('value') or {}
                if isinstance(sub, dict):
                    token = (sub.get('bearer') or sub.get('token') or sub.get('accessToken') or
                             sub.get('jwt') or sub.get('jwtToken'))
        elif isinstance(body, str):
            s = body.strip()
            token = s if s else None
        return token

    # ------- Step 0 actions -------
    def action_step0_have_account(self):
        self.ensure_one()
        self.step = '1'
        return self._reopen()

    def action_step0_open_signup(self):
        self.ensure_one()
        self.step = '0a'
        return self._reopen()

    # ------- Step 0a action (submit sign-up) -------
    def action_signup_submit(self):
        self.ensure_one()
        req = [
            ('signup_first_name', _("First name")),
            ('signup_last_name', _("Last name")),
            ('signup_company_name', _("Company name")),
            ('signup_email', _("Email")),
            ('signup_time_zone', _('Time zone')),
                    ('signup_password', _('Password')),
        ]
        for f, label in req:
            if not (self[f] or "").strip():
                raise UserError(_("Field '%s' is required.") % label)

        base = self.base_url or 'https://app-winnerei-dev-1taskapp-api.azurewebsites.net/'
        url = self._fmt_url(base, self.signup_path or "api/Auth/external-sign-up")
        payload = {
            "firstName": self.signup_first_name,
            "lastName": self.signup_last_name,
            "companyName": self.signup_company_name,
            "companyType": int(self.signup_company_type or 1),
            "phone": self.signup_phone or "",
            "email": self.signup_email,
            "timeZoneId": (self.signup_time_zone or self.signup_time_zone),
            "companyInfo": self.signup_company_info or "",
            "password": self.signup_password,
        }
        try:
            r = requests.post(url, json=payload, timeout=60)
        except Exception as e:
            raise UserError(_("Sign-up error: %s") % e)
        if r.status_code >= 300:
            raise UserError(_("Sign-up failed (HTTP %s): %s") % (r.status_code, r.text or ""))

        # на Step 1 підставимо email і перейдемо далі
        self.api_email = self.signup_email
        self.step = '1'
        return self._reopen()

    # ------- Step 1 (Connect) -------
    def action_test_connection_wizard(self):
        self.ensure_one()
        if not (self.base_url and self.api_email and self.api_password):
            raise UserError(_("Please fill Base URL, API Email and API Password."))

        signin_url = self._fmt_url(self.base_url, "api/Auth/sign-in")
        try:
            r = requests.post(signin_url, json={"email": self.api_email, "password": self.api_password}, timeout=60)
            if r.status_code >= 400:
                self.ping_status = f"AUTH FAIL {r.status_code}"
                raise UserError(_("Auth failed: %s") % r.text)
            token = self._extract_token_from_response(r)
            if not token:
                self.ping_status = 'AUTH FAIL (no token)'
                raise UserError(_('Auth response has no token'))
        except Exception as e:
            self.ping_status = f"AUTH ERROR: {e}"
            raise UserError(_("Auth error: %s") % e)

        probe_path = (self.probe_path or "").strip() or "api/companies/{companyId}/CompanyAssets"
        if "{companyId}" in probe_path:
            if not self.company_id:
                self.ping_status = "FAIL (companyId required)"
                raise UserError(_("Company ID is required for the selected probe path."))
            probe_path = probe_path.replace("{companyId}", self.company_id)

        probe_url = self._fmt_url(self.base_url, probe_path)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            pr = requests.get(probe_url, headers=headers, timeout=60)
            self.ping_status = "OK" if pr.status_code == 200 else f"HTTP {pr.status_code}"
            try:
                meta = pr.json() if pr.text else {}
            except Exception:
                meta = {}
            if isinstance(meta, list):
                meta = meta[0] if meta and isinstance(meta[0], dict) else {}
            elif not isinstance(meta, dict):
                meta = {}
            self.ping_tenant = meta.get("ip") or meta.get("tenant") or meta.get("companyName") or meta.get("tenantName") or self.ping_tenant
        except Exception as e:
            self.ping_status = f"FAIL: {e}"
            raise UserError(_("Probe error: %s") % e)

        try:
            sv = requests.get(self._fmt_url(self.base_url, "swagger/v1/swagger.json"), timeout=30)
            if sv.ok:
                js = sv.json()
                ver = js.get("info", {}).get("version")
                if ver:
                    self.ping_api_version = ver
        except Exception:
            pass

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Integri-x"),
                'message': _("Probe finished: %s") % (self.ping_status or "—"),
                'type': 'success' if (self.ping_status or "").startswith("OK") else 'warning',
                'sticky': False,
            }
        }

    # ------- навігація -------
    def _view_id_for_step(self, step):
        xmlid = {
            '0':  'integrix_connector.view_integrix_setup_wizard_form_step0',
            '0a': 'integrix_connector.view_integrix_setup_wizard_form_step0a',
            '1':  'integrix_connector.view_integrix_setup_wizard_form_step1',
            '2':  'integrix_connector.view_integrix_setup_wizard_form_step2',
            '3':  'integrix_connector.view_integrix_setup_wizard_form_step3',
            '4':  'integrix_connector.view_integrix_setup_wizard_form_step4',
        }[step]
        return self.env.ref(xmlid).id

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'integrix.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self._view_id_for_step(self.step or '0'),
            'target': 'new',
            'name': _('Integri-x Setup Wizard'),
        }

    def action_next(self):
        self.ensure_one()
        order = ['0','0a','1','2','3','4']
        i = order.index(self.step or '0')
        self.step = order[min(i+1, len(order)-1)]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        order = ['0','0a','1','2','3','4']
        i = order.index(self.step or '0')
        self.step = order[max(i-1, 0)]
        return self._reopen()

    def action_finish(self):
        self.ensure_one()
        Config = self.env['integrix.config'].sudo()
        config = Config.search([], limit=1) or Config.create({})
        config.write({
            'base_url': self.base_url or '',
            'api_email': self.api_email or '',
            'api_password': self.api_password or '',
            'company_id': self.company_id or '',
            'probe_path': self.probe_path or '',
            'export_path': self.export_path or '',
            'ssot': self.ssot,
            'sync_direction': self.sync_direction,
            'last_probe_status': self.ping_status,
            'tenant_ip': self.ping_tenant,
            'api_version': self.ping_api_version,
        })
        config.mapping_ids.unlink()
        if self.line_ids:
            self.env['integrix.field.map'].sudo().create([{
                'config_id': config.id,
                'active': l.active,
                'sequence': l.sequence,
                'ix_field': l.ix_field,
                'odoo_field': l.odoo_field,
            } for l in self.line_ids])
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'integrix.config',
            'view_mode': 'form',
            'res_id': config.id,
            'target': 'current',
            'name': _('Integri-x Settings'),
        }
