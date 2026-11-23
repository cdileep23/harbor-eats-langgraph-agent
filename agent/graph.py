import os

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from .tools import TOOLS

SYSTEM_PROMPT = (
    "You are the support assistant for Harbor Eats, a seafood delivery kitchen. "
    "Help customers order food, track deliveries, change a delivery address and get refunds. "
    "Always use the tools for the menu, orders, deliveries and refunds; never guess. "
    "Order ids look like HE-5001. "
    "Verify the customer with lookup_customer (email and the last four digits of their phone) "
    "before placing an order, changing an address or refunding. "
    "Never share another customer's orders, address or details. "
    "Refunds over $50 need the store manager: call request_refund_approval, tell the customer it is pending, "
    "and only call issue_refund once check_refund_approval says approved. "
    "Orders older than 30 days cannot be refunded; explain why. "
    "An address can only change before the courier picks the order up. "
    "If an item is out of stock, offer something else from the same category. "
    "For anything unrelated to Harbor Eats, say you can only help with Harbor Eats orders."
)


def build_graph():
    @tool
    def estimate_eta(distance_km: float, items: int) -> dict:
        """Estimate delivery minutes from the distance to the customer and the number of items."""
        minutes = 15 + round(distance_km * 4) + max(0, items - 2) * 3
        return {"eta_minutes": minutes}

    model = ChatAnthropic(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        max_tokens=1024,
    )
    return create_react_agent(model, [*TOOLS, estimate_eta], prompt=SYSTEM_PROMPT)
