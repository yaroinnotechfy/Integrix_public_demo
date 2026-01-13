/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, "integrix_connector.inline_loader", {
    async onButtonClicked(ev) {
        const attrs = ev?.detail?.attrs || {};
        const name = attrs.name;
        const ctx = attrs.context || {};
        const shouldHandle = ctx.integrix_show_loader && name === "action_test_connection_wizard";

        if (!shouldHandle) {
            return await this._super(ev);
        }

        const root = this.el || document;
        const btn =
            root.querySelector("button.ix-test-conn-btn") ||
            root.querySelector('[data-name="action_test_connection_wizard"]') ||
            root.querySelector('[name="action_test_connection_wizard"]');

        const box = btn ? (btn.closest(".ix-test-conn") || root) : root;
        const spinner = box.querySelector(".ix-inline-loader");

        if (btn) btn.disabled = true;
        if (spinner) spinner.style.display = "inline-block";

        try {
            return await this._super(ev);
        } finally {
            if (spinner) spinner.style.display = "none";
            if (btn) btn.disabled = false;
        }
    },
});
