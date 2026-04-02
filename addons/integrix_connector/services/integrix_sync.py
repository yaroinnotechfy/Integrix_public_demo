from odoo import api, models, _
from odoo.exceptions import UserError
import requests

class IntegrixSync(models.AbstractModel):
    def _base_root(self, base):
        base = (base or '').strip()
        base = re.sub(r'/api/auth/sign-in/?$', '', base, flags=re.I)
        return base.rstrip('/')

    _name = "integrix.sync"
    _description = "Integri-x Sync (IX → Odoo)"

    # --- helpers ---
    def _cfg(self):
        cfg = self.env["integrix.config"].sudo().search([], limit=1)
        if not cfg or not (cfg.base_url and cfg.api_email and cfg.api_password):
            raise UserError(_("Configure Integri-x Settings first (base_url, email, password)."))
        return cfg

    def _login(self, base_url, email, password, timeout=30):
        base = self._base_root(base_url)
        url = f"{base}/api/auth/sign-in"
        r = requests.post(url, json={"email": email, "password": password, "timeZoneId": (self.env.user.tz or "UTC")}, timeout=timeout)
        r.raise_for_status()
        token = None
        try:
            body = r.json()
            token = (body.get("bearer") or body.get("token") or body.get("accessToken")
                     or (body.get("data") or {}).get("token"))
        except Exception:
            token = r.text.strip()
        if not token:
            raise UserError(_("Auth response has no token"))
        return token

    def _fetch_assets(self, base_url, bearer, company_id, probe_path=None, timeout=60, page=None, page_size=None):
        path = (probe_path or "api/companies/{companyId}/CompanyAssets").strip()
        if "{companyId}" in path:
            path = path.replace("{companyId}", company_id or "")
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        qs = []
        if page is not None: qs.append(f"page={int(page)}")
        if page_size is not None: qs.append(f"pageSize={int(page_size)}")
        if qs:
            url += ("&" if "?" in url else "?") + "&".join(qs)
        r = requests.get(url, headers={"Authorization": f"Bearer {bearer}"}, timeout=timeout)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception:
            data = []
    
        if isinstance(data, dict):
            data = data.get("items") or data.get("data") or data.get("result") or []
            if isinstance(data, dict):  # edge
                data = [data]
        return data if isinstance(data, list) else []

    # --- mapping ---
    def _mapping_pairs(self, cfg):
        # integrix.field.map з Settings
        pairs = []
        for m in cfg.mapping_ids.sudo().filtered(lambda x: x.active):
            ix = (m.ix_field or "").strip()
            od = (m.odoo_field or "").strip()
            if ix and od:
                pairs.append((ix, od))
    
        if ("id", "x_integrix_external_id") not in pairs:
            pairs.insert(0, ("id", "x_integrix_external_id"))
        return pairs

    def _apply_mapping(self, payload: dict, pairs):
        vals = {}
        for ix, od in pairs:
            # підтримуємо прості ключі 'a/b/c' як глибокі
            value = payload
            for part in ix.split("/"):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
            vals[od] = value
        return vals

    # --- upsert ---
    def _upsert_equipment(self, vals):
        Equip = self.env["maintenance.equipment"].sudo()
        ext = (vals.get("x_integrix_external_id") or "").strip()
        if not ext:
            return None, "skip (no external id)"
        rec = Equip.search([("x_integrix_external_id", "=", ext)], limit=1)
        allowed = set(self.env["maintenance.equipment"]._fields)
        write_vals = {k: v for k, v in vals.items() if k != "x_integrix_external_id" and k in allowed}
        if rec:
            rec.write(write_vals)
            return rec, "updated"
        else:
            allowed = set(self.env["maintenance.equipment"]._fields)
            vals2 = {k: v for k, v in vals.items() if k in allowed}
            # мінімум: name обов'язкове
            vals2.setdefault("name", f"IX {ext}")
            rec = Equip.create(vals2)
            return rec, "created"

    # --- public API ---
    def run_import_once(self, page=None, page_size=None):
        cfg = self._cfg()
        token = self._login(cfg.base_url, cfg.api_email, cfg.api_password)
        data = self._fetch_assets(cfg.base_url, token, cfg.company_id, cfg.probe_path, page=page, page_size=page_size)
        pairs = self._mapping_pairs(cfg)

        done = {"created": 0, "updated": 0, "skipped": 0}
        for row in data:
            vals = self._apply_mapping(row or {}, pairs)
            rec, status = self._upsert_equipment(vals)
            if status == "created": done["created"] += 1
            elif status == "updated": done["updated"] += 1
            else: done["skipped"] += 1

 
        self.env["ir.config_parameter"].sudo().set_param("integrix_connector.last_sync_dt", fields.Datetime.now())
        return done
