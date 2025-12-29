import mysql.connector
from datetime import datetime
import os
import csv

base_dir = os.path.dirname(os.path.abspath(__file__))

while True:
    try:
        # === Ask for MySQL root password (for Database setup) ===
        mysql_password = input("Enter MySQL root password: ")

        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password=mysql_password
        )
        cursor = conn.cursor()
        print("Connected to MySQL as root.")
        break   # success → exit loop

    except KeyboardInterrupt:
        print("\nLogin cancelled by user. Exiting...")
        exit(0)

    except mysql.connector.Error as e:
        if e.errno == 1045:
            print("Wrong password. Try again.\n")
        else:
            print(f"MySQL error: {e}")
            exit(1)

# === Database and tables ===
cursor.execute("CREATE DATABASE IF NOT EXISTS inventory_db")
conn.database = "inventory_db"

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) UNIQUE,
    password VARCHAR(255) COLLATE utf8mb4_bin
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS suppliers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    supplier_name VARCHAR(255),
    supplier_phone VARCHAR(20),
    supplier_address TEXT,
    UNIQUE(user_id, supplier_name),
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    supplier_id INT,
    name VARCHAR(255),
    quantity INT,
    price DECIMAL(10,2),
    supplier_price DECIMAL(10,2),
    gst_percent DECIMAL(5,2),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
)
""")
conn.commit()

# === Users data folder ===
users_data_dir = os.path.join(base_dir, "users_data")
os.makedirs(users_data_dir, exist_ok=True)

def pause():
    input("\nPress Enter to continue...")

# === Helper functions ===
def ensure_user_folder(username: str) -> str:
    folder_path = os.path.join(users_data_dir, username)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def login_user():
    while True:
        print("\n=== LOGIN ===")
        user = input("Username: ").strip()
        pwd = input("Password: ").strip()

        try:
            # Fetch user ID from users table
            cursor.execute("SELECT id FROM users WHERE username=%s AND password=%s", (user, pwd))
            result = cursor.fetchone()
            if not result:
                print("Invalid username or password. Try again.")
                continue

            user_id = result[0]
            print("Login successful.")
            ensure_user_folder(user)
            return user, user_id

        except mysql.connector.Error:
            print(f"Database error during login.")

def signup_user():
    while True:
        print("\n=== SIGN UP ===")
        user = input("Choose username: ").strip()
        pwd = input("Choose password: ").strip()

        if not user or not pwd:
            print("Username and password cannot be empty.")
            continue

        try:
            # Insert into app users table
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                (user, pwd)
            )
            conn.commit()

            ensure_user_folder(user)
            print("Account created. You can now log in.")
            return
        except mysql.connector.Error as e:
            # 1062 / 1396 = duplicate user / already exists
            if e.errno in (1062, 1396):
                print("Username already exists. Try another.")
            else:
                print(f"MySQL error: {e}")
            continue

def add_supplier(current_user_id):
    print("\n=== ADD SUPPLIER ===")

    # Supplier Name
    name = input("Supplier Name (blank to cancel): ").strip()
    if not name:
        print("Cancelled.")
        return

    # Phone verification loop
    while True:
        phone = input("Supplier Phone No.: ").strip()
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 10:
            print("Phone number must contain at least 10 digits. Try again.")
            continue
        phone = digits
        break

    # Supplier Address
    address = input("Supplier Address: ").strip()

    try:
        cursor.execute(
            """
            INSERT INTO suppliers (user_id, supplier_name, supplier_phone, supplier_address)
            VALUES (%s, %s, %s, %s)
            """,
            (current_user_id, name, phone, address)
        )
        conn.commit()
        print("Supplier added successfully.")
    except mysql.connector.Error:
        print(f"Failed to add supplier.")

    pause()

# Allowed GST slabs as per Indian taxation rules
ALLOWED_GST_SLABS = {0.0, 0.25, 3.0, 5.0, 12.0, 18.0, 28.0, 40.0}

def add_stock(current_user_id):
    print("\n=== ADD STOCK ===")

    num_items_str = input("How many different items to add? ").strip()
    try:
        num_items = int(num_items_str)
        if num_items <= 0:
            print("Number must be positive.")
            pause()
            return
    except ValueError:
        print("Invalid number.")
        pause()
        return

    for i in range(num_items):
        print(f"\n--- Item {i + 1}/{num_items} ---")
        name = input("Item name (blank to cancel): ").strip().replace("'", "").replace('"', "")
        if not name:
            print("Skipped.")
            continue

        qty_str = input("Quantity (blank to cancel): ").strip()
        price_str = input("Price ₹ (blank to cancel): ").strip()
        if not qty_str or not price_str:
            print("Skipped.")
            continue

        try:
            qty = int(qty_str)
            price = round(float(price_str), 2)
        except ValueError:
            print("Quantity and price must be numeric. Skipping.")
            continue

        # --- GST input ---
        while True:
            gst_str = input("Choose GST % [0, 0.25, 3, 5, 12, 18, 28, 40]: ").strip()
            try:
                gst_percent = float(gst_str)
                if gst_percent not in ALLOWED_GST_SLABS:
                    print("Invalid GST %. Choose from allowed slabs only.")
                    continue
                break
            except ValueError:
                print("Invalid input. Enter a numeric GST value.")

        # --- Supplier selection (mandatory) ---
        cursor.execute("SELECT id, supplier_name FROM suppliers WHERE user_id=%s ORDER BY id ASC", (current_user_id,))
        suppliers = cursor.fetchall()

        if not suppliers:
            print("No suppliers found. Please add a supplier first.")
            pause()
            return

        print("\nSelect Supplier (mandatory):")
        for sid, sname in suppliers:
            print(f"{sid}. {sname}")

        supplier_id_str = input("Supplier ID: ").strip()
        if not supplier_id_str:
            print("Skipped. Item not added because supplier is mandatory.")
            continue  # skips this item entirely

        try:
            supplier_id = int(supplier_id_str)
        except ValueError:
            print("Invalid supplier ID. Skipping item.")
            continue

        # --- Supplier price input (mandatory) ---
        supplier_price_str = input("Supplier Price ₹ (mandatory): ").strip()
        if not supplier_price_str:
            print("Skipped. Item not added because supplier price is mandatory.")
            continue
        try:
            supplier_price = round(float(supplier_price_str), 2)
        except ValueError:
            print("Invalid price. Skipping item.")
            continue

        # --- Merge items per supplier ---
        cursor.execute(
            "SELECT id, quantity FROM inventory WHERE user_id=%s AND name=%s AND price=%s AND gst_percent=%s AND supplier_id=%s",
            (current_user_id, name, price, gst_percent, supplier_id)
        )
        existing = cursor.fetchone()
        if existing:
            item_id, existing_qty = existing
            new_qty = existing_qty + qty
            cursor.execute(
                "UPDATE inventory SET quantity=%s, supplier_price=%s WHERE id=%s",
                (new_qty, supplier_price, item_id)
            )
            action = "updated"
        else:
            cursor.execute(
                "INSERT INTO inventory (user_id, supplier_id, name, quantity, price, supplier_price, gst_percent) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (current_user_id, supplier_id, name, qty, price, supplier_price, gst_percent)
            )
            action = "added"

        conn.commit()
        print(f"Item {action} successfully: {name} x{qty} @ Rs.{price:.2f}")

    pause()

def view_stock(current_user_id, do_pause=True):
    print("\n=== VIEW STOCK ===")
    cursor.execute("""
        SELECT i.id, i.name, i.quantity, i.price, i.gst_percent, s.supplier_name, i.supplier_price
        FROM inventory i
        LEFT JOIN suppliers s ON i.supplier_id = s.id
        WHERE i.user_id=%s
    """, (current_user_id,))
    rows = cursor.fetchall()

    if not rows:
        print("No items in inventory.")
        pause()
        return

    print(f"{'ID':<5} {'Name':<15} {'Qty':>10} {'Price ₹':>15} {'GST%':>10} {'Supplier':<20} {'Supplier Price ₹':>15}")
    print("-" * 100)
    for item_id, name, qty, price, gst_percent, supplier_name, supplier_price in rows:
        supplier_name = supplier_name if supplier_name else "N/A"
        supplier_price = float(supplier_price) if supplier_price else 0.0
        gst_percent = float(gst_percent) if gst_percent else 0.0
        print(f"{item_id:<5} {name:<15} {qty:>10} {float(price):>15.2f} {gst_percent:>10.2f} {supplier_name:<20} {supplier_price:>15.2f}")

    if do_pause:
        pause()

def view_suppliers(current_user_id):
    print("\n=== SUPPLIERS ===")
    cursor.execute(
        "SELECT id, supplier_name, supplier_phone, supplier_address FROM suppliers WHERE user_id=%s",
        (current_user_id,)
    )
    rows = cursor.fetchall()
    if not rows:
        print("No suppliers yet.")
        return

    print(f"{'ID':<5} {'Name':<20} {'Phone No.':<15} {'Address'}")
    print("-"*65)
    for sid, name, phone, address in rows:
        print(f"{sid:<5} {name:<20} {phone:<15} {address}")
    pause()

def edit_item(current_user_id):
    print("\n=== EDIT ITEM ===")
    view_stock(current_user_id, False)

    item_ids_input = input("\nEnter ID('s) to edit (comma separated, blank to cancel): ").strip()
    if not item_ids_input:
        return

    try:
        item_ids = [int(x.strip()) for x in item_ids_input.split(",") if x.strip()]
    except ValueError:
        print("Invalid input. Please enter valid numeric IDs separated by commas.")
        return

    updates = []  # store all changes here

    for item_id in item_ids:
        cursor.execute(
            "SELECT name, quantity, price, gst_percent, supplier_price FROM inventory WHERE id=%s AND user_id=%s",
            (item_id, current_user_id)
        )
        item = cursor.fetchone()

        if not item:
            print(f"ID {item_id} not found. Skipping...")
            continue

        name, old_qty, old_price, old_gst, old_supplier_price = item
        print(f"\nEditing: {name} (ID: {item_id})")
        print(
            f"Current Qty: {old_qty}, Price: ₹{float(old_price):.2f}, GST%: {old_gst}, Supplier Price: ₹{float(old_supplier_price):.2f}")

        # Take new inputs (blank = keep old)
        try:
            qty_input = input("New Quantity (>=0, blank to keep): ").strip()
            price_input = input("New Price (>=0, blank to keep): ").strip()
            gst_input = input(f"New GST% {sorted(ALLOWED_GST_SLABS)} (blank to keep): ").strip()
            supplier_price_input = input("New Supplier Price (>=0, blank to keep): ").strip()

            # Determine new values
            new_qty = old_qty if qty_input == "" else int(qty_input)
            new_price = old_price if price_input == "" else float(price_input)
            new_supplier_price = old_supplier_price if supplier_price_input == "" else float(supplier_price_input)

            if gst_input == "":
                new_gst = old_gst
            else:
                new_gst = float(gst_input)
                if new_gst not in ALLOWED_GST_SLABS:
                    print(f"Invalid GST %. Skipping this item.")
                    continue

            if new_qty < 0 or new_price < 0 or new_supplier_price < 0:
                print("Negative values not allowed. Skipping this item.")
                continue

            # Skip if nothing changed
            if (new_qty, new_price, new_gst, new_supplier_price) == (old_qty, old_price, old_gst, old_supplier_price):
                print(f"No changes for '{name}'. Skipping.")
                continue

            updates.append({
                "id": item_id,
                "name": name,
                "quantity": new_qty,
                "price": new_price,
                "gst_percent": new_gst,
                "supplier_price": new_supplier_price
            })

        except ValueError:
            print("Invalid input. Skipping this item.")
            continue

    if not updates:
        print("No changes to apply.")
        return

    # Show summary before final confirmation
    print("\nSummary of changes:")
    for u in updates:
        print(
            f"ID {u['id']}: {u['name']} -> Qty: {u['quantity']}, Price: ₹{u['price']:.2f}, "
            f"GST%: {u['gst_percent']}, Supplier Price: ₹{u['supplier_price']:.2f}"
        )

    confirm = input("\nConfirm update all items (y/n): ").strip().lower()
    if confirm != 'y':
        print("Update cancelled for all items.")
        return

    # Apply updates
    for u in updates:
        cursor.execute(
            "UPDATE inventory SET quantity=%s, price=%s, gst_percent=%s, supplier_price=%s WHERE id=%s AND user_id=%s",
            (u["quantity"], u["price"], u["gst_percent"], u["supplier_price"], u["id"], current_user_id)
        )
    conn.commit()
    print("All changes applied successfully!")

def delete_item(current_user_id):
    print("\n=== DELETE ITEM ===")
    view_stock(current_user_id, False)

    item_id_str = input("\nEnter ID to delete (blank to cancel): ").strip()
    if not item_id_str:
        return

    try:
        item_id = int(item_id_str)

        # Verify exists
        cursor.execute("SELECT name FROM inventory WHERE id=%s AND user_id=%s", (item_id, current_user_id))
        item = cursor.fetchone()
        if not item:
            print(f"ID {item_id} not found.")
            pause()
            return

        confirm = input(f"Delete '{item[0]}' (y/n): ").strip().lower()
        if confirm == 'y':
            cursor.execute("DELETE FROM inventory WHERE id=%s AND user_id=%s", (item_id, current_user_id))
            conn.commit()
            print("Item deleted!")
            pause()
        else:
            print("Cancelled.")
    except ValueError:
        print("Invalid ID.")
        pause()

def generate_bill_txt(current_user, current_user_id):
    print("\n=== GENERATE BILL ===")
    view_stock(current_user_id, False)

    # ---------------- CUSTOMER DETAILS ----------------
    customer_name = input("Customer name (blank to cancel): ").strip()
    if not customer_name:
        print("Cancelled.")
        pause()
        return

    customer_phone = input("Customer Phone No. (optional): ").strip()
    customer_address = input("Customer Address (optional): ").strip()

    # ---------------- ITEM SELECTION ----------------
    item_ids_input = input("Enter item ID('s) to add to bill (blank to finish): ").strip()
    if not item_ids_input:
        print("Cancelled.")
        pause()
        return

    item_ids = [x.strip() for x in item_ids_input.split(",")]
    selected_items = []

    for item_id_str in item_ids:
        try:
            item_id = int(item_id_str)
            cursor.execute(
                "SELECT id, name, quantity, price, gst_percent, supplier_price "
                "FROM inventory WHERE id=%s AND user_id=%s",
                (item_id, current_user_id)
            )
            row = cursor.fetchone()
            if row:
                print(f"Selected: {row[1]}, Available: {row[2]}, Price: {row[3]}, GST%: {row[4]}")
                selected_items.append(row)
        except:
            continue

    if not selected_items:
        print("No valid items selected.")
        return

    # ---------------- QUANTITY ----------------
    bill_items = []

    for item_id, name, stock, price, gst_percent, supplier_price in selected_items:
        try:
            qty = int(input(f"Enter quantity for {name}: "))
            if qty <= 0 or qty > stock:
                print("Invalid quantity. Skipped.")
                continue

            base = qty * float(price)
            bill_items.append({
                "id": item_id,
                "name": name,
                "qty": qty,
                "price": float(price),
                "gst_percent": float(gst_percent),
                "supplier_price": float(supplier_price),
                "base": base
            })
        except:
            continue

    if not bill_items:
        print("Nothing to bill.")
        return

    total_base_price = sum(item["base"] for item in bill_items)
    print(f"Total Price : {total_base_price:.2f}")

    # ---------------- DISCOUNT ----------------
    while True:
        discount_str = input("Enter Discount% if any (0-100): ").strip()
        if not discount_str:
            discount_percent = 0.0
            break
        try:
            discount_percent = float(discount_str)
            if 0 <= discount_percent <= 100:
                break
            else:
                print("Discount must be between 0 and 100.")
        except ValueError:
            print("Enter a valid number for discount.")

    discount_factor = 1 - (discount_percent / 100)

    # ---------------- GST AFTER DISCOUNT ----------------
    total_gst = 0.0
    final_total = 0.0

    for item in bill_items:
        discounted_base = max(item["base"] * discount_factor, 0)
        gst_amount = max(discounted_base * (item["gst_percent"] / 100), 0)

        item["discounted_base"] = discounted_base
        item["gst_amount"] = gst_amount
        item["final"] = discounted_base + gst_amount

        total_gst += gst_amount
        final_total += item["final"]

    total_discounted_price = sum(item["discounted_base"] for item in bill_items)

    print(f"GST Amount: {total_gst:.2f}")
    print(f"Final Price (after GST%): {final_total:.2f}")

    # ---------------- UPDATE INVENTORY ----------------
    for item in bill_items:
        cursor.execute(
            "UPDATE inventory SET quantity = quantity - %s WHERE id=%s AND user_id=%s",
            (item["qty"], item["id"], current_user_id)
        )
    conn.commit()

    # ---------------- TXT BILL ----------------
    user_folder = ensure_user_folder(current_user)
    bill_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    bill_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    first_name = customer_name.strip().split()[0]
    safe_name = "".join(c for c in first_name if c.isalnum())
    txt_path = os.path.join(user_folder, f"{safe_name}_{bill_id}.txt")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("INVENTORY BILL\n")
        f.write("=" * 90 + "\n")
        f.write(f"Bill ID   : {bill_id}\n")
        f.write(f"Bill Date : {bill_date}\n")
        f.write(f"Customer Name : {customer_name}\n")
        f.write(f"Customer Phone no. : {customer_phone}\n")
        f.write(f"Customer Address : {customer_address}\n")
        f.write("=" * 90 + "\n\n")

        for item in bill_items:
            line_base = item["base"]
            f.write(
                f"{item['name']} x {item['qty']} @ Rs. {item['price']:.2f} "
                f"= Rs. {line_base:.2f} "
                f"(After discount: {item['discounted_base']:.2f}, "
                f"GST {item['gst_percent']:.1f}%: {item['gst_amount']:.2f})\n"
            )

        f.write("\n" + "=" * 90 + "\n")
        f.write(f"Total Price : Rs. {total_base_price:.2f}\n")
        f.write(f"Discount% : {discount_percent:.2f}%\n")
        f.write(f"Discounted Price : Rs. {total_discounted_price:.2f}\n")
        f.write(f"GST Amount : Rs. {total_gst:.2f}\n")
        f.write(f"Final Price (with GST) : Rs. {final_total:.2f}\n")
        f.write("=" * 90 + "\n")

    print(f"Bill saved as TXT: {safe_name}_{bill_id}.txt")

    # ---------------- CSV ----------------
    csv_path = os.path.join(user_folder, "bill_history.csv")
    exists = os.path.exists(csv_path)

    with open(csv_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not exists:
            writer.writerow([
                "Bill_ID", "Bill Date", "Customer Name", "Phone", "Address",
                "Item Name", "Quantity", "Supplier Price", "Selling Price",
                "Total Price", "Discount%", "Discounted Price",
                "GST%", "GST Amount", "Final Price (after GST)"
            ])

        for item in bill_items:
            writer.writerow([
                bill_id,
                bill_date,
                customer_name,
                customer_phone,
                customer_address,
                item["name"],
                item["qty"],
                round(item["supplier_price"], 2),
                round(item["price"], 2),
                round(item["base"], 2),
                discount_percent,
                round(item["discounted_base"], 2),
                item["gst_percent"],
                round(item["gst_amount"], 2),
                round(item["final"], 2)
            ])

    print("Bill saved to history CSV.")
    pause()

def search_customer_bills(current_user):
    print("\n=== SEARCH CUSTOMER BILLS ===")

    user_folder = ensure_user_folder(current_user)

    # Get only .txt bills (ignore csv)
    bill_files = [
        f for f in os.listdir(user_folder)
        if f.endswith(".txt")
    ]

    if not bill_files:
        print("No bills found.")
        pause()
        return

    # Sort by latest first (optional but better UX)
    bill_files.sort(reverse=True)

    print("\nAvailable Bills:")
    for idx, bill in enumerate(bill_files, start=1):
        print(f"{idx}. {bill}")

    choice = input("\nSelect bill number (blank to cancel): ").strip()
    if not choice:
        return

    try:
        choice = int(choice)
        if choice < 1 or choice > len(bill_files):
            print("Invalid selection.")
            pause()
            return

        selected_bill = bill_files[choice - 1]
        bill_path = os.path.join(user_folder, selected_bill)

        print("\n" + "=" * 90)
        with open(bill_path, "r", encoding="utf-8") as f:
            print(f.read())

    except ValueError:
        print("Please enter a valid number.")
    except Exception as e:
        print(f"Failed to open bill: {e}")

    pause()

def view_sales_history(current_user):
    print("\n=== SALES HISTORY ===")
    user_folder = ensure_user_folder(current_user)
    csv_filename = os.path.join(user_folder, "bill_history.csv")

    if not os.path.exists(csv_filename):
        print("No sales history yet.")
        pause()
        return

    total_sales = 0.0
    total_cost = 0.0
    total_gst_all = 0.0

    try:
        with open(csv_filename, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        # Group rows by Bill_ID
        bills = {}
        for row in rows:
            bills.setdefault(row["Bill_ID"], []).append(row)

        print(
            f"{'S No.':<6} {'Date':<22} {'Customer':<25} "
            f"{'Supplier Cost':>15} {'Final Price':>15} "
            f"{'Discount%':>10} {'Profit/Loss':>15}"
        )
        print("-" * 120)

        serial_no = 1

        for bill_id, items in bills.items():
            bill_date = items[0]["Bill Date"]
            customer_name = items[0]["Customer Name"]
            discount_percent = float(items[0].get("Discount%", 0) or 0)

            # Total GST for this bill
            total_gst = sum(float(i["GST Amount"] or 0) for i in items)
            total_gst_all += total_gst

            # Supplier cost
            total_supplier_cost = sum(
                float(i["Supplier Price"] or 0) * int(i["Quantity"] or 0)
                for i in items
            )

            # Final price paid by customer (Discounted Base + GST)
            final_bill_price = sum(float(i["Final Price (after GST)"] or 0) for i in items)

            # Profit = Discounted Base - Supplier Cost
            total_discounted_base = sum(float(i["Discounted Price"] or 0) for i in items)
            bill_profit = total_discounted_base - total_supplier_cost

            pl_text = f"+{bill_profit:.2f}" if bill_profit > 0 else f"-{abs(bill_profit):.2f}" if bill_profit < 0 else "0.00"

            print(
                f"{serial_no:<6} {bill_date:<22} {customer_name:<25} "
                f"{total_supplier_cost:>15.2f} {final_bill_price:>15.2f} "
                f"{discount_percent:>10.2f} {pl_text:>15}"
            )

            total_sales += final_bill_price
            total_cost += total_supplier_cost
            serial_no += 1

        # GST is excluded from profit calculation as it is payable to the government
        net = total_sales - total_cost - total_gst_all
        if net > 0:
            overall = f"Net Profit of Rs {net:.2f}"
        elif net < 0:
            overall = f"Loss of Rs {abs(net):.2f}"
        else:
            overall = "No Profit or Loss"

        print("\n" + "-" * 120)
        print(f"Total Sales : Rs {total_sales:.2f}")
        print(f"Total Cost  : Rs {total_cost:.2f}")
        print(f"Total GST   : Rs {total_gst_all:.2f}")
        print(f"Profit/Loss : {overall}")

    except Exception as e:
        print(f"Failed to load sales history: {e}")
    finally:
        pause()

def dashboard(current_user, current_user_id):
    while True:
        print("\n=== DASHBOARD ===")
        print("1. Add Supplier")
        print("2. Add Stock")
        print("3. View Stock")
        print("4. View Suppliers")
        print("5. Edit Item")
        print("6. Delete Item")
        print("7. Generate Bill")
        print("8. Search Bills")
        print("9. Sales History")
        print("10. Logout")
        print("11. Exit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            add_supplier(current_user_id)
        elif choice == "2":
            add_stock(current_user_id)
        elif choice == "3":
            view_stock(current_user_id)
        elif choice == "4":
            view_suppliers(current_user_id)
        elif choice == "5":
            edit_item(current_user_id)
        elif choice == "6":
            delete_item(current_user_id)
        elif choice == "7":
            generate_bill_txt(current_user, current_user_id)
        elif choice == "8":
            search_customer_bills(current_user)
        elif choice == "9":
            view_sales_history(current_user)
        elif choice == "10":
            print("Logging out...")
            break
        elif choice == "11":
            print("Exiting program...")
            cursor.close()
            conn.close()
            exit(0)
        else:
            print("Invalid choice.")

def main():
    while True:
        print("\n=== INVENTORY MANAGER ===")
        print("1. Login")
        print("2. Sign Up")
        print("3. Exit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            current_user, current_user_id = login_user()
            dashboard(current_user, current_user_id)
        elif choice == "2":
            signup_user()
        elif choice == "3":
            print("Exiting program...")
            cursor.close()
            conn.close()
            exit(0)
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting gracefully.")
        cursor.close()
        conn.close()