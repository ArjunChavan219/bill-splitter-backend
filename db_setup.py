import os
import json
import psycopg2
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


# Creating Database
conn_ = psycopg2.connect(f"dbname=postgres user={os.getenv('DB_USER')} password={os.getenv('DB_PASSWORD')}")
conn_.autocommit = True
cur_ = conn_.cursor()
database = "bill_splitter_db"
cur_.execute(f"CREATE database {database}")
conn_.close()
print("Database created")


# Generating data for tables
# Bills Table
with open("Database/bills.json") as file:
    bills_j = json.load(file)

bills_c = {
    "name": [],
    "group": [],
    "status": []
}

for bill in bills_j:
    bills_c["name"].append(bill["name"])
    bills_c["group"].append(bill["group"])
    bills_c["status"].append(bill["status"])

pd.DataFrame(bills_c).to_csv("Database/bills.csv", index=False)

# Items Table
items_c = {
    "bill_name": [],
    "name": [],
    "cost": [],
    "quantity": [],
    "type": []
}

for bill in bills_j:
    for item in bill["items"]:
        items_c["bill_name"].append(bill["name"])
        items_c["name"].append(item["name"])
        items_c["cost"].append(item["cost"])
        items_c["quantity"].append(item["quantity"])
        items_c["type"].append(item["type"])

pd.DataFrame(items_c).to_csv("Database/items.csv", index=False)

# Users Table
with open("Database/users.json") as file:
    users_j = json.load(file)
with open("Database/userGroups.json") as file:
    groups_j = json.load(file)

user_groups = {}
for group in groups_j:
    for user in group["users"]:
        user_groups[user] = group["name"]

user_c = {
    "username": [],
    "first_name": [],
    "last_name": [],
    "password": [],
    "user_group": []
}

for user in users_j:
    user_c["username"].append(user["username"])
    user_c["first_name"].append(user["firstName"])
    user_c["last_name"].append(user["lastName"])
    user_c["password"].append(user["password"])
    user_c["user_group"].append(user_groups[user["username"]])

pd.DataFrame(user_c).to_csv("Database/users.csv", index=False)

print("CSV files created")


# Generating Tables
def create_cols(cols):
    return ", ".join([f"{key} {value} NOT NULL" for key, value in cols.items()])


def create_table(name, cols, primary, col_id=""):
    if col_id != "":
        col_id += " serial, "
    conn = psycopg2.connect(f"dbname={database} user={os.getenv('DB_USER')} password={os.getenv('DB_PASSWORD')}")
    cur = conn.cursor()
    cur.execute(f"CREATE TABLE {name}({col_id}{create_cols(cols)}, PRIMARY KEY ({primary}))")
    if not name.startswith("user_"):
        col_names = ", ".join(cols.keys())
        add_csv_q = (
            f"COPY {name}({col_names})"
            f"FROM '{os.getcwd()}/Database/{name}.csv'"
            f"DELIMITER ','"
            f"CSV HEADER;"
        )
        cur.execute(add_csv_q)
    conn.commit()
    conn_.close()


# Users Table
create_table("users", {
    "username": "text",
    "first_name": "text",
    "last_name": "text",
    "password": "text",
    "user_group": "text"
}, "username")

# Bills Table
create_table("bills", {
    "bill_name": "text",
    "bill_group": "text",
    "status": "text"
}, "bill_name")

# Items Table
create_table("items", {
    "bill_name": "text",
    "item_name": "text",
    "cost": "numeric",
    "quantity": "int",
    "type": "text"
}, "item_id", "item_id")

# User Bills Table
create_table("user_bills", {
    "username": "text",
    "bill_name": "text",
    "amount": "numeric",
    "paid": "boolean",
    "locked": "boolean"
}, "username, bill_name")

# User Items Table
create_table("user_items", {
    "username": "text",
    "item_id": "int",
    "amount": "numeric",
    "share": "numeric"
}, "username, item_id")

print("Tables created")
