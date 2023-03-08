import jwt
import pymongo
from flask import Flask, request
from flask_cors import CORS
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["billSplitterDB"]
users = db["users"]
bills = db["bills"]

app = Flask(__name__)
CORS(app)


def auth_error(error):
    return {
        "error": error
    }


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


# Check if username and password exist
@app.route('/api/login', methods=["GET"])
def login_check():
    users_list = list(users.find({}, {"_id": False, "username": True, "password": True}))
    users_dict = {user["username"]: user["password"] for user in users_list}

    username = request.args.get("username")
    password = request.args.get("password")
    if username not in users_dict:
        return {
            "success": False,
            "error": "Username"
        }

    if not check_password_hash(users_dict[username], password):
        return {
            "success": False,
            "error": "Password"
        }

    return {
        "success": True,
        "token": jwt.encode({"username": username}, "secret", algorithm="HS256"),
        "userGroup": db["userGroups"].find({"users": username}, {"_id": False, "name": True})[0]["name"]
    }


# Change password
@app.route('/api/password', methods=["POST"])
@token_check
def change_password():
    username = request.json["username"]
    password = generate_password_hash(request.json["password"], "sha256")
    users.update_one({"username": username}, {"$set": {"password": password}})

    return {
        "success": True
    }


# Get User data
@app.route('/api/user', methods=["GET"])
@token_check
def user_data():
    username = request.args.get("username")
    return users.find({"username": username}, {"_id": False, "firstName": True, "lastName": True})[0]


# Get list of all unsettled bills
@app.route('/api/bills', methods=["GET"])
@token_check
def get_bills():
    user_group = request.args.get("userGroup")
    if user_group == "admin":
        all_bills = bills.find({"status": {"$ne": "settled"}}, {"_id": False, "name": True})
    else:
        all_bills = bills.find({"status": {"$ne": "settled"}, "group": user_group}, {"_id": False, "name": True})
    return {
        "bills": [bill["name"] for bill in all_bills]
    }


# Get bill data
@app.route('/api/bill', methods=["GET"])
@token_check
def get_bill():
    items = list(bills.find({"name": request.args.get("bill")}, {"_id": False, "items": True}))[0]["items"]
    for item in items:
        item["cost"] = 0
        item["share"] = 0

    return {"items": items}


# Get bills for the user
@app.route('/api/user-bills', methods=["GET"])
@token_check
def get_user_bills():
    return list(users.find({"username": request.args.get("username")},
                           {"_id": False, "bills.name": True, "bills.amount": True,
                            "bills.paid": True, "bills.locked": True}))[0]


# Get a bill for the user
@app.route('/api/user-bill', methods=["GET"])
@token_check
def get_user_bill():
    return list(users.find({"username": request.args.get("username"), "bills.name": request.args.get("bill")},
                           {"_id": False, "bills.$": 1}))[0]["bills"][0]


# Add a bill to user bills
@app.route('/api/add-user-bills', methods=["POST"])
@token_check
def add_user_bills():
    user_entry = {"username": request.json["username"], "locked": False}
    user_bills = [{"name": bill, "items": [], "amount": 0, "paid": False, "locked": False}
                  for bill in request.json["bills"]]

    users.update_one({"username": request.json["username"]}, {"$push": {"bills": {"$each": user_bills}}})
    bills.update_many({"name": {"$in": request.json["bills"]}}, {"$push": {"members": user_entry}})

    return {}


# Remove a bill from user bills
@app.route('/api/remove-user-bills', methods=["POST"])
@token_check
def remove_user_bills():
    username = request.json["username"]
    bill_names = request.json["bills"]

    users.update_one({"username": username}, {"$pull": {"bills": {"name": {"$in": bill_names}}}})
    bills.update_many({"name": {"$in": bill_names}}, {"$pull": {"members": {"username": username}}})

    return {}


# Update a user bill
@app.route('/api/update-user-bill', methods=["POST"])
@token_check
def update_user_bill():
    users.update_one({"username": request.json["username"], "bills.name": request.json["bill"]},
                     {"$set": {"bills.$.items": request.json["items"]}})

    return {}


# Lock a user bill
@app.route('/api/lock-user-bill', methods=["POST"])
@token_check
def lock_user_bill():
    username = request.json["username"]
    bill_name = request.json["bill"]

    bills.update_one({"name": bill_name, "members.username": username},
                     {"$set": {"members.$.locked": True}})
    users.update_one({"username": username, "bills.name": bill_name},
                     {"$set": {"bills.$.locked": True}})
    return {}


