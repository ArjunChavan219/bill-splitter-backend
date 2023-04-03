import os
import jwt
import psycopg2
import pandas as pd
from flask_cors import CORS
from functools import wraps
from dotenv import load_dotenv
from twilio.rest import Client
from flask import Flask, request
from random import choice, shuffle
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

connection = f"dbname=bill_splitter_db user={os.getenv('DB_USER')} password={os.getenv('DB_PASSWORD')}"

app = Flask(__name__)
CORS(app)

account_sid = "AC4d26ee4b7ff5b5d27c8835e9fdb1d427"
auth_token = "02127d31bb90086ab2d78be003c03566"
TWILIO_PHONE = "+14155238886"
MY_PHONE = "+918451956800"


# Function to return error object
def auth_error(error):
    return {
        "error": error
    }


# Function for token authentication
def token_check(f):
    @wraps(f)
    def decorated_function():
        if 'x-access-token' not in request.headers or "x-access-user" not in request.headers:
            return auth_error("Missing headers")

        try:
            token = jwt.decode(request.headers["x-access-token"], "secret", algorithms=["HS256"])
        except (jwt.InvalidTokenError, jwt.DecodeError):
            return auth_error("Invalid token")

        if token["username"] != request.headers["x-access-user"]:
            return auth_error("Invalid user token")

        return f()

    return decorated_function


# Function for get user item/bill data
def get_data(input_cols, table_name, format_cols, output_cols, condition=""):
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    table = "user_items ui inner join items i on ui.item_id=i.item_id" if table_name == "user_items" else table_name
    cur.execute(f"select {input_cols} from {table} {condition};")
    df = pd.DataFrame(cur.fetchall(), columns=output_cols)
    for col in format_cols:
        df[col] = df[col].astype("float")

    conn.commit()
    conn.close()
    return df.to_dict("records")


# Function for ids for items
def get_item_ids(bill):
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    cur.execute(f"select item_id, item_name from items where bill_name='{bill}';")
    ids = {name: item_id for item_id, name in cur.fetchall()}

    conn.commit()
    conn.close()
    return ids, ", ".join([str(id_) for id_ in ids.values()])


# Function to get item entry strings
def get_item_entries(username, items, item_ids):
    item_entries = []
    for item in items:
        item_id, amount, share = item_ids[item["name"]], item["cost"], item["share"]
        item_entries.append(f"('{username}', {str(item_id)}, {str(amount)}, {str(share)})")
    return ", ".join(item_entries)


# Function to generate a password
def password_generator():
    letters_small = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's',
                     't', 'u', 'v', 'w', 'x', 'y', 'z']
    letters_caps = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S',
                    'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
    numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    symbols = ['!', '#', '$', '%', '&', '(', ')', '*', '+', '_']

    password_list = [choice(letters_small) for _ in range(3)]
    password_list.append(choice(letters_caps))
    password_list.append(choice(numbers))
    password_list.append(choice(symbols))
    shuffle(password_list)
    return "".join(password_list)


# Server test ping
@app.route('/api/ping', methods=["GET"])
def server_ping():
    return {
        "status": 200
    }


# Check if username and password exist
@app.route('/api/login', methods=["GET"])
def login_check():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    cur.execute(f"select username, password from users;")
    users_dict = {username: password for username, password in cur.fetchall()}

    username = request.args.get("username")
    password = request.args.get("password")
    if username not in users_dict:
        conn.commit()
        conn.close()
        return {
            "success": False,
            "error": "Username"
        }

    if not check_password_hash(users_dict[username], password):
        conn.commit()
        conn.close()
        return {
            "success": False,
            "error": "Password"
        }

    cur.execute(f"select first_name, last_name, user_group from users where username='{username}';")
    user_first_name, user_last_name, user_group = cur.fetchone()
    conn.commit()
    conn.close()
    return {
        "success": True,
        "token": jwt.encode({"username": username}, "secret", algorithm="HS256"),
        "userGroup": user_group,
        "userName": user_first_name + " " + user_last_name
    }


# Change password
@app.route('/api/password', methods=["POST"])
@token_check
def change_password():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    username = request.json["username"]
    password = generate_password_hash(request.json["password"], "sha256")
    cur.execute(f"update users set password='{password}' where username='{username}';")

    conn.commit()
    conn.close()
    return {
        "success": True
    }


