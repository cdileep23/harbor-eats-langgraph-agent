import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .db import connect

MANAGER_APPROVAL_OVER_CENTS = 5000
REFUND_WINDOW_DAYS = 30
RECEIPTS_API_URL = os.environ.get("RECEIPTS_API_URL", "https://api.resend.com/emails")


class LookupCustomerInput(BaseModel):
    email: str = Field(description="The email address on the account")
    phone_last4: str = Field(description="The last four digits of the phone number on the account")


class GetOrderInput(BaseModel):
    order_id: str = Field(description="The order id, for example HE-5001")


class ListMenuInput(BaseModel):
    category: Literal["mains", "sides", "drinks", "desserts"] = Field(
        description="Which part of the menu to list"
    )


class PlaceOrderInput(BaseModel):
    customer_id: str = Field(description="The verified customer's id, for example C-100")
    item_id: str = Field(description="The menu item id, for example M-1")
    quantity: int = Field(ge=1, le=10, description="How many of the item, from 1 to 10")
    size: Literal["s", "m", "l"] = Field(default="m", description="Portion size")
    note: str = Field(default="", description="A note for the kitchen")


class ChangeAddressInput(BaseModel):
    order_id: str = Field(description="The order id, for example HE-5002")
    new_address: str = Field(min_length=5, description="The full new delivery address")


class RefundApprovalInput(BaseModel):
    order_id: str = Field(description="The order id to refund")
    amount_cents: int = Field(ge=1, le=20000, description="The refund amount in cents, from 1 to 20000")
    reason: str = Field(description="Why the customer wants a refund")


class IssueRefundInput(BaseModel):
    order_id: str = Field(description="The order id to refund")
    amount_cents: int = Field(ge=1, le=20000, description="The refund amount in cents, from 1 to 20000")
    reason: str = Field(description="Why the refund is given")


class SendReceiptInput(BaseModel):
    order_id: str = Field(description="The order id")
    email: str = Field(description="Where to send the receipt")


def _order(conn, order_id: str) -> dict | None:
    return conn.execute(
        "SELECT order_id, customer_id, status, total_cents, delivery_address, "
        "extract(day FROM now() - placed_at)::int AS age_days FROM orders WHERE order_id = %s",
        (order_id.strip().upper(),),
    ).fetchone()


@tool(args_schema=LookupCustomerInput)
def lookup_customer(email: str, phone_last4: str) -> dict:
    """Verify a customer by email and the last four digits of their phone. Returns their id and default address."""
    with connect() as conn:
        found = conn.execute(
            "SELECT customer_id, full_name, default_address, loyalty_tier FROM customers "
            "WHERE lower(email) = lower(%s) AND phone_last4 = %s",
            (email.strip(), phone_last4.strip()),
        ).fetchone()
    if found is None:
        return {"verified": False}
    return {"verified": True, **found}


@tool(args_schema=GetOrderInput)
def get_order(order_id: str) -> dict:
    """Look up an order with its items and delivery status."""
    with connect() as conn:
        order = _order(conn, order_id)
        if order is None:
            return {"found": False, "order_id": order_id}
        items = conn.execute(
            "SELECT m.name, oi.size, oi.quantity FROM order_items oi "
            "JOIN menu_items m ON m.item_id = oi.item_id WHERE oi.order_id = %s",
            (order["order_id"],),
        ).fetchall()
        delivery = conn.execute(
            "SELECT courier_name, status, eta_minutes FROM deliveries WHERE order_id = %s",
            (order["order_id"],),
        ).fetchone()
    return {"found": True, **order, "items": items, "delivery": delivery}


@tool(args_schema=ListMenuInput)
def list_menu(category: str) -> list[dict]:
    """List the menu items in one category with their price and whether they are in stock."""
    with connect() as conn:
        return conn.execute(
            "SELECT item_id, name, price_cents, in_stock FROM menu_items WHERE category = %s ORDER BY item_id",
            (category,),
        ).fetchall()


@tool(args_schema=PlaceOrderInput)
def place_order(customer_id: str, item_id: str, quantity: int, size: str = "m", note: str = "") -> dict:
    """Place a new order for a verified customer. Refuses an item that is out of stock."""
    with connect() as conn:
        customer = conn.execute(
            "SELECT default_address FROM customers WHERE customer_id = %s", (customer_id,)
        ).fetchone()
        if customer is None:
            return {"placed": False, "error": "customer_not_found"}
        item = conn.execute(
            "SELECT price_cents, in_stock FROM menu_items WHERE item_id = %s", (item_id,)
        ).fetchone()
        if item is None:
            return {"placed": False, "error": "item_not_found"}
        if not item["in_stock"]:
            return {"placed": False, "error": "item_out_of_stock"}
        order_id = f"HE-{uuid.uuid4().int % 90000 + 10000}"
        total = item["price_cents"] * quantity
        conn.execute(
            "INSERT INTO orders (order_id, customer_id, status, total_cents, delivery_address) "
            "VALUES (%s, %s, 'placed', %s, %s)",
            (order_id, customer_id, total, customer["default_address"]),
        )
        conn.execute(
            "INSERT INTO order_items (order_id, item_id, size, quantity) VALUES (%s, %s, %s, %s)",
            (order_id, item_id, size, quantity),
        )
        conn.execute(
            "INSERT INTO deliveries (order_id, status, eta_minutes) VALUES (%s, 'waiting', 40)",
            (order_id,),
        )
    return {"placed": True, "order_id": order_id, "total_cents": total, "note": note}


