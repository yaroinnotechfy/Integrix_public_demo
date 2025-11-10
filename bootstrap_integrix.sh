#!/usr/bin/env bash
set -e

# 1) env + docker-compose + odoo.conf + README
cat > .env.example <<'EOF'
ODOO_VERSION=17.0
POSTGRES_VERSION=15
POSTGRES_DB=postgres
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo
DB_HOST=db
DB_PORT=5432
ADMIN_PASSWORD=admin
ADDONS_PATH=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
LOG_LEVEL=info
WORKERS=0
LIMIT_TIME_CPU=120
LIMIT_TIME_REAL=240
PROXY_MODE=False
EOF

cat > docker-compose.yml <<'EOF'
version: "3.9"
services:
  db:
    image: postgres:${POSTGRES_VERSION}
    container_name: integrix_db
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 5

  odoo:
    image: odoo:${ODOO_VERSION}
    container_name: integrix_odoo
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8069:8069"
      - "8072:8072"
    environment:
      HOST: ${DB_HOST}
      USER: ${POSTGRES_USER}
      PASSWORD: ${POSTGRES_PASSWORD}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      LOG_LEVEL: ${LOG_LEVEL}
    volumes:
      - ./addons:/mnt/extra-addons
      - ./odoo.conf:/etc/odoo/odoo.conf:ro
    command: ["odoo", "-c", "/etc/odoo/odoo.conf"]

volumes:
  db_data:
EOF

cat > odoo.conf <<'EOF'
[options]
db_host = ${DB_HOST}
db_port = ${DB_PORT}
db_user = ${POSTGRES_USER}
db_password = ${POSTGRES_PASSWORD}
admin_passwd = ${ADMIN_PASSWORD}
log_level = ${LOG_LEVEL}
addons_path = ${ADDONS_PATH}
proxy_mode = ${PROXY_MODE}
limit_time_cpu = ${LIMIT_TIME_CPU}
limit_time_real = ${LIMIT_TIME_REAL}
workers = ${WORKERS}
EOF

# 2) базовий модуль
mkdir -p addons/integrix_connector/{models,security,services,views}
cat > addons/integrix_connector/__init__.py <<'EOF'
from . import models
from . import services
EOF

cat > addons/integrix_connector/__manifest__.py <<'EOF'
{
    "name": "Integri-x Connector (MVP)",
    "version": "17.0.1.0.0",
    "summary": "Base connector skeleton: settings, menu, placeholders for sync.",
    "author": "Your Company",
    "license": "LGPL-3",
    "website": "https://example.com",
    "depends": ["base", "maintenance"],
    "data": [
        "security/ir.model.access.csv",
        "views/integrix_menus.xml",
        "views/integrix_config_views.xml",
    ],
    "assets": {},
    "installable": True,
    "application": False,
}
EOF

cat > addons/integrix_connector/models/__init__.py <<'EOF'
from . import integrix_config
EOF

cat > addons/integrix_connector/models/integrix_config.py <<'EOF'
from odoo import api, fields, models
from odoo.exceptions import UserError

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    integrix_base_url = fields.Char(string="Integri-x Base URL")
    integrix_api_key = fields.Char(string="Integri-x API Key", password=True)
    integrix_env = fields.Selection(
        selection=[("dev", "Dev"), ("prod", "Prod")],
        string="Environment",
        default="dev",
    )
    integrix_ssot = fields.Selection(
        selection=[("odoo", "Odoo"), ("integrix", "Integri-x")],
        string="SSOT (Source of Truth)",
        default="integrix",
    )
    integrix_sync_direction = fields.Selection(
        selection=[("push", "Odoo → Integri-x"), ("pull", "Integri-x → Odoo")],
        string="Sync Direction",
        default="pull",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"].sudo()
        res.update(
            integrix_base_url=ICP.get_param("integrix.base_url", default=""),
            integrix_api_key=ICP.get_param("integrix.api_key", default=""),
            integrix_env=ICP.get_param("integrix.env", default="dev"),
            integrix_ssot=ICP.get_param("integrix.ssot", default="integrix"),
            integrix_sync_direction=ICP.get_param(
                "integrix.sync_direction", default="pull"
            ),
        )
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("integrix.base_url", self.integrix_base_url or "")
        ICP.set_param("integrix.api_key", self.integrix_api_key or "")
        ICP.set_param("integrix.env", self.integrix_env or "dev")
        ICP.set_param("integrix.ssot", self.integrix_ssot or "integrix")
        ICP.set_param("integrix.sync_direction", self.integrix_sync_direction or "pull")

    def action_test_connection(self):
        ICP = self.env["ir.config_parameter"].sudo()
        base_url = (ICP.get_param("integrix.base_url") or "").strip().rstrip("/")
        api_key = (ICP.get_param("integrix.api_key") or "").strip()
        if not base_url or not api_key:
            raise UserError("Please fill Base URL and API Key, then Save.")

        client = self.env["integrix.client"].sudo()
        ok, info = client.ping(base_url, api_key)
        if ok:
            msg = f"Ping OK. tenant={info.get('tenant','?')} version={info.get('version','?')}"
            msg_type = "success"
        else:
            msg = f"Ping FAILED: {info}"
            msg_type = "danger"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Integri-x", "message": msg, "sticky": False, "type": msg_type},
        }
