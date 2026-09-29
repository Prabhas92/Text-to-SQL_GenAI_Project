# ============================================================
# create_db.py
# Module 1 — Build the Retail Database
# ============================================================

# ------------------------------------------------------------
# 1. IMPORTS
# ------------------------------------------------------------

# sqlite3 is Python's built-in library for working with SQLite
# databases. We don't need to install SQLite separately.
import sqlite3

# random helps us generate realistic-looking sample data.
import random

# date and timedelta help us generate order dates across
# multiple months.
from datetime import date, timedelta


# ------------------------------------------------------------
# 2. PROJECT CONFIGURATION
# ------------------------------------------------------------

# This is the filename of our SQLite database.
# Running this script will create retail.db in the project folder.
DB = "retail.db"


# ------------------------------------------------------------
# 3. REPRODUCIBLE RANDOM DATA
# ------------------------------------------------------------

# Normally random data changes every time we run the program.
#
# random.seed(42) makes the random sequence reproducible.
#
# That means:
#
#     Run 1 → same dataset
#     Run 2 → same dataset
#     Run 3 → same dataset
#
# This is useful for testing and evaluation later.
random.seed(42)


# ------------------------------------------------------------
# 4. REFERENCE DATA
# ------------------------------------------------------------

# These are possible customer cities.
CITIES = [
    "Bengaluru",
    "Delhi",
    "Mumbai",
    "Hyderabad",
    "Chennai",
    "Pune",
    "Kolkata",
    "Ahmedabad",
]


# Possible product categories.
CATEGORIES = [
    "Electronics",
    "Furniture",
    "Clothing",
    "Books",
    "Home",
]


# Possible order statuses.
#
# These values will become important later when our LLM
# needs to understand business rules such as:
#
# "Revenue should exclude cancelled and returned orders."
STATUSES = [
    "placed",
    "shipped",
    "delivered",
    "cancelled",
    "returned",
]


# ------------------------------------------------------------
# 5. PRODUCT DATA
# ------------------------------------------------------------

# A list of product names from which we will randomly
# create products.
PRODUCT_NAMES = [
    "Laptop",
    "Wireless Mouse",
    "Keyboard",
    "Monitor",
    "Headphones",
    "Office Chair",
    "Desk",
    "Bookshelf",
    "T-Shirt",
    "Jeans",
    "Jacket",
    "Python Book",
    "SQL Book",
    "Data Engineering Book",
    "Coffee Maker",
    "Blender",
    "Backpack",
    "Table Lamp",
    "Smartphone",
    "Tablet",
]


# ------------------------------------------------------------
# 6. CONNECT TO SQLITE
# ------------------------------------------------------------

# sqlite3.connect() creates the database if it doesn't already
# exist.
#
# If retail.db already exists, it opens that database.
conn = sqlite3.connect(DB)

# A cursor allows us to execute SQL statements against
# the database.
cursor = conn.cursor()


# ------------------------------------------------------------
# 7. ENABLE FOREIGN KEY CONSTRAINTS
# ------------------------------------------------------------

# SQLite does not always enforce foreign keys unless they are
# explicitly enabled for the connection.
#
# We want relationships such as:
#
# orders.customer_id → customers.customer_id
#
# to be enforced.
cursor.execute("PRAGMA foreign_keys = ON")


# ------------------------------------------------------------
# 8. REMOVE OLD TABLES
# ------------------------------------------------------------

# This makes the script reproducible.
#
# If retail.db already exists and we run this script again,
# we don't want duplicate data.
#
# We therefore remove the existing tables first.
cursor.executescript(
    """
    DROP TABLE IF EXISTS order_items;
    DROP TABLE IF EXISTS orders;
    DROP TABLE IF EXISTS products;
    DROP TABLE IF EXISTS customers;
    """
)


# ------------------------------------------------------------
# 9. CREATE CUSTOMERS TABLE
# ------------------------------------------------------------

cursor.execute(
    """
    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        city TEXT NOT NULL
    )
    """
)


# ------------------------------------------------------------
# 10. CREATE PRODUCTS TABLE
# ------------------------------------------------------------

cursor.execute(
    """
    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_price REAL NOT NULL
    )
    """
)


# ------------------------------------------------------------
# 11. CREATE ORDERS TABLE
# ------------------------------------------------------------