# Get User data
@app.route('/api/user', methods=["GET"])
@token_check
def user_data():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    username = request.args.get("username")
    cur.execute(f"select first_name, last_name from users where username='{username}';")
    user_name = {key: value for key, value in zip(["firstName", "lastName"], cur.fetchone())}
    conn.commit()
    conn.close()
    return user_name


# Get list of all unsettled bills
@app.route('/api/bills', methods=["GET"])
@token_check
def get_bills():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    user_group = request.args.get("userGroup")
    condition = "" if user_group == "admin" else f" where bill_group='{user_group}'"
    cur.execute(f"select bill_name from bills{condition};")
    bills = [bill[0] for bill in cur.fetchall()]
    conn.commit()
    conn.close()
    return {
        "bills": bills
    }


# Get bill data
@app.route('/api/bill', methods=["GET"])
@token_check
def get_bill():
    bill = request.args.get("bill").replace("'", "''")
    items = get_data("item_name, quantity, type", "items", [],
                     ["name", "quantity", "type"], f" where bill_name='{bill}'")
    for item in items:
        item["cost"] = 0
        item["share"] = 0

    return {"items": items}


# Get bills for the user
@app.route('/api/user-bills', methods=["GET"])
@token_check
def get_user_bills():
    username = request.args.get("username")
    return {"bills": get_data("bill_name, amount, paid, locked", "user_bills", ["amount"],
                              ["name", "amount", "paid", "locked"], f"where username='{username}'")}


# Get a bill for the user
@app.route('/api/user-bill', methods=["GET"])
@token_check
def get_user_bill():
    username = request.args.get("username")
    bill = request.args.get("bill").replace("'", "''")

    return {
        "items": get_data("item_name, amount, quantity, share, type", "user_items", ["cost", "share"],
                          ["name", "cost", "quantity", "share", "type"],
                          f"where bill_name='{bill}' and username='{username}'")
    }


# Add a bill to user bills
@app.route('/api/add-user-bills', methods=["POST"])
@token_check
def add_user_bills():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    username = request.json["username"]
    user_bills = [bill.replace("'", "''") for bill in request.json["bills"]]
    entries = ", ".join([f"('{username}', '{bill}', 0, false, false)" for bill in user_bills])
    cur.execute(f"insert into user_bills (username, bill_name, amount, paid, locked) values {entries};")

    conn.commit()
    conn.close()
    return {}


# Remove a bill from user bills
@app.route('/api/remove-user-bills', methods=["POST"])
@token_check
def remove_user_bills():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    username = request.json["username"]
    bills = request.json["bills"]
    entries = ", ".join(["'" + bill.replace("'", "''") + "'" for bill in bills])
    cur.execute(f"delete from user_bills where username='{username}' and bill_name in ({entries});")
    id_query = ", ".join([get_item_ids(bill.replace("'", "''"))[1] for bill in bills])
    cur.execute(f"delete from user_items where username='{username}' and item_id in ({id_query});")

    conn.commit()
    conn.close()
    return {}


# Update a user bill
@app.route('/api/update-user-bill', methods=["POST"])
@token_check
def update_user_bill():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    username = request.json["username"]
    bill = request.json["bill"].replace("'", "''")
    items = request.json["items"]
    item_ids, id_query = get_item_ids(bill)
    entries = get_item_entries(username, items, item_ids)
    cur.execute(f"delete from user_items where username='{username}' and item_id in ({id_query});")
    cur.execute(f"insert into user_items (username, item_id, amount, share) values {entries};")

    conn.commit()
    conn.close()
    return {}


# Lock a user bill
@app.route('/api/lock-user-bill', methods=["POST"])
@token_check
def lock_user_bill():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    username = request.json["username"]
    bill_name = request.json["bill"].replace("'", "''")
    cur.execute(f"update user_bills set locked=true where username='{username}' and bill_name='{bill_name}';")
    conn.commit()
    conn.close()
    return {}


# Unlock a bill for the users
@app.route('/api/unlock-bill', methods=["POST"])
@token_check
def unlock_bill():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    usernames = ", ".join([f"'{user}'" for user in request.json["users"]])
    bill_name = request.json["bill"].replace("'", "''")
    cur.execute(f"update user_bills set locked=false where bill_name='{bill_name}' and username in ({usernames});")
    conn.commit()
    conn.close()
    return {}


