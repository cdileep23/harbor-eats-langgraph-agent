# Harbor Eats support agent (LangGraph, OpenTelemetry) (Postgres)

A chat support assistant for Harbor Eats, a fictional seafood delivery kitchen. It is a LangGraph ReAct agent
(`create_react_agent`) on an Anthropic Claude chat model (`langchain-anthropic`) with ten tools, traced with
OpenTelemetry over OTLP.

## HTTP interface

| Method | Path      | Purpose                                    |
|--------|-----------|--------------------------------------------|
| POST   | `/chat`   | One conversation turn.                     |
| GET    | `/health` | Readiness probe. Returns `{"status":"ok"}`. |

Listens on port `8080`, overridable with `AGENT_PORT`.

Request (the FutureAGI agent callback envelope; only `messages` and `new_message` are read):

```json
{"turn_index": 0, "messages": [{"role": "user", "content": "where is HE-5001"}], "new_message": "where is HE-5001"}
```

Response:

```json
{
  "content": "Your order HE-5001 is nearby with Sam Okafor, about 6 minutes away.",
  "tool_calls": [{"id": "call_1", "name": "get_order", "arguments": {"order_id": "HE-5001"}}],
  "tool_responses": [{"id": "call_1", "name": "get_order", "content": "{\"found\": true}"}]
}
```

## Tools

| Tool                      | Arguments                                                        | Behaviour |
|---------------------------|------------------------------------------------------------------|-----------|
| `lookup_customer`         | `email`, `phone_last4`                                           | Verifies the customer. Reads `customers`. |
| `get_order`               | `order_id`                                                       | The order with its items and delivery. Reads `orders`, `order_items`, `menu_items`, `deliveries`. |
| `list_menu`               | `category`: one of `mains`, `sides`, `drinks`, `desserts`        | Items with price and stock. Reads `menu_items`. |
| `place_order`             | `customer_id`, `item_id`, `quantity` (1 to 10), `size` (`s`, `m`, `l`, optional), `note` (optional) | Adds to `orders`, `order_items`, `deliveries`. Refuses an out-of-stock item. |
| `change_delivery_address` | `order_id`, `new_address`                                        | Changes `orders`. Refuses once the courier has picked the order up. |
| `request_refund_approval` | `order_id`, `amount_cents` (1 to 20000), `reason`                | Adds a pending row to `refund_approvals` for the store manager. |
| `check_refund_approval`   | `approval_id`                                                    | Reads `refund_approvals`. |
| `issue_refund`            | `order_id`, `amount_cents` (1 to 20000), `reason`                | Adds to `refunds`. Over $50 needs an approved request; older than 30 days is refused. |
| `send_receipt`            | `order_id`, `email`                                              | Calls the outside receipts email API (`RECEIPTS_API_URL`). |
| `estimate_eta`            | `distance_km`, `items`                                           | Worked out inside the agent; touches no data. |

## Who else acts in this world

The agent is not the only one changing the data. Three other people act on it while a customer is talking:

| Actor            | What they do                                                                 | Data they change |
|------------------|------------------------------------------------------------------------------|------------------|
| Store manager    | Approves or declines refund requests, usually within a few minutes. Declines anything that looks like abuse. | `refund_approvals` (`status`, `decided_by`) |
| Kitchen          | Marks a menu item out of stock when it runs out, sometimes in the middle of an order. | `menu_items` (`in_stock`) |
| Courier          | Picks orders up and updates the delivery as they go, which closes the window for address changes. | `deliveries` (`status`, `eta_minutes`, `courier_name`) |

## Rules the agent keeps

- Verify the customer with `lookup_customer` before placing an order, changing an address or refunding.
- Never share another customer's orders, address or details.
- Refunds over $50 need the store manager's approval first.
- No refunds on orders older than 30 days.
- An address can only change before the courier picks the order up.

## Fixture data

Customers: `C-100` Maya Patel (maya.patel@example.com, phone ending 4421), `C-101` Leo Brandt (leo.brandt@example.com,
9083), `C-102` Ana Souza (ana.souza@example.com, 1177).

Orders:
- `HE-5001` is out for delivery and nearby.
- `HE-5002` is preparing, so its address can still change.
- `HE-5003` was delivered 3 days ago for $78, so a full refund needs the manager.
- `HE-5004` was delivered 45 days ago, outside the refund window.
- `HE-5005` was just placed.

The lobster roll (`M-3`) is out of stock. Data lives in Postgres (`agent/schema.sql`). The agent creates the tables
and seeds them on startup when they are missing.

## Configuration

| Variable                              | Purpose |
|---------------------------------------|---------|
| `ANTHROPIC_API_KEY`                   | Required. The Anthropic API key. |
| `DATABASE_URL`                        | Required. Postgres connection string, for example `postgresql://user:pass@host:5432/db`. |
| `ANTHROPIC_MODEL`                     | Optional, default `claude-haiku-5-5`. |
| `RECEIPTS_API_KEY`                    | Optional. Without it `send_receipt` answers that receipts are not configured. |
| `RECEIPTS_API_URL`                    | Optional, default `https://api.resend.com/emails`. |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`  | Where traces are sent (OTLP over HTTP). |
| `OTEL_EXPORTER_OTLP_TRACES_HEADERS`   | Optional exporter headers. |

## Running it

```
pip install -r requirements.txt
ANTHROPIC_API_KEY=... DATABASE_URL=... python -m agent.server
curl -s localhost:8080/chat -H 'content-type: application/json' -d '{"new_message":"where is HE-5001","messages":[]}'
```
