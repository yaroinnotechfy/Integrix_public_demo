# -*- coding: utf-8 -*-
# Integri-x default field mapping for the setup wizard
DEFAULT_FIELD_MAPPING = [
    # Integrix field         Odoo field
    ("id",                   "x_integrix_external_id"),
    ("name",                 "name"),
    ("parent_id",            "parent_id"),
    ("code",                 "serial_no"),                 # aka tag/code → беремо serial_no
    ("category",             "category_id"),
    ("site/location_path",   "location_id"),              # беремо location_id (не complete_name)
    ("criticality",          "x_criticality"),
    ("status",               "equipment_state"),          # або active; equipment_state
    ("manufacturer",         "x_manufacturer"),
    ("model",                "x_model"),
    ("commissioning_date",   "acquisition_date"),
    ("serial_number",        "serial_no"),
    ("uom",                  "x_uom"),
    ("cost_center",          "x_cost_center"),
    ("notes",                "note"),
]
