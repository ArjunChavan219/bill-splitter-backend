import pymongo
from flask import Flask, request
from flask_cors import CORS


client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["billSplitterDB"]
users = db["users"]
bills = db["bills"]

app = Flask(__name__)
CORS(app)


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
    if users_dict[username] != password:
        return {
            "success": False,
            "error": "Password"
        }

    return {
        "success": True
    }


# Change password
@app.route('/api/password', methods=["POST"])
def change_password():
    print(request.json)
    username = request.json["username"]
    password = request.json["password"]
    users.update_one({"username": username}, {"$set": {"password": password}})

    return {
        "success": True
    }


# Get User Group for a user
@app.route('/api/permission', methods=["GET"])
def permission_check():
    user_groups = db["userGroups"]
    username = request.args.get("username")

    return {
        "userGroup": user_groups.find({"users": username}, {"_id": False, "name": True})[0]["name"]
    }


# Get User data
@app.route('/api/user', methods=["GET"])
def user_data():
    username = request.args.get("username")
    return users.find({"username": username}, {"_id": False, "firstName": True, "lastName": True})[0]


# Get list of all unsettled bills
@app.route('/api/bills', methods=["GET"])
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
def get_bill():
    items = list(bills.find({"name": request.args.get("bill")}, {"_id": False, "items": True}))[0]["items"]
    for item in items:
        item["cost"] = 0
        item["share"] = 0

    return {"items": items}


# Get bills for the user
@app.route('/api/user-bills', methods=["GET"])
def get_user_bills():
    return list(users.find({"username": request.args.get("username")},
                           {"_id": False, "bills.name": True, "bills.amount": True,
                            "bills.paid": True, "bills.locked": True}))[0]


# Get a bill for the user
@app.route('/api/user-bill', methods=["GET"])
def get_user_bill():
    return list(users.find({"username": request.args.get("username"), "bills.name": request.args.get("bill")},
                           {"_id": False, "bills.$": 1}))[0]["bills"][0]


# Add a bill to user bills
@app.route('/api/add-user-bills', methods=["POST"])
def add_user_bills():
    user_entry = {"username": request.json["username"], "locked": False}
    user_bills = [{"name": bill, "items": [], "amount": 0, "paid": False, "locked": False}
                  for bill in request.json["bills"]]

    users.update_one({"username": request.json["username"]}, {"$push": {"bills": {"$each": user_bills}}})
    bills.update_many({"name": {"$in": request.json["bills"]}}, {"$push": {"members": user_entry}})

    return {}


# Remove a bill from user bills
@app.route('/api/remove-user-bills', methods=["POST"])
def remove_user_bills():
    username = request.json["username"]
    bill_names = request.json["bills"]

    users.update_one({"username": username}, {"$pull": {"bills": {"name": {"$in": bill_names}}}})
    bills.update_many({"name": {"$in": bill_names}}, {"$pull": {"members": {"username": username}}})

    return {}


# Update a user bill
@app.route('/api/update-user-bill', methods=["POST"])
def update_user_bill():
    users.update_one({"username": request.json["username"], "bills.name": request.json["bill"]},
                     {"$set": {"bills.$.items": request.json["items"]}})

    return {}


# Lock a user bill
@app.route('/api/lock-user-bill', methods=["POST"])
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
                change = (1 - total_share)/len(specified)
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
                change = 1/(len(specified)+len(sharing))

                for user in item_users:
                    if user["username"] in sharing:
                        user["share"] = round(change, 2)
                    else:
                        user["share"] = round(user["share"] * change * len(specified), 2)

    extra_items = [item["name"] for item in list(bills.find({"name": bill}, {"_id": False, "items": True}))[0]["items"]]
    for item in extra_items:
        if item not in items_data:
            items_data[item] = {
                "name": item,
                "users": []
            }

    return {
        "items": list(items_data.values()),
        "users": bill_users
    }


# Save bill and update amounts for users
@app.route('/api/save-bill', methods=["POST"])
def save_bill():
    items_data = request.json["items"]
    bill_data = list(bills.find({"name": request.json["bill"]}, {"_id": False, "items": True}))[0]["items"]
    items = {item["name"]: item for item in bill_data}
    user_items = {}
    for item in items_data:
        for user in item["users"]:
            if user["username"] not in user_items:
                user_items[user["username"]] = {"items": [], "amount": 0}
            cost = round(items[item["name"]]["cost"] * user["share"], 2)
            user_items[user["username"]]["items"].append({
                "name": item["name"],
                "quantity": items[item["name"]]["quantity"],
                "type": items[item["name"]]["type"],
                "share": user["share"],
                "cost": cost
            })
            user_items[user["username"]]["amount"] += cost

    bills.update_one({"name": request.json["bill"]}, {"$set": {"status": "settled"}})
    users.bulk_write([pymongo.UpdateOne({"username": user, "bills.name": request.json["bill"]},
                                        {"$set": {"bills.$.items": user_items[user]["items"],
                                                  "bills.$.amount": round(user_items[user]["amount"])}})
                      for user in user_items])

    return {}


if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)