# Get all bills and update their statuses
@app.route('/api/all-bills', methods=["GET"])
@token_check
def get_all_bills():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    update_bills = []
    cur.execute("select bill_name, bool_and(locked), count(locked) from user_bills group by bill_name;")
    bills_data = {bill_name: (all_locked, user_count) for bill_name, all_locked, user_count in cur.fetchall()}
    all_bills = get_data("bill_name, status", "bills", [], ["name", "status"])
    for bill in all_bills:
        status = "open"
        if bill["name"] in bills_data:
            all_locked, user_count = bills_data[bill["name"]]
            status = "ready" if all_locked else "pending"
            bill["members"] = user_count
        if bill["status"] != "settled" and bill["status"] != status:
            bill["status"] = status
            update_bills.append((bill["name"].replace("'", "''"), status))

    if len(update_bills) != 0:
        entries = ", ".join([f"('{entry[0]}', '{entry[1]}')" for entry in update_bills])
        cur.execute(f"update bills as b set status=b2.status from (values {entries}) as b2(bill_name, status)\n"
                    f"where b.bill_name = b2.bill_name;")

    order = {"ready": 0, "pending": 1, "open": 2, "settled": 3}

    conn.commit()
    conn.close()
    return {
        "bills": sorted(all_bills, key=lambda a: (order[a["status"]], a["name"]))
    }


# Calculate and get user and item details for a bill
@app.route('/api/manage-bill', methods=["GET"])
@token_check
def manage_bill():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    bill = request.args.get("bill").replace("'", "''")
    cur.execute(f"select username from user_bills where bill_name='{bill}';")
    bill_users = [bill_data[0] for bill_data in cur.fetchall()]

    items_data: dict[str, list] = {}
    cur.execute(f"select username, item_name, share\n"
                f"from user_items ui inner join items i on ui.item_id=i.item_id\n"
                f"where bill_name='{bill}';")
    for item_user, item_name, user_share in cur.fetchall():
        if item_name not in items_data:
            items_data[item_name] = []
        items_data[item_name].append({
            "username": item_user,
            "share": float(user_share)
        })

    for item in items_data:
        sharing = {}
        specified = {}
        total_share = 0
        item_users = items_data[item]

        for user in item_users:
            if user["share"] == 0:
                sharing[user["username"]] = None
            else:
                specified[user["username"]] = None
                total_share += user["share"]

        if len(sharing) == 0:
            if total_share != 1:
                change = (1 - total_share) / len(specified)
                for user in item_users:
                    if user["username"] in specified:
                        user["share"] = round(user["share"] + change, 2)
        else:
            if total_share < 1:
                change = (1 - total_share) / len(sharing)
                for user in item_users:
                    if user["username"] in sharing:
                        user["share"] = round(change, 2)
            else:
                if total_share > 1:
                    change = (1 - total_share) / len(specified)
                    for user in item_users:
                        if user["username"] in specified:
                            user["share"] += change
                change = 1 / (len(specified) + len(sharing))

                for user in item_users:
                    if user["username"] in sharing:
                        user["share"] = round(change, 2)
                    else:
                        user["share"] = round(user["share"] * change * len(specified), 2)

    cur.execute(f"select item_name from items where bill_name='{bill}'")
    for item in cur.fetchall():
        if item[0] not in items_data:
            items_data[item[0]] = []
    cur.execute(f"select bill_group from bills where bill_name='{bill}'")
    bill_group = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return {
        "items": [{"name": key, "users": value} for key, value in items_data.items()],
        "users": bill_users,
        "group": bill_group
    }


