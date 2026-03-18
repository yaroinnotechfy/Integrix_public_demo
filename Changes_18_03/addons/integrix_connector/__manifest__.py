{
  "name": "Integri-x Connector",
  "version": "17.0.1.0.0",
  "summary": "Base connector",
  "author": "Integri-X",
  "license": "LGPL-3",
  "website": "https://example.com",
  "depends": ["base", "maintenance"],
  "post_init_hook": "post_init_hook",
  "data": [
    "security/ir.model.access.csv",
    "data/integrix_dashboard_data.xml",
    "views/integrix_config_views.xml",
    "views/integrix_dashboard_views.xml",
    "views/integrix_actions.xml",
    "views/integrix_menus.xml",
    "views/setup_wizard_views.xml",
    "views/integrix_hide_menus.xml",
    "views/integrix_config_view_inherit_no_create.xml",
        "views/maintenance_equipment_views.xml",
    "views/maintenance_equipment_list_search.xml",
    "views/maintenance_equipment_actions.xml",
    "views/maintenance_equipment_import.xml",
  ],
  "assets": {
    "web.assets_backend": [
      "integrix_connector/static/src/scss/wizard.scss",
      "integrix_connector/static/src/scss/integrix_dashboard.scss"
    ]
  },
  "installable": True,
  "application": True
}