EOF

cat > addons/integrix_connector/services/__init__.py <<'EOF'
from . import integrix_client
EOF

cat > addons/integrix_connector/services/integrix_client.py <<'EOF'
import json
import logging
from urllib import request, error

from odoo import models

_logger = logging.getLogger(__name__)

class IntegrixClient(models.AbstractModel):
    _name = "integrix.client"
    _description = "HTTP client for Integri-x API"

    def _http_get(self, url, api_key):
        req = request.Request(url)
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        try:
            with request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return True, json.loads(raw) if raw else {}
        except error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            _logger.warning("Integri-x HTTP %s: %s", e.code, raw)
            return False, f"HTTP {e.code}: {raw}"
        except Exception as ex:  # noqa
            _logger.exception("Integri-x request failed")
            return False, str(ex)

    def ping(self, base_url, api_key, path="/ping"):
        url = f"{base_url.rstrip('/')}{path}"
        return self._http_get(url, api_key)
EOF

cat > addons/integrix_connector/security/ir.model.access.csv <<'EOF'
"id","name","model_id:id","group_id:id","perm_read","perm_write","perm_create","perm_unlink"
EOF

cat > addons/integrix_connector/views/integrix_menus.xml <<'EOF'
<odoo>
  <data>
    <menuitem id="menu_integrix_root" name="Integri-x Sync"
              parent="maintenance.menu_maintenance_root" sequence="90"/>
    <record id="action_open_integrix_settings" model="ir.actions.act_window">
      <field name="name">Integri-x Settings</field>
      <field name="res_model">res.config.settings</field>
      <field name="view_mode">form</field>
      <field name="target">current</field>
      <field name="context">{"default_module":"integrix_connector"}</field>
    </record>
    <menuitem id="menu_integrix_settings" name="Settings" parent="menu_integrix_root"
              action="action_open_integrix_settings" sequence="1"/>
  </data>
</odoo>
EOF

cat > addons/integrix_connector/views/integrix_config_views.xml <<'EOF'
<odoo>
  <data>
    <record id="view_res_config_settings_integrix_form" model="ir.ui.view">
      <field name="name">res.config.settings.view.form.integrix</field>
      <field name="model">res.config.settings</field>
      <field name="inherit_id" ref="base.view_res_config_settings"/>
      <field name="arch" type="xml">
        <xpath expr="//div[@id='settings']" position="inside">
          <div class="app_settings_block" data-string="Integri-x" string="Integri-x" id="integrix_settings">
            <h2>Integri-x</h2>
            <group>
              <field name="integrix_base_url" placeholder="https://api.example.com"/>
              <field name="integrix_api_key" password="True"/>
              <field name="integrix_env"/>
              <field name="integrix_ssot"/>
              <field name="integrix_sync_direction"/>
            </group>
            <footer>
              <button name="action_test_connection" type="object" class="btn btn-primary" string="Test Connection"/>
            </footer>
          </div>
        </xpath>
      </field>
    </record>
  </data>
</odoo>
EOF

echo "✅ Files generated."