# Save bill and update amounts for users
@app.route('/api/save-bill', methods=["POST"])
@token_check
def save_bill():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    bill = request.json["bill"].replace("'", "''")
    new_users = request.json["newUsers"]
    old_users = request.json["oldUsers"]
    items_data = request.json["items"]

    bill_data = get_data("item_name, cost, quantity, type", "items", ["cost"],
                         ["name", "cost", "quantity", "type"], f"where bill_name='{bill}'")
    items = {item["name"]: item for item in bill_data}
    user_items = {}
    for item in items_data:
        for user in item["users"]:
            if user["username"] not in user_items:
                user_items[user["username"]] = {"items": [], "amount": 0}
            user_items[user["username"]]["items"].append({
                "name": item["name"],
                "quantity": items[item["name"]]["quantity"],
                "type": items[item["name"]]["type"],
                "share": user["share"],
                "cost": round(items[item["name"]]["cost"] * user["share"], 2)
            })

    existing_users = list(set(user_items) - set(new_users) - set(old_users))
    item_ids, id_query = get_item_ids(bill)

    if len(new_users) != 0:
        entries = ", ".join([f"('{user}', '{bill}', 0, false, true)" for user in new_users])
        cur.execute(f"insert into user_bills (username, bill_name, amount, paid, locked) values {entries};")

        entries = ", ".join([get_item_entries(user, user_items[user]["items"], item_ids) for user in new_users])
        cur.execute(f"insert into user_items (username, item_id, amount, share) values {entries};")

    if len(old_users) != 0:
        entries = ", ".join(["'" + user + "'" for user in old_users])
        cur.execute(f"delete from user_bills where username in ({entries}) and bill_name='{bill}';")
        cur.execute(f"delete from user_items where username in ({entries}) and item_id in ({id_query});")

    entries = ", ".join(["'" + user + "'" for user in existing_users])
    cur.execute(f"delete from user_items where username in ({entries}) and item_id in ({id_query});")
    entries = ", ".join([get_item_entries(user, user_items[user]["items"], item_ids) for user in existing_users])
    cur.execute(f"insert into user_items (username, item_id, amount, share) values {entries};")

    conn.commit()
    conn.close()
    return {}


# Save bill and update amounts for users
@app.route('/api/submit-bill', methods=["POST"])
@token_check
def submit_bill():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    bill = request.json["bill"].replace("'", "''")
    user_amounts = {}
    cur.execute(f"select username, amount\n"
                f"from user_items ui inner join items i on ui.item_id=i.item_id\n"
                f"where bill_name='{bill}';")
    for item_user, user_amount in cur.fetchall():
        if item_user not in user_amounts:
            user_amounts[item_user] = 0
        user_amounts[item_user] += float(user_amount)

    cur.execute(f"update bills set status='settled' where bill_name='{bill}';")
    entries = ", ".join([f"('{user}', {round(user_amounts[user], 2)})" for user in user_amounts])
    cur.execute(f"update user_bills as ub set amount=ub2.amount from (values {entries}) as ub2(username, amount)\n"
                f"where bill_name='{bill}' and ub.username = ub2.username;")
    conn.commit()
    conn.close()
    return {}


# Return users for that userGroup
@app.route('/api/users', methods=["GET"])
@token_check
def get_users():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    group = request.args["group"]
    cur.execute(f"select username from users where user_group='admin' or user_group='{group}';")
    users = [q[0] for q in cur.fetchall()]
    conn.commit()
    conn.close()
    return {
        "users": users
    }


# Return users and their shares for that bill
@app.route('/api/bill-split', methods=["GET"])
@token_check
def bill_split():
    bill = request.args["bill"].replace("'", "''")
    return {
        "users": get_data("username, amount, paid", "user_bills", ["share"],
                          ["name", "share", "paid"], f"where bill_name='{bill}'")
    }


# Return all users and their respective debts
@app.route('/api/all-users', methods=["GET"])
@token_check
def all_users():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    cur.execute("select username from users;")
    user_bills_each = {user[0]: [] for user in cur.fetchall()}
    user_bills_all = get_data("username, bill_name, amount, paid", "user_bills", ["amount"],
                              ["username", "name", "amount", "paid"], "where amount!=0 and paid=false")
    for entry in user_bills_all:
        user_bills_each[entry["username"]].append({key: entry[key] for key in entry if key != "username"})

    conn.commit()
    conn.close()
    return {
        "users": [{'username': key, 'bills': value} for key, value in user_bills_each.items()]
    }


# Create a user
@app.route('/api/create-user', methods=["POST"])
@token_check
def create_user():
    conn = psycopg2.connect(connection)
    cur = conn.cursor()
    first_name = request.json["firstName"]
    last_name = request.json["lastName"]
    user_group = request.json["userGroup"]
    username = first_name.lower() + last_name[0].upper()
    password = password_generator()
    final_pass = generate_password_hash(password, "sha256")

    cur.execute(f"insert into users (username, first_name, last_name, password, user_group) values"
                f" ('{username}', '{first_name}', '{last_name}', '{final_pass}', '{user_group}');")

    client = Client(account_sid, auth_token)

    message = client.messages.create(
        from_=f"whatsapp:{TWILIO_PHONE}",
        body=f"New user created:\n{username} @ {password} # {user_group}",
        to=f"whatsapp:{MY_PHONE}"
    )

    conn.commit()
    conn.close()
    return {}


if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=3000)
