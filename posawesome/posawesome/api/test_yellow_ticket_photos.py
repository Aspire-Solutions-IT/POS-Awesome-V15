import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from posawesome.posawesome.api import yellow_ticket_photos


class TestYellowTicketPhotoLinking(FrappeTestCase):
    def test_references_cover_split_orders_main_document_first(self):
        result = {"name": "SO-1", "doctype": "Sales Order", "created_sales_orders": [{"name": "SO-2"}, "SO-1"]}
        self.assertEqual(
            yellow_ticket_photos._references_from_result(result, "Sales Invoice"),
            [("Sales Order", "SO-1"), ("Sales Order", "SO-2")],
        )
        self.assertEqual(
            yellow_ticket_photos._references_from_result({"name": "SINV-1"}, "Sales Invoice"),
            [("Sales Invoice", "SINV-1")],
        )
        self.assertEqual(yellow_ticket_photos._references_from_result(None, "Sales Invoice"), [])

    def test_nothing_happens_without_a_photo_payload(self):
        with patch("customer_due_dates.yellow_ticket_photos.service.link_session") as link:
            yellow_ticket_photos.link_from_submission(json.dumps({}), {"name": "SO-1"}, "Sales Order")
        link.assert_not_called()

    def test_passes_the_payload_through(self):
        data = {
            "yellow_ticket_photos": {
                "client_ref": "basket-12345678",
                "lines": [{"row_ref": "r1", "item_code": "NS-1"}],
                "photos_owed": 1,
            }
        }
        with patch("customer_due_dates.yellow_ticket_photos.service.link_session") as link:
            yellow_ticket_photos.link_from_submission(
                json.dumps(data), {"name": "SO-1"}, "Sales Order", pos_profile="Till 1"
            )
        link.assert_called_once_with(
            "basket-12345678",
            [("Sales Order", "SO-1")],
            lines=[{"row_ref": "r1", "item_code": "NS-1"}],
            photos_owed=1,
            pos_profile="Till 1",
        )

    def test_a_failure_never_reaches_the_sale(self):
        todo = frappe.get_doc({"doctype": "ToDo", "description": "sale written before linking"}).insert()

        def explode(*args, **kwargs):
            frappe.get_doc({"doctype": "ToDo", "description": "written inside the failed link"}).insert()
            raise RuntimeError("WorkDrive is unreachable")

        data = {"yellow_ticket_photos": {"client_ref": "basket-12345678"}}
        with patch("customer_due_dates.yellow_ticket_photos.service.link_session", side_effect=explode):
            yellow_ticket_photos.link_from_submission(data, {"name": todo.name}, "ToDo")

        self.assertTrue(frappe.db.exists("ToDo", todo.name), "the sale's own writes survive")
        self.assertFalse(
            frappe.db.exists("ToDo", {"description": "written inside the failed link"}),
            "the failed link's writes are rolled back",
        )

    def test_requirements_off_unless_the_profile_opts_in(self):
        with patch.object(frappe.db, "get_value", return_value=0):
            result = yellow_ticket_photos.get_requirements("Till 1", "[]")
        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["row_refs"], [])
