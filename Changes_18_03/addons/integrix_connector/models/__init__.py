from . import integrix_config          # базова модель integrix.config — першою
from . import field_map                # окрема модель integrix.field.map
from . import config_mapping_inherit   # _inherit = 'integrix.config' — після базової
from . import dashboard                # інші моделі/сервіси
from . import integrix_dashboard_actions
from . import res_config_settings
from . import setup_wizard             # візард — наприкінці, але до завантаження views
from . import equipment_inherit
from . import equipment_bulk
from . import equipment_flags