cursor.execute(
    """
    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        status TEXT NOT NULL,

        FOREIGN KEY (customer_id)
            REFERENCES customers(customer_id)
    )
    """
)


# ------------------------------------------------------------
# 12. CREATE ORDER_ITEMS TABLE
# ------------------------------------------------------------

cursor.execute(
    """
    CREATE TABLE order_items (
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,

        FOREIGN KEY (order_id)
            REFERENCES orders(order_id),

        FOREIGN KEY (product_id)
            REFERENCES products(product_id)
    )
    """
)


# ------------------------------------------------------------
# 13. INSERT CUSTOMERS
# ------------------------------------------------------------

# We will create 100 customers.
#
# range(1, 101) produces:
#
# 1, 2, 3, ... 100
#
# Each customer receives:
#   - an ID
#   - a generated name
#   - a random city

customers = []

for customer_id in range(1, 101):

    name = f"Customer {customer_id}"

    city = random.choice(CITIES)

    customers.append(
        (customer_id, name, city)
    )


# executemany() inserts many rows efficiently.
cursor.executemany(
    """
    INSERT INTO customers
        (customer_id, name, city)
    VALUES (?, ?, ?)
    """,
    customers
)


# ------------------------------------------------------------
# 14. INSERT PRODUCTS
# ------------------------------------------------------------

products = []

for product_id, product_name in enumerate(
    PRODUCT_NAMES,
    start=1,
):

    # Generate a realistic-looking product price.
    price = round(
        random.uniform(10, 2000),
        2,
    )

    category = random.choice(CATEGORIES)

    products.append(
        (
            product_id,
            product_name,
            category,
            price,
        )
    )


cursor.executemany(
    """
    INSERT INTO products
        (product_id, name, category, unit_price)
    VALUES (?, ?, ?, ?)
    """,
    products
)


# ------------------------------------------------------------
# 15. GENERATE ORDERS
# ------------------------------------------------------------

orders = []

# We want approximately 1,500 orders.
for order_id in range(1, 1501):

    # Pick a random existing customer.
    customer_id = random.randint(1, 100)

    # Generate a random date over approximately 20 months.
    #
    # 600 days is roughly 20 months.
    days_ago = random.randint(0, 600)

    order_date = (
        date.today() - timedelta(days=days_ago)
    ).isoformat()

    status = random.choice(STATUSES)

    orders.append(
        (
            order_id,
            customer_id,
            order_date,
            status,
        )
    )


cursor.executemany(
    """
    INSERT INTO orders
        (order_id, customer_id, order_date, status)
    VALUES (?, ?, ?, ?)
    """,
    orders
)


# ------------------------------------------------------------
# 16. GENERATE ORDER ITEMS
# ------------------------------------------------------------

order_items = []

# Every order can contain between 1 and 5 products.
for order_id in range(1, 1501):

    number_of_items = random.randint(1, 5)

    for _ in range(number_of_items):

        product_id = random.randint(
            1,
            len(PRODUCT_NAMES),
        )

        quantity = random.randint(1, 5)

        order_items.append(
            (
                order_id,
                product_id,
                quantity,
            )
        )


cursor.executemany(
    """
    INSERT INTO order_items
        (order_id, product_id, quantity)
    VALUES (?, ?, ?)
    """,
    order_items
)


# ------------------------------------------------------------
# 17. SAVE CHANGES
# ------------------------------------------------------------

# Until commit(), the changes are part of the current
# database transaction.
#
# commit() permanently saves our INSERTs.
conn.commit()


# ------------------------------------------------------------
# 18. BASIC VERIFICATION
# ------------------------------------------------------------

# Let's verify that the database contains the expected
# number of rows.

cursor.execute("SELECT COUNT(*) FROM customers")
customer_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM products")
product_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM orders")
order_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM order_items")
order_item_count = cursor.fetchone()[0]


# ------------------------------------------------------------
# 19. DISPLAY RESULTS
# ------------------------------------------------------------

print("Database created successfully!")
print()
print(f"Database : {DB}")
print(f"Customers: {customer_count}")
print(f"Products : {product_count}")
print(f"Orders   : {order_count}")
print(f"Items    : {order_item_count}")


# ------------------------------------------------------------
# 20. CLOSE DATABASE CONNECTION
# ------------------------------------------------------------

# Always close the database connection when we're finished.
conn.close()

print()
print("Database connection closed.")