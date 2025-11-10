# -*- coding: utf-8 -*-
from odoo import models
from urllib import parse
import requests

TIMEOUT = 25

class IntegrixClient(models.AbstractModel):
    _name = "integrix.client"
    _description = "Integri-x HTTP client"

    def _request(self, method, url, *, bearer=None, data=None, json=None, timeout=TIMEOUT):
        headers = {"User-Agent": "Odoo-Integrix/1.0"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            resp = requests.request(method, url, headers=headers, data=data, json=json, timeout=timeout)
            try:
                content = resp.json()
            except Exception:
                content = resp.text
            return True, {"status": resp.status_code, "body": content}
        except Exception as e:
            return False, {"status": 0, "error": str(e)}

    def _get(self, url, *, bearer=None, timeout=TIMEOUT):
        return self._request("GET", url, bearer=bearer, timeout=timeout)

    def _post(self, url, *, data=None, json=None, bearer=None, timeout=TIMEOUT):
        return self._request("POST", url, bearer=bearer, data=data, json=json, timeout=timeout)

    # ---- auth ----
    def _login(self, base_url, email, password):
        url = f"{base_url.rstrip('/')}/api/Auth/sign-in"
        ok, info = self._post(url, json={"email": email, "password": password}, timeout=20)
        if not ok:
            return False, f"Auth error: {info.get('error')}"
        if int(info.get("status", 0)) >= 400:
            return False, f"Auth HTTP {info.get('status')}: {info.get('body')}"

        body = info.get("body")
        token = None

       
        if isinstance(body, dict):
           
            token = body.get("token") or body.get("access_token") or body.get("Token") or body.get("jwt") or body.get("jwtToken")
            # вкладені структури: data / result / value
            if not token:
                data = body.get("data") or body.get("result") or body.get("value") or {}
                if isinstance(data, dict):
                    token = data.get("token") or data.get("access_token") or data.get("jwt") or data.get("jwtToken")
        elif isinstance(body, str):
           
            token = body.strip() if body.strip() and len(body.strip()) > 20 else None

        if not token:
            return False, f"Auth response has no token: {body}"
        return True, token

    def get_auth_ip(self, base_url, bearer):
        url = f"{base_url.rstrip('/')}/api/Auth/Ip"
        return self._get(url, bearer=bearer, timeout=15)

    def get_api_version(self, base_url):
        url = f"{base_url.rstrip('/')}/swagger/v1/swagger.json"
        ok, info = self._get(url, timeout=15)
        if not ok or int(info.get("status", 0)) >= 400:
            return False, {}
        body = info.get("body") or {}
        ver = title = None
        if isinstance(body, dict):
            inf = body.get("info") or {}
            ver = inf.get("version")
            title = inf.get("title")
        return True, {"version": ver, "title": title}

    # ---- business: probe ----
    def probe_company_assets(self, base_url, email, password, company_id, probe_path):
        ok, token = self._login(base_url, email, password)
        if not ok:
            return False, token

        base = base_url.rstrip("/")
        path = probe_path if probe_path.startswith("/") else f"/{probe_path}"
        if "{companyId}" in path:
            url = f"{base}{path.replace('{companyId}', company_id)}"
        else:
            sep = "&" if "?" in path else "?"
            from urllib import parse as _p
            url = f"{base}{path}{sep}companyId={_p.quote(company_id)}"

        ok2, info = self._get(url, bearer=token, timeout=25)
        if not ok2:
            return False, f"Probe error: {info.get('error')}"
        if int(info.get("status", 0)) >= 400:
            return False, f"Probe FAILED: HTTP {info.get('status')} @ {url}"

        return True, {"status": info.get("status"), "body": info.get("body"), "bearer": token, "url": url}

    # ---- fetch list for initial import (IX → Odoo) ----
    def fetch_company_assets(self, base_url, email, password, company_id, probe_path):
        """Returns (ok, data|error). data is list[dict] best-effort-normalized."""
        ok, token = self._login(base_url, email, password)
        if not ok:
            return False, token
        base = base_url.rstrip("/")
        path = probe_path if probe_path.startswith("/") else f"/{probe_path}"
        if "{companyId}" in path:
            url = f"{base}{path.replace('{companyId}', company_id)}"
        else:
            sep = "&" if "?" in path else "?"
            url = f"{base}{path}{sep}companyId={parse.quote(company_id)}"
        ok2, info = self._get(url, bearer=token, timeout=25)
        if not ok2:
            return False, info.get("error")
        if int(info.get("status", 0)) >= 400:
            return False, f"HTTP {info.get('status')} @ {url}"
        body = info.get("body")
        # normalize to list[dict]
        if isinstance(body, dict):
            items = body.get("items") or body.get("data") or body.get("result") or body.get("value")
            body = items if isinstance(items, list) else [body]
        if not isinstance(body, list):
            body = []
        data = [it for it in body if isinstance(it, dict)]
        return True, data


    def import_assets(self, base_url, email, password, company_id, assets, export_path=None, timeout=TIMEOUT):
        ok, token = self._login(base_url, email, password)
        if not ok:
            return False, token
        base = base_url.rstrip('/')
        path = (export_path or f"api/AssetsImport/{company_id}/import-asset").lstrip("/")
        if "{companyId}" in path:
            path = path.replace("{companyId}", company_id or "")
        url = f"{base}/{path}"
        payload = {"assets": list(assets or [])}
        ok2, info = self._post(url, json=payload, bearer=token, timeout=timeout)
        if not ok2:
            return False, info.get("error")
        status = int(info.get("status", 0))
        if status >= 400:
            return False, f"HTTP {status}: {info.get('body')}"
        return True, info.get("body")
