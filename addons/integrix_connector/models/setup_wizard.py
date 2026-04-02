from odoo import api, fields, models, _
from odoo.exceptions import UserError
import requests
import re
import json
from .integrix_default_mapping import DEFAULT_FIELD_MAPPING
import re

class IntegrixSetupWizardLine(models.TransientModel):
    _name = "integrix.setup.wizard.line"
    _description = "Integri-x Setup Wizard Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("integrix.setup.wizard", required=True, ondelete="cascade")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    ix_field = fields.Char(required=True)
    odoo_field = fields.Char(required=True)

class IntegrixSetupWizard(models.TransientModel):
    def _base_root(self, base):
        base = (base or '').strip()
        base = re.sub(r'/api/Auth/sign-in/?$', '', base, flags=re.I)
        return base.rstrip('/')

    def _tz_get(self):
        import pytz
        return [(tz, tz) for tz in pytz.all_timezones]

    _name = "integrix.setup.wizard"
    _description = "Integri-x Setup Wizard"

    step = fields.Selection([
        ("0", "Step 0"),
        ("0a", "Step 0a"),
        ("1", "Step 1"),
        ("2", "Step 2"),
        ("3", "Step 3"),
        ("4", "Step 4"),
    ], default="0")

    signup_first_name = fields.Char(string="First name")
    signup_last_name = fields.Char(string="Last name")
    signup_company_name = fields.Char(string="Company name")
    signup_company_type = fields.Integer(string="Company type", default=1)
    signup_phone = fields.Char(string="Phone")
    signup_email = fields.Char(string="Email")
    signup_password = fields.Char(string="Password")
    signup_time_zone = fields.Selection(selection="_tz_get", string="Time zone", default=lambda self: (self.env.user.tz or "UTC"))
    signup_company_info = fields.Char(string="Company info")
    signup_path = fields.Char(string="Sign-up Path", default="api/auth/external-sign-up")

    base_url = fields.Char(default="https://api.integri-x.com")
    api_email = fields.Char(string="Integrix Email")
    api_password = fields.Char(string="Integrix Password")
    company_id = fields.Char()
    probe_path   = fields.Char(default="api/Auth/Ip")
    export_path = fields.Char()

    ssot = fields.Selection([("ix", "Integri-x is source of truth"), ("odoo", "Odoo is source of truth")], default="odoo")
    sync_direction = fields.Selection([("ix2odoo", "Integri-x → Odoo"), ("odoo2ix", "Odoo → Integri-x"), ("two_way", "Two-way (advanced)")], default="ix2odoo")

    line_ids = fields.One2many("integrix.setup.wizard.line", "wizard_id", string="Field Mapping")

    ping_status = fields.Char(readonly=True)
    ping_tenant = fields.Char(readonly=True)
    ping_api_version = fields.Char(readonly=True)

    do_initial_sync = fields.Boolean(string="Import all equipment from Odoo to IntegriX")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        vals.setdefault("step", "0")

        user = self.env.user.sudo()
        full_name = (user.name or "").strip()
        parts = full_name.split(None, 1)
        first = parts[0] if parts else ""
        last = parts[1] if len(parts) > 1 else ""
        vals.setdefault("signup_first_name", first)
        vals.setdefault("signup_last_name", last)
        vals.setdefault("signup_email", (user.email or user.login or "").strip())
        phone = (user.partner_id.mobile or user.partner_id.phone or "").strip()
        if phone:
            vals.setdefault("signup_phone", phone)
        vals.setdefault("signup_company_name", (user.company_id.name or "").strip())
        vals.setdefault("signup_time_zone", user.tz or "UTC")

        ICP = self.env["ir.config_parameter"].sudo()
        db_uuid = ICP.get_param("database.uuid") or ""
        vals.setdefault("signup_company_info", json.dumps({"db_uuid": db_uuid, "company_id": int(self.env.company.id)}))

        config = self.env["integrix.config"].sudo().search([], limit=1)
        if config:
            vals.update({
                "base_url": config.base_url or vals.get("base_url"),
                "api_email": config.api_email,
                "company_id": config.company_id,
                "probe_path": config.probe_path,
                "export_path": config.export_path,
                "ssot": config.ssot or "odoo",
                "sync_direction": config.sync_direction or "ix2odoo",
                "ping_status": config.last_probe_status,
                "ping_tenant": config.tenant_ip,
                "ping_api_version": config.api_version,
            })
            if config.mapping_ids:
                vals["line_ids"] = [(0, 0, {
                    "active": m.active,
                    "sequence": m.sequence,
                    "ix_field": m.ix_field,
                    "odoo_field": m.odoo_field,
                }) for m in config.mapping_ids]
            else:
                vals["line_ids"] = [(0, 0, {"active": True, "ix_field": ix, "odoo_field": od}) for ix, od in DEFAULT_FIELD_MAPPING]
        else:
            vals["line_ids"] = [(0, 0, {"active": True, "ix_field": ix, "odoo_field": od}) for ix, od in DEFAULT_FIELD_MAPPING]
        return vals

    def _fmt_url(self, base, path):
        base = self._base_root(base)
        path = (path or "").lstrip("/")
        return f"{base}/{path}" if (base or path) else ""

    def _extract_token_from_response(self, resp):
        try:
            body = resp.json() if getattr(resp, "text", None) else {}
        except Exception:
            body = getattr(resp, "text", "") or ""
        token = None
        if isinstance(body, dict):
            token = (body.get("bearer") or body.get("token") or body.get("accessToken") or body.get("jwt") or body.get("jwtToken"))
            if not token:
                sub = body.get("data") or body.get("result") or body.get("value") or {}
                if isinstance(sub, dict):
                    token = (sub.get("bearer") or sub.get("token") or sub.get("accessToken") or sub.get("jwt") or sub.get("jwtToken"))
        elif isinstance(body, str):
            s = body.strip()
            token = s if s else None
        return token

    def action_step0_have_account(self):
        self.ensure_one()
        self.step = "1"
        return self._reopen()

    def action_step0_open_signup(self):
        self.ensure_one()
        self.step = "0a"
        return self._reopen()

    def action_signup_submit(self):
        self.ensure_one()
        req = [
            ("signup_first_name", _("First name")),
            ("signup_last_name", _("Last name")),
            ("signup_company_name", _("Company name")),
            ("signup_email", _("Email")),
            ("signup_time_zone", _("Time zone")),
            ("signup_password", _("Password")),
        ]
        for f, label in req:
            if not (self[f] or "").strip():
                raise UserError(_("Field %s is required.") % label)

        base = (self.base_url or "https://api.integri-x.com").rstrip("/")
        url = self._fmt_url(base, self.signup_path or "api/auth/external-sign-up")

        try:
            d = json.loads(self.signup_company_info) if self.signup_company_info else None
        except Exception:
            d = None
        if not isinstance(d, dict):
            ICP = self.env["ir.config_parameter"].sudo()
            db_uuid = ICP.get_param("database.uuid") or ""
            d = {"db_uuid": db_uuid, "company_id": int(self.env.company.id)}
        company_info_str = json.dumps(d)

        payload = {
            "firstName": self.signup_first_name,
            "lastName": self.signup_last_name,
            "companyName": self.signup_company_name,
            "companyType": int(self.signup_company_type or 1),
            "phone": self.signup_phone or "",
            "email": self.signup_email,
            "timeZoneId": (self.signup_time_zone or "UTC"),
            "companyInfo": company_info_str,
            "model": "Odoo",
            "password": self.signup_password,
        }
        r = requests.post(url, json=payload, timeout=60)
        if r.status_code >= 300:
            raise UserError(_("Sign-up failed (HTTP %s): %s") % (r.status_code, r.text or ""))

        self.api_email = self.signup_email
        self.api_password = self.signup_password
        self.action_test_connection_wizard()
        self.step = "4"
        return self._reopen()

    def action_test_connection_wizard(self):
        self.ensure_one()
        if not (self.api_email and self.api_password):
            raise UserError(_("Please fill Integrix Email and Integrix Password."))

        base = (self.base_url or "https://api.integri-x.com").rstrip("/")
        signin_url = self._fmt_url(base, "api/Auth/sign-in")

        r = requests.post(signin_url, json={"email": self.api_email, "password": self.api_password, "timeZoneId": (self.env.user.tz or "UTC")}, timeout=60)
        if r.status_code >= 400:
            self.ping_status = f"AUTH FAIL {r.status_code}"
            raise UserError(_("Authentication failed: %s") % (r.text or r.status_code))

        token = self._extract_token_from_response(r)
        if not token:
            self.ping_status = "AUTH FAIL (no token)"
            raise UserError(_("Authentication response has no token"))

        probe_path = (self.probe_path or "").strip()
        if not probe_path:
            probe_path = "api/Auth/Ip" if not (self.company_id or "").strip() else "api/companies/{companyId}/CompanyAssets"
        if "{companyId}" in probe_path and (self.company_id or "").strip():
            probe_path = probe_path.replace("{companyId}", self.company_id)

        probe_url = self._fmt_url(base, probe_path)
        pr = requests.get(probe_url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        self.ping_status = "OK" if pr.status_code == 200 else f"HTTP {pr.status_code}"

        try:
            meta = pr.json() if pr.text else {}
        except Exception:
            meta = {}
        if isinstance(meta, list):
            meta = meta[0] if meta and isinstance(meta[0], dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        cid = None
        if isinstance(meta, dict):
            cid = meta.get("companyId") or meta.get("company_id") or meta.get("id") or meta.get("companyGuid")
            if not cid and isinstance(meta.get("company"), dict):
                cid = meta["company"].get("id") or meta["company"].get("companyId")
        elif isinstance(meta, list) and meta and isinstance(meta[0], dict):
            first = meta[0]
            cid = first.get("companyId") or first.get("company_id") or first.get("id") or first.get("companyGuid")
            if not cid and isinstance(first.get("company"), dict):
                cid = first["company"].get("id") or first["company"].get("companyId")
        if cid and not (self.company_id or "").strip():
            self.company_id = str(cid)

        self.ping_tenant = meta.get("ip") or meta.get("tenant") or meta.get("companyName") or meta.get("tenantName") or self.ping_tenant

        try:
            sv = requests.get(self._fmt_url(base, "swagger/v1/swagger.json"), timeout=30)
            if sv.ok:
                js = sv.json()
                ver = js.get("info", {}).get("version")
                if ver:
                    self.ping_api_version = ver
        except Exception:
            pass

        return True

    def _view_id_for_step(self, step):
        xmlid = {
            "0": "integrix_connector.view_integrix_setup_wizard_form_step0",
            "0a": "integrix_connector.view_integrix_setup_wizard_form_step0a",
            "1": "integrix_connector.view_integrix_setup_wizard_form_step1",
            "2": "integrix_connector.view_integrix_setup_wizard_form_step2",
            "3": "integrix_connector.view_integrix_setup_wizard_form_step3",
            "4": "integrix_connector.view_integrix_setup_wizard_form_step4",
        }[step]
        return self.env.ref(xmlid).id

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "integrix.setup.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self._view_id_for_step(self.step or "0"),
            "target": "new",
            "name": _("Integri-x Setup Wizard"),
        }

    def action_next(self):
        self.ensure_one()
        st = self.step or "0"
        if st == "1":
            self.action_test_connection_wizard()
            self.step = "4"
            return self._reopen()
        order = ["0", "0a", "1", "4"]
        i = order.index(st) if st in order else 0
        self.step = order[min(i + 1, len(order) - 1)]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        st = self.step or "0"
        if st == "4":
            self.step = "1"
            return self._reopen()
        order = ["0", "0a", "1", "4"]
        i = order.index(st) if st in order else 0
        self.step = order[max(i - 1, 0)]
        return self._reopen()

    def action_finish(self):
        self.ensure_one()
        Config = self.env["integrix.config"].sudo()
        config = Config.search([], limit=1) or Config.create({})
        config.write({
            "base_url": self.base_url or "",
            "api_email": self.api_email or "",
            "api_password": self.api_password or "",
            "company_id": self.company_id or "",
            "probe_path": self.probe_path or "",
            "export_path": self.export_path or "",
            "ssot": self.ssot,
            "sync_direction": self.sync_direction,
            "last_probe_status": self.ping_status,
            "tenant_ip": self.ping_tenant,
            "api_version": self.ping_api_version,
        })
        config.mapping_ids.unlink()
        if self.line_ids:
            self.env["integrix.field.map"].sudo().create([{
                "config_id": config.id,
                "active": l.active,
                "sequence": l.sequence,
                "ix_field": l.ix_field,
                "odoo_field": l.odoo_field,
            } for l in self.line_ids])

        if self.do_initial_sync:
            Equip = self.env["maintenance.equipment"].sudo().search([])
            for rec in Equip:
                if not (rec.x_integrix_external_id or "").strip():
                    rec.x_integrix_external_id = (rec.serial_no or "").strip() or str(rec.id)
            self.env["integrix.push"].push_equipment(Equip)

        action = self.env.ref("integrix_connector.action_integrix_dashboard", raise_if_not_found=False)
        if action:
            return action.read()[0]
        dash = self.env["integrix.dashboard"].sudo().search([], limit=1)
        return {
            "type": "ir.actions.act_window",
            "name": "Integri-x Sync Dashboard",
            "res_model": "integrix.dashboard",
            "view_mode": "form",
            "target": "current",
            "res_id": dash.id if dash else False,
        }

