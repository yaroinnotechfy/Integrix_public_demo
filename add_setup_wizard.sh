set -e


mkdir -p addons/integrix_connector/models
cat > addons/integrix_connector/models/setup_wizard.py <<'PY'
from odoo import api, fields, models
from odoo.exceptions import UserError

class IntegrixSetupWizard(models.TransientModel):
    _name = "integrix.setup.wizard"
    _description = "Integri-x Setup Wizard"

    state = fields.Selection([
        ("connect", "Connect"),
        ("ssot", "SSOT"),
        ("mapping", "Field Mapping"),
        ("initial_sync", "Initial Sync"),
    ], default="connect", string="Step")

    base_url = fields.Char(string="Base URL")
    email = fields.Char(string="API Email")
    password = fields.Char(string="API Password")
    company_id = fields.Char(string="Company ID")
    probe_path = fields.Char(string="Probe Path", default="/api/companies/{companyId}/CompanyAssets")

    last_message = fields.Text(readonly=True, string="Status")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        ICP = self.env["ir.config_parameter"].sudo()
        vals.setdefault("base_url", ICP.get_param("integrix.base_url", ""))
        vals.setdefault("email", ICP.get_param("integrix.basic_email", ""))
        vals.setdefault("password", ICP.get_param("integrix.basic_password", ""))
        vals.setdefault("company_id", ICP.get_param("integrix.company_id", ""))
        vals.setdefault("probe_path", ICP.get_param("integrix.probe_path", "/api/companies/{companyId}/CompanyAssets"))
        return vals

    def action_test_connection(self):
        self.ensure_one()
        if not (self.base_url and self.email and self.password and self.company_id):
            raise UserError("Please fill Base URL, Email, Password and Company ID.")
        client = self.env["integrix.client"].sudo()
        ok, info = client.probe_company_assets(self.base_url, self.email, self.password, self.company_id, self.probe_path)
        msg = info if isinstance(info, str) else str(info)
        self.write({"last_message": msg})
        return {"type":"ir.actions.client","tag":"display_notification",
                "params":{"title":"Integri-x","message":msg,
                          "type":"success" if ok else "danger","sticky":False}}

    def action_next(self):
        self.ensure_one()
        flow = ["connect","ssot","mapping","initial_sync"]
        idx = flow.index(self.state)
        if idx < len(flow)-1:
            self.state = flow[idx+1]
        return {"type":"ir.actions.act_window","res_model":self._name,"res_id":self.id,"view_mode":"form","target":"new"}

    def action_prev(self):
        self.ensure_one()
        flow = ["connect","ssot","mapping","initial_sync"]
        idx = flow.index(self.state)
        if idx > 0:
            self.state = flow[idx-1]
        return {"type":"ir.actions.act_window","res_model":self._name,"res_id":self.id,"view_mode":"form","target":"new"}

    def action_apply_and_save(self):
        self.ensure_one()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("integrix.base_url", (self.base_url or "").strip())
        ICP.set_param("integrix.basic_email", (self.email or "").strip())
        ICP.set_param("integrix.basic_password", self.password or "")
        ICP.set_param("integrix.company_id", (self.company_id or "").strip())
        ICP.set_param("integrix.probe_path", (self.probe_path or "/api/companies/{companyId}/CompanyAssets").strip())
        return {"type": "ir.actions.act_window_close"}
PY


grep -q "from \. import setup_wizard" addons/integrix_connector/models/__init__.py 2>/dev/null || \
printf "\nfrom . import setup_wizard\n" >> addons/integrix_connector/models/__init__.py


mkdir -p addons/integrix_connector/views
cat > addons/integrix_connector/views/setup_wizard_views.xml <<'XML'
<odoo>
  <data>
    <record id="view_integrix_setup_wizard_form" model="ir.ui.view">
      <field name="name">integrix.setup.wizard.form</field>
      <field name="model">integrix.setup.wizard</field>
      <field name="arch" type="xml">
        <form string="Integri-x Setup Wizard">
          <header>
            <button name="action_prev" string="Back" type="object" class="btn-secondary" attrs="{'invisible':[('state','=','connect')]}"/>
            <button name="action_next" string="Next" type="object" class="btn-primary" attrs="{'invisible':[('state','=','initial_sync')]}"/>
            <button name="action_apply_and_save" string="Apply &amp; Close" type="object" class="btn-primary" attrs="{'invisible':[('state','!=','initial_sync')]}"/>
            <field name="state" widget="statusbar" statusbar_visible="connect,ssot,mapping,initial_sync"/>
          </header>
          <sheet>
            <group attrs="{'invisible':[('state','!=','connect')]}">
              <h3>Step 1 — Connect</h3>
              <group>
                <field name="base_url" placeholder="https://app-...azurewebsites.net"/>
                <field name="email"/>
                <field name="password"/>
                <field name="company_id"/>
                <field name="probe_path" placeholder="/api/companies/{companyId}/CompanyAssets"/>
              </group>
              <button name="action_test_connection" type="object" string="Test Connection" class="btn btn-primary"/>
              <field name="last_message" readonly="1" nolabel="1" placeholder="Status will appear here..."/>
            </group>

            <group attrs="{'invisible':[('state','!=','ssot')]}">
              <h3>Step 2 — SSOT</h3>
              <p>Placeholder (to be implemented).</p>
            </group>

            <group attrs="{'invisible':[('state','!=','mapping')]}">
              <h3>Step 3 — Field Mapping</h3>
              <p>Placeholder (to be implemented).</p>
            </group>

            <group attrs="{'invisible':[('state','!=','initial_sync')]}">
              <h3>Step 4 — Initial Sync</h3>
              <p>Placeholder (to be implemented).</p>
            </group>
          </sheet>
        </form>
      </field>
    </record>

    <record id="action_integrix_setup_wizard" model="ir.actions.act_window">
      <field name="name">Integri-x Setup Wizard</field>
      <field name="res_model">integrix.setup.wizard</field>
      <field name="view_mode">form</field>
      <field name="target">new</field>
    </record>
  </data>
</odoo>
XML


awk '
/<\/data>/ && !p { print "    <menuitem id=\"menu_integrix_setup_wizard\" name=\"Setup Wizard\" parent=\"menu_integrix_root\" action=\"action_integrix_setup_wizard\" sequence=\"2\"/>"; p=1 }
{ print }
' addons/integrix_connector/views/integrix_menus.xml > /tmp/menus.xml && mv /tmp/menus.xml addons/integrix_connector/views/integrix_menus.xml


python3 - "$PWD/addons/integrix_connector/__manifest__.py" <<'PY'
import ast, sys, json
p=sys.argv[1]
m=ast.parse(open(p).read(), filename=p, mode="exec")
d=next(n.value for n in m.body if isinstance(n, ast.Assign) and getattr(n.targets[0],'id',None)=='__manifest__' or getattr(n.targets[0],'id',None)=='manifest' or isinstance(n.targets[0], ast.Name))
# грубо: просто додаємо views/setup_wizard_views.xml, якщо немає
s=open(p).read()
if "views/setup_wizard_views.xml" not in s:
    s=s.replace('"views/integrix_config_views.xml",', '"views/integrix_config_views.xml",\n        "views/setup_wizard_views.xml",')
open(p,"w").write(s)
print("manifest patched")
PY

echo "✅ Setup Wizard files generated."
