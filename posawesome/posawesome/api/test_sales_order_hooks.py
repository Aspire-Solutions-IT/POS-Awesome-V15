import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS_PATH = REPO_ROOT / "posawesome" / "hooks.py"


class TestSalesOrderHooks(unittest.TestCase):
    def test_sales_order_submit_hook_registered(self):
        hooks = HOOKS_PATH.read_text()

        self.assertIn('"Sales Order": {', hooks)
        self.assertIn('"on_submit": "posawesome.posawesome.api.sales_orders.on_submit"', hooks)

    def test_sales_order_cancel_hook_registered(self):
        hooks = HOOKS_PATH.read_text()

        self.assertIn('"Sales Order": {', hooks)
        self.assertIn('"on_cancel": "posawesome.posawesome.api.sales_orders.on_cancel"', hooks)


if __name__ == "__main__":
    unittest.main()
