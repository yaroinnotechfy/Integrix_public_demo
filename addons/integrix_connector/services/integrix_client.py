# -*- coding: utf-8 -*-
from odoo import models
from urllib import parse
import requests
import re

TIMEOUT = 25

class IntegrixClient(models.AbstractModel):

    def _company_id_from_api(self, base_url, bearer):
        base = self._base_root(base_url)
        url = f"{base.rstrip('/')}/api/Companies/user"
        ok, info = self._get(url, bearer=bearer, timeout=15)
        if not ok or int(info.get("status", 0)) >= 400:
            return None
        body = info.get("body")
        if isinstance(body, dict):
            for k in ("companyId","company_id","companyGuid","companyGuidId","id","guid"):
                v = body.get(k)
                if isinstance(v, (str,int)) and str(v).strip():
                    return str(v).strip()
            c = body.get("company") or {}
            if isinstance(c, dict):
                for k in ("id","companyId","guid"):
                    v = c.get(k)
                    if isinstance(v, (str,int)) and str(v).strip():
                        return str(v).strip()
        return None
    _name = "integrix.client"
    _description = "Integri-x HTTP client"

    def _base_root(self, base_url):
        base = (base_url or "").strip()
        base = re.sub(r'/api/Auth/sign-in/?$', '', base, flags=re.I)
        base = re.sub(r'/api/Auth/sign-in/?$', '', base)
        return base.rstrip("/")

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

    def _login(self, base_url, email, password):
        base = self._base_root(base_url)
        url = f"{base}/api/Auth/sign-in"
        ok, info = self._post(url, json={"email": email, "password": password, "timeZoneId": (self.env.user.tz or "UTC")}, timeout=20)
        if not ok:
            return False, f"Auth error: {info.get('error')}"
        if int(info.get("status", 0)) >= 400:
            return False, f"Auth HTTP {info.get('status')}: {info.get('body')}"
        body = info.get("body")
        token = None
        if isinstance(body, dict):
            token = body.get("bearer") or body.get("token") or body.get("accessToken") or body.get("jwt") or body.get("jwtToken")
            if not token:
                data = body.get("data") or body.get("result") or body.get("value") or {}
                if isinstance(data, dict):
                    token = data.get("bearer") or data.get("token") or data.get("accessToken") or data.get("jwt") or data.get("jwtToken")
        elif isinstance(body, str):
            s = body.strip()
            token = s if s else None
        if not token:
            return False, f"Auth response has no token: {body}"
        return True, token

    def _company_id_for_token(self, base_url, bearer):
        base = self._base_root(base_url)
        url = f"{base}/api/Companies/user"
        ok, info = self._get(url, bearer=bearer, timeout=20)
        if not ok:
            return False, f"Company lookup error: {info.get('error')}"
        if int(info.get("status", 0)) >= 400:
            return False, f"Company lookup HTTP {info.get('status')}: {info.get('body')}"
        body = info.get("body")
        if isinstance(body, dict):
            cid = (body.get("id") or "").strip()
            return (True, cid) if cid else (False, f"Company lookup: no id in {body}")
        return False, f"Company lookup: unexpected body {body}"

    def probe_company_assets(self, base_url, email, password, company_id, probe_path):
        ok, token = self._login(base_url, email, password)
        if not ok:
            return False, token
        if not (company_id or "").strip():
            cid = self._company_id_from_api(base_url, token)
            if cid:
                company_id = cid

        cid = (company_id or "").strip()
        if not cid:
            okc, cid_or_err = self._company_id_for_token(base_url, token)
            if not okc:
                return False, cid_or_err
            cid = cid_or_err

        base = self._base_root(base_url)
        path = probe_path if (probe_path or "").startswith("/") else f"/{(probe_path or '').lstrip('/')}"
        if "{companyId}" in path:
            url = f"{base}{path.replace('{companyId}', cid)}"
        else:
            sep = "&" if "?" in path else "?"
            url = f"{base}{path}{sep}companyId={parse.quote(cid)}"

        ok2, info = self._get(url, bearer=token, timeout=25)
        if not ok2:
            return False, f"Probe error: {info.get('error')}"
        if int(info.get("status", 0)) >= 400:
            return False, f"Probe FAILED: HTTP {info.get('status')} @ {url}"
        return True, {"status": info.get("status"), "body": info.get("body"), "bearer": token, "url": url, "companyId": cid}

    def fetch_company_assets(self, base_url, email, password, company_id, probe_path):
        ok, token = self._login(base_url, email, password)
        if not ok:
            return False, token
        if not (company_id or "").strip():
            cid = self._company_id_from_api(base_url, token)
            if cid:
                company_id = cid

        cid = (company_id or "").strip()
        if not cid:
            okc, cid_or_err = self._company_id_for_token(base_url, token)
            if not okc:
                return False, cid_or_err
            cid = cid_or_err

        base = self._base_root(base_url)
        path = probe_path if (probe_path or "").startswith("/") else f"/{(probe_path or '').lstrip('/')}"
        if "{companyId}" in path:
            url = f"{base}{path.replace('{companyId}', cid)}"
        else:
            sep = "&" if "?" in path else "?"
            url = f"{base}{path}{sep}companyId={parse.quote(cid)}"

        ok2, info = self._get(url, bearer=token, timeout=25)
        if not ok2:
            return False, info.get("error")
        if int(info.get("status", 0)) >= 400:
            return False, f"HTTP {info.get('status')} @ {url}"
        body = info.get("body")
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

        base = (base_url or "").rstrip("/")

        path = (export_path or "").strip().lstrip("/")
        if not path:
            path = "api/AssetsImport/import-asset"

        if "{companyId}" in path:
            if company_id:
                path = path.replace("{companyId}", (company_id or "").strip())
            else:
                path = path.replace("/{companyId}", "")
                path = path.replace("{companyId}/", "")
                path = path.replace("{companyId}", "")

        while "//" in path:
            path = path.replace("//", "/")
        url = f"{base}/{path.lstrip('/')}"

        payload = {"assets": list(assets or [])}
        ok2, info = self._post(url, json=payload, bearer=token, timeout=timeout)
        if not ok2:
            return False, info.get("error")
        status = int(info.get("status", 0))
        if status >= 400:
            return False, f"HTTP {status}: {info.get('body')}"
        return True, info.get("body")
