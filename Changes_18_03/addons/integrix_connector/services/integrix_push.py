from odoo import fields, models, _
from odoo.exceptions import UserError

class IntegrixPush(models.AbstractModel):
    _name = "integrix.push"
    _description = "Integri-x Push (Odoo → IX)"

    def _cfg(self):
        cfg = self.env["integrix.config"].sudo().search([], limit=1)
        if not cfg or not (cfg.base_url and cfg.api_email and cfg.api_password):
            raise UserError(_("Configure Integri-x Settings first (Base URL, Integrix Email/Password)."))
        return cfg

    def _ensure_external_id(self, rec):
        ext = (rec.x_integrix_external_id or "").strip()
        if not ext:
            raise UserError(_("Not linked to Integri-x — use 'Link to Integri-x' first."))
        return ext

    def _asset_payload(self, rec):
        self._ensure_external_id(rec)
        parent_ext = None
        if "parent_id" in rec._fields and rec.parent_id:
            parent_ext = (rec.parent_id.x_integrix_external_id or "").strip() or None
        return {"name": rec.name or f"Odoo {rec.id}", "externalId": rec.x_integrix_external_id, "parentId": parent_ext}

    def _extract_remote_external_id(self, item):
        if isinstance(item, dict):
            val = item.get("externalId") or item.get("external_id") or item.get("id")
            if not val and isinstance(item.get("asset"), dict):
                val = item["asset"].get("externalId")
            return (val or "").strip() or None
        return None

    def push_equipment(self, records):
        Equip = self.env["maintenance.equipment"].sudo()
        if isinstance(records, models.Model):
            recs = records
        elif isinstance(records, (list, tuple, set)):
            recs = Equip.browse(list(records))
        elif isinstance(records, int):
            recs = Equip.browse([records])
        else:
            recs = Equip.browse(self.env.context.get("active_ids", []) or [])
        recs = recs.exists()
        if not recs:
            return {"pushed": 0, "errors": 0, "skipped": 0, "details": []}

        cfg = self._cfg()

        ok, remote = self.env["integrix.client"].fetch_company_assets(
            cfg.base_url, cfg.api_email, cfg.api_password, cfg.company_id or "",
            cfg.probe_path or "api/companies/{companyId}/CompanyAssets"
        )
        remote = remote if ok else []
        remote_ext = {self._extract_remote_external_id(it) for it in remote}
        remote_ext.discard(None)

        assets_all, skipped_unlinked = [], 0
        for r in recs:
            try:
                assets_all.append(self._asset_payload(r))
            except UserError:
                skipped_unlinked += 1

        new_assets = [a for a in assets_all if (a.get("externalId") or "").strip() not in remote_ext]
        skipped_duplicates = len(assets_all) - len(new_assets)

        if new_assets:
            ok2, result = self.env["integrix.client"].import_assets(
                cfg.base_url, cfg.api_email, cfg.api_password, cfg.company_id or "",
                new_assets, cfg.export_path
            )
            if not ok2:
                raise UserError(_("Integri-x import failed: %s") % result)

            self.env["ir.config_parameter"].sudo().set_param("integrix_connector.last_sync_dt", fields.Datetime.now())
            return {"pushed": len(new_assets), "errors": 0, "skipped": skipped_unlinked + skipped_duplicates, "details": result}

        return {"pushed": 0, "errors": 0, "skipped": skipped_unlinked + skipped_duplicates, "details": []}