@tool(args_schema=ChangeAddressInput)
def change_delivery_address(order_id: str, new_address: str) -> dict:
    """Change where an order is delivered. Refuses once the courier has picked it up."""
    with connect() as conn:
        order = _order(conn, order_id)
        if order is None:
            return {"changed": False, "error": "order_not_found"}
        delivery = conn.execute(
            "SELECT status FROM deliveries WHERE order_id = %s", (order["order_id"],)
        ).fetchone()
        if order["status"] in ("out_for_delivery", "delivered", "cancelled") or (
            delivery and delivery["status"] != "waiting"
        ):
            return {"changed": False, "error": "already_picked_up"}
        conn.execute(
            "UPDATE orders SET delivery_address = %s WHERE order_id = %s",
            (new_address.strip(), order["order_id"]),
        )
    return {"changed": True, "order_id": order["order_id"], "delivery_address": new_address.strip()}


@tool(args_schema=RefundApprovalInput)
def request_refund_approval(order_id: str, amount_cents: int, reason: str) -> dict:
    """Ask the store manager to approve a refund over $50. Returns the approval id to check later."""
    with connect() as conn:
        order = _order(conn, order_id)
        if order is None:
            return {"requested": False, "error": "order_not_found"}
        approval_id = f"AP-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO refund_approvals (approval_id, order_id, amount_cents, reason) VALUES (%s, %s, %s, %s)",
            (approval_id, order["order_id"], amount_cents, reason),
        )
    return {"requested": True, "approval_id": approval_id, "status": "pending"}


@tool
def check_refund_approval(approval_id: str) -> dict:
    """Check whether the store manager approved or declined a refund request."""
    with connect() as conn:
        found = conn.execute(
            "SELECT approval_id, order_id, amount_cents, status, decided_by FROM refund_approvals "
            "WHERE approval_id = %s",
            (approval_id.strip(),),
        ).fetchone()
    return {"found": False} if found is None else {"found": True, **found}


@tool(args_schema=IssueRefundInput)
def issue_refund(order_id: str, amount_cents: int, reason: str) -> dict:
    """Refund an order. Over $50 needs an approved manager request; orders older than 30 days are refused."""
    with connect() as conn:
        order = _order(conn, order_id)
        if order is None:
            return {"refunded": False, "error": "order_not_found"}
        if order["age_days"] > REFUND_WINDOW_DAYS:
            return {"refunded": False, "error": "outside_refund_window"}
        if amount_cents > order["total_cents"]:
            return {"refunded": False, "error": "more_than_order_total"}
        approval = None
        if amount_cents > MANAGER_APPROVAL_OVER_CENTS:
            approval = conn.execute(
                "SELECT approval_id FROM refund_approvals WHERE order_id = %s AND status = 'approved' "
                "AND amount_cents >= %s ORDER BY requested_at DESC LIMIT 1",
                (order["order_id"], amount_cents),
            ).fetchone()
            if approval is None:
                return {"refunded": False, "error": "manager_approval_required"}
        refund_id = f"RF-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO refunds (refund_id, order_id, amount_cents, reason, approval_id) VALUES (%s, %s, %s, %s, %s)",
            (refund_id, order["order_id"], amount_cents, reason, approval and approval["approval_id"]),
        )
    return {"refunded": True, "refund_id": refund_id, "amount_cents": amount_cents}


@tool(args_schema=SendReceiptInput)
def send_receipt(order_id: str, email: str) -> dict:
    """Email the receipt for an order through the receipts service."""
    key = os.environ.get("RECEIPTS_API_KEY", "")
    if not key:
        return {"sent": False, "error": "receipts_not_configured"}
    body = json.dumps(
        {"from": "receipts@harboreats.example", "to": [email], "subject": f"Your receipt for {order_id}",
         "text": f"Thanks for ordering with Harbor Eats. Order {order_id}."}
    ).encode("utf-8")
    request = urllib.request.Request(
        RECEIPTS_API_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"sent": response.status < 300}
    except urllib.error.URLError as error:
        return {"sent": False, "error": str(error.reason)}


TOOLS = [
    lookup_customer,
    get_order,
    list_menu,
    place_order,
    change_delivery_address,
    request_refund_approval,
    check_refund_approval,
    issue_refund,
    send_receipt,
]
