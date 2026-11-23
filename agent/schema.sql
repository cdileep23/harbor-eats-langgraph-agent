CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone_last4 TEXT NOT NULL,
    default_address TEXT NOT NULL,
    loyalty_tier TEXT NOT NULL DEFAULT 'standard' CHECK (loyalty_tier IN ('standard', 'gold', 'platinum'))
);

CREATE TABLE IF NOT EXISTS menu_items (
    item_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('mains', 'sides', 'drinks', 'desserts')),
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    in_stock BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers (customer_id),
    status TEXT NOT NULL CHECK (status IN ('placed', 'preparing', 'out_for_delivery', 'delivered', 'cancelled')),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    delivery_address TEXT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL REFERENCES orders (order_id),
    item_id TEXT NOT NULL REFERENCES menu_items (item_id),
    size TEXT NOT NULL CHECK (size IN ('s', 'm', 'l')),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    PRIMARY KEY (order_id, item_id, size)
);

CREATE TABLE IF NOT EXISTS deliveries (
    order_id TEXT PRIMARY KEY REFERENCES orders (order_id),
    courier_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('waiting', 'picked_up', 'nearby', 'delivered', 'failed')),
    eta_minutes INTEGER CHECK (eta_minutes >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refund_approvals (
    approval_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders (order_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'declined')),
    decided_by TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders (order_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    reason TEXT NOT NULL,
    approval_id TEXT REFERENCES refund_approvals (approval_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO customers (customer_id, full_name, email, phone_last4, default_address, loyalty_tier) VALUES
    ('C-100', 'Maya Patel', 'maya.patel@example.com', '4421', '12 Harbor Way, Apt 3', 'gold'),
    ('C-101', 'Leo Brandt', 'leo.brandt@example.com', '9083', '88 Pier Road', 'standard'),
    ('C-102', 'Ana Souza', 'ana.souza@example.com', '1177', '5 Lighthouse Lane', 'platinum')
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO menu_items (item_id, name, category, price_cents, in_stock) VALUES
    ('M-1', 'Grilled salmon bowl', 'mains', 1850, TRUE),
    ('M-2', 'Fish tacos', 'mains', 1400, TRUE),
    ('M-3', 'Lobster roll', 'mains', 2600, FALSE),
    ('S-1', 'Sweet potato fries', 'sides', 550, TRUE),
    ('S-2', 'Harbor slaw', 'sides', 450, TRUE),
    ('D-1', 'Lemonade', 'drinks', 350, TRUE),
    ('D-2', 'Cold brew', 'drinks', 450, TRUE),
    ('X-1', 'Key lime pie', 'desserts', 700, TRUE)
ON CONFLICT (item_id) DO NOTHING;

INSERT INTO orders (order_id, customer_id, status, total_cents, delivery_address, placed_at) VALUES
    ('HE-5001', 'C-100', 'out_for_delivery', 4250, '12 Harbor Way, Apt 3', '2026-11-23T12:00:00Z'),
    ('HE-5002', 'C-101', 'preparing', 1950, '88 Pier Road', '2026-11-23T12:25:00Z'),
    ('HE-5003', 'C-100', 'delivered', 7800, '12 Harbor Way, Apt 3', '2026-11-20T18:30:00Z'),
    ('HE-5004', 'C-102', 'delivered', 2600, '5 Lighthouse Lane', '2026-10-05T19:00:00Z'),
    ('HE-5005', 'C-102', 'placed', 1400, '5 Lighthouse Lane', '2026-11-23T12:33:00Z')
ON CONFLICT (order_id) DO NOTHING;

INSERT INTO order_items (order_id, item_id, size, quantity) VALUES
    ('HE-5001', 'M-1', 'l', 2),
    ('HE-5001', 'D-1', 'm', 1),
    ('HE-5002', 'M-2', 'm', 1),
    ('HE-5002', 'S-1', 'm', 1),
    ('HE-5003', 'M-3', 'l', 3),
    ('HE-5004', 'M-3', 'm', 1),
    ('HE-5005', 'M-2', 's', 1)
ON CONFLICT (order_id, item_id, size) DO NOTHING;

INSERT INTO deliveries (order_id, courier_name, status, eta_minutes, updated_at) VALUES
    ('HE-5001', 'Sam Okafor', 'nearby', 6, '2026-11-23T12:29:00Z'),
    ('HE-5002', NULL, 'waiting', 30, '2026-11-23T12:25:00Z'),
    ('HE-5003', 'Rita Moreno', 'delivered', 0, '2026-11-20T19:05:00Z'),
    ('HE-5004', 'Sam Okafor', 'delivered', 0, '2026-10-05T19:40:00Z'),
    ('HE-5005', NULL, 'waiting', 40, '2026-11-23T12:33:00Z')
ON CONFLICT (order_id) DO NOTHING;