# Unlock a bill for the users
@app.route('/api/unlock-bill', methods=["POST"])
@token_check
def unlock_bill():
    usernames = request.json["users"]
    bill_name = request.json["bill"]

    users.update_many({"username": {"$in": usernames}, "bills.name": bill_name},
                      {"$set": {"bills.$.locked": False}})
    bills.update_one({"name": bill_name}, {"$set": {"members.$[elem].locked": False}},
                     array_filters=[{"elem.username": {"$in": usernames}}])
    return {}


# Get all bills and update their statuses
@app.route('/api/all-bills', methods=["GET"])
@token_check
def get_all_bills():
    all_bills = list(bills.find({}, {"_id": False, "name": True, "status": True, "members.locked": True}))
    update_bills = []
    for bill in all_bills:
        bill["members"] = [member["locked"] for member in bill["members"]]
        status = "open" if len(bill["members"]) == 0 else "ready" if all(bill["members"]) else "pending"
        if bill["status"] != "settled" and bill["status"] != status:
            bill["status"] = status
            update_bills.append((bill["name"], status))
        bill["members"] = len(bill["members"])

    if len(update_bills) != 0:
        bills.bulk_write([pymongo.UpdateOne({"name": entry[0]},
                                            {"$set": {"status": entry[1]}}) for entry in update_bills])

    return {
        "bills": all_bills
    }


# Calculate and get user and item details for a bill
@app.route('/api/manage-bill', methods=["GET"])
@token_check
def manage_bill():
    bill = request.args.get("bill")
    users_data = list(users.find({"bills.name": bill}, {"_id": False, "username": True, "bills.$": True}))
    items_data: dict[str, dict[str, list]] = {}
    bill_users = []

    for user in users_data:
        bill_users.append(user["username"])
        for item in user["bills"][0]["items"]:
            if item["name"] not in items_data:
                items_data[item["name"]] = {"name": item["name"], "users": []}
            items_data[item["name"]]["users"].append({
                "username": user["username"],
                "share": item["share"]
            })

    for item in items_data:
        sharing = {}
        specified = {}
        total_share = 0
        item_users = items_data[item]["users"]

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

    bill_data = list(bills.find({"name": bill}, {"_id": False, "items": True, "group": True}))[0]
    extra_items = [item["name"] for item in bill_data["items"]]
    for item in extra_items:
        if item not in items_data:
            items_data[item] = {
                "name": item,
                "users": []
            }

    return {
        "items": list(items_data.values()),
        "users": bill_users,
        "group": bill_data["group"]
    }


# Save bill and update amounts for users
@app.route('/api/save-bill', methods=["POST"])
@token_check
def save_bill():
    bill = request.json["bill"]
    new_users = request.json["newUsers"]
    old_users = request.json["oldUsers"]
    items_data = request.json["items"]

    bill_data = list(bills.find({"name": request.json["bill"]}, {"_id": False, "items": True}))[0]["items"]
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

    if len(new_users) != 0:
        users.bulk_write([pymongo.UpdateOne({"username": user},
                                            {"$push": {"bills": {"name": bill, "items": user_items[user]["items"],
                                                                 "amount": 0, "paid": False, "locked": True}}})
                          for user in new_users])
        bills.bulk_write([pymongo.UpdateOne({"name": bill}, {"$push": {"members": {"username": user, "locked": True}}})
                          for user in new_users])

    if len(old_users) != 0:
        users.update_many({"username": {"$in": old_users}}, {"$pull": {"bills": {"name": bill}}})
        bills.update_one({"name": bill}, {"$pull": {"members": {"username": {"$in": old_users}}}})

    users.bulk_write([pymongo.UpdateOne({"username": user, "bills.name": bill},
                                        {"$set": {"bills.$.items": user_items[user]["items"]}})
                      for user in existing_users])

    return {}


# Save bill and update amounts for users
@app.route('/api/submit-bill', methods=["POST"])
@token_check
def submit_bill():
    bill = request.json["bill"]
    bill_users = list(users.find({"bills.name": bill}, {"_id": False, "username": True, "bills.$": True}))
    user_amounts = {}

    for user in bill_users:
        user_amounts[user["username"]] = 0
        for item in user["bills"][0]["items"]:
            user_amounts[user["username"]] += item["cost"]

    bills.update_one({"name": bill}, {"$set": {"status": "settled"}})
    users.bulk_write([pymongo.UpdateOne({"username": user, "bills.name": bill},
                                        {"$set": {"bills.$.amount": round(user_amounts[user], 2)}})
                      for user in user_amounts])

    return {}


# Return users for that userGroup
@app.route('/api/users', methods=["GET"])
@token_check
def get_users():
    group = request.args["group"]
    user_list = list(db.userGroups.find({"name": {"$in": ["admin", group]}}, {"_id": False, "users": True}))
    users_list = []
    for user in user_list:
        users_list.extend(user["users"])

    return {
        "users": users_list
    }


if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)
