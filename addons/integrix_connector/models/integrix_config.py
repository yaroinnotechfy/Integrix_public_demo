from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests

class IntegrixConfig(models.Model):
    _name = 'integrix.config'
    _description = 'Integri-x Settings'

    # Connection
    base_url = fields.Char(string='Base URL')
    api_email = fields.Char(string='API Email')
    api_password = fields.Char(string='API Password')
    company_id = fields.Char(string='Company ID')
    probe_path = fields.Char(string='Probe Path')

    export_path = fields.Char(string='Export Path', default="api/AssetsImport/{companyId}/import-asset")

    # Sync policy
    ssot = fields.Selection([
        ('ix', 'Integri-x is source of truth'),
        ('odoo', 'Odoo is source of truth'),
    ], string='Single Source of Truth')

    sync_direction = fields.Selection([
        ('ix2odoo', 'Integri-x → Odoo'),
        ('odoo2ix', 'Odoo → Integri-x'),
        ('two_way', 'Two-way (advanced)'),
    ], string='Sync Direction')

    # Probe result (readonly display)
    last_probe_status = fields.Char(string='Last Probe Status', readonly=True)
    tenant_ip        = fields.Char(string='Tenant / IP', readonly=True)
    api_version      = fields.Char(string='API Version', readonly=True)

    def _fmt_url(self, base, path):
        base = (base or '').rstrip('/')
        path = (path or '').lstrip('/')
        return f"{base}/{path}" if base or path else ''

    def action_test_connection(self):
        """Ping API using provided creds and probe_path. Saves status / ip / version."""
        self.ensure_one()
        if not (self.base_url and self.api_email and self.api_password):
            raise UserError(_("Please fill Base URL, API Email and API Password."))

        # 1) Sign-in -> token
        signin_url = self._fmt_url(self.base_url, "api/Auth/sign-in")
        try:
            r = requests.post(
                signin_url,
                json={"email": self.api_email, "password": self.api_password},
                timeout=60,
            )
            if r.status_code >= 400:
                self.last_probe_status = f"AUTH FAIL {r.status_code}"
                raise UserError(_("Auth failed: %s") % (r.text or r.status_code))

            # robust token extraction: dict / nested / raw string
            try:
                body = r.json() if r.text else {}
            except Exception:
                body = r.text or ""

            token = None
            if isinstance(body, dict):
                token = (
                    body.get("bearer") or body.get("token") or body.get("accessToken")
                    or body.get("jwt") or body.get("jwtToken")
                )
                if not token:
                    nested = body.get("data") or body.get("result") or body.get("value") or {}
                    if isinstance(nested, dict):
                        token = (
                            nested.get("bearer") or nested.get("token") or nested.get("accessToken")
                            or nested.get("jwt") or nested.get("jwtToken")
                        )
            elif isinstance(body, str):
                s = body.strip()
                token = s if s and len(s) >= 20 else None

            if not token:
                self.last_probe_status = "AUTH FAIL (no token)"
                raise UserError(_("Auth response has no token"))
        except Exception as e:
            self.last_probe_status = f"AUTH ERROR: {e}"
            raise UserError(_("Auth error: %s") % e)

        # 2) Probe endpoint
        probe_path = (self.probe_path or "").strip() or "api/companies/{companyId}/CompanyAssets"
        if "{companyId}" in probe_path:
            if not self.company_id:
                self.last_probe_status = "FAIL (companyId required)"
                raise UserError(_("Company ID is required for the selected probe path."))
            probe_path = probe_path.replace("{companyId}", self.company_id)

        probe_url = self._fmt_url(self.base_url, probe_path)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            pr = requests.get(probe_url, headers=headers, timeout=60)
            self.last_probe_status = "OK" if pr.status_code == 200 else f"HTTP {pr.status_code}"
            # meta може бути dict або list
            try:
                meta = pr.json() if pr.text else {}
            except Exception:
                meta = {}
            val = None
            if isinstance(meta, dict):
                val = meta.get("ip") or meta.get("tenant") or meta.get("companyName") or meta.get("tenantName")
            elif isinstance(meta, list) and meta:
                first = meta[0]
                if isinstance(first, dict):
                    val = first.get("ip") or first.get("tenant") or first.get("companyName") or first.get("tenantName")
            self.tenant_ip = val or self.tenant_ip
        except Exception as e:
            self.last_probe_status = f"FAIL: {e}"
            raise UserError(_("Probe error: %s") % e)

        # 3) Swagger version (best-effort)
        try:
            sv = requests.get(self._fmt_url(self.base_url, "swagger/v1/swagger.json"), timeout=30)
            if sv.ok:
                js = sv.json()
                ver = js.get("info", {}).get("version")
                if ver:
                    self.api_version = ver
        except Exception:
            pass

        # Persist to ICP so Dashboard sees it
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('integrix_connector.base_url', self.base_url or '')
        ICP.set_param('integrix_connector.ping_status', (self.last_probe_status or '').upper())
        ICP.set_param('integrix_connector.ping_tenant', self.tenant_ip or '')
        ICP.set_param('integrix_connector.api_version', self.api_version or '')

        # Notify
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Integri-x"),
                'message': _("Probe finished: %s") % (self.last_probe_status or "—"),
                'type': 'success' if (self.last_probe_status or "").startswith("OK") else 'warning',
                'sticky': False,
            }
        }
