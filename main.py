import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import date

# ---------------- DATABASE ----------------
conn = sqlite3.connect("accounting.db")
conn.execute("PRAGMA foreign_keys = ON")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN
        ('Asset', 'Liability', 'Equity', 'Revenue', 'Expense'))
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    description TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    debit REAL NOT NULL DEFAULT 0,
    credit REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
)
""")
conn.commit()


# ---------------- HELPERS ----------------
def money(value):
    return f"{value:,.2f}"


def clear_tree(tree):
    for item in tree.get_children():
        tree.delete(item)


def make_tree(parent, columns, headings=None, height=12):
    tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
    for column in columns:
        tree.heading(column, text=(headings or {}).get(column, column))
        tree.column(column, width=130, anchor="center")
    tree.pack(fill="both", expand=True, padx=10, pady=8)
    return tree


def account_rows():
    cursor.execute("SELECT id, code, name, type FROM accounts ORDER BY code")
    return cursor.fetchall()


def account_balance(account_id):
    cursor.execute("""
        SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
        FROM journal_lines WHERE account_id = ?
    """, (account_id,))
    debit, credit = cursor.fetchone()
    return debit - credit


def refresh_account_choices():
    rows = account_rows()
    choices = [f"{code} - {name}" for _, code, name, _ in rows]
    journal_account_box["values"] = choices
    ledger_account_box["values"] = choices


def account_id_from_choice(choice):
    if not choice:
        return None
    code = choice.split(" - ", 1)[0]
    cursor.execute("SELECT id FROM accounts WHERE code = ?", (code,))
    row = cursor.fetchone()
    return row[0] if row else None


# ---------------- ACCOUNT FUNCTIONS ----------------
def add_account():
    code = account_code_entry.get().strip()
    name = account_name_entry.get().strip()
    account_type = account_type_box.get().strip()

    if not code or not name or not account_type:
        messagebox.showwarning("Missing information", "Please fill all account fields.")
        return

    try:
        cursor.execute(
            "INSERT INTO accounts (code, name, type) VALUES (?, ?, ?)",
            (code, name, account_type)
        )
        conn.commit()
        account_code_entry.delete(0, tk.END)
        account_name_entry.delete(0, tk.END)
        account_type_box.set("")
        refresh_all()
        messagebox.showinfo("Success", "Account added successfully.")
    except sqlite3.IntegrityError:
        messagebox.showerror("Duplicate code", "This account code already exists.")


def refresh_accounts():
    clear_tree(accounts_tree)
    for _, code, name, account_type in account_rows():
        accounts_tree.insert("", tk.END, values=(code, name, account_type))


# ---------------- JOURNAL FUNCTIONS ----------------
def add_journal_line():
    choice = journal_account_box.get().strip()
    debit_text = journal_debit_entry.get().strip()
    credit_text = journal_credit_entry.get().strip()
    account_id = account_id_from_choice(choice)

    if not account_id:
        messagebox.showwarning("Account required", "Choose an account first.")
        return

    try:
        debit = float(debit_text) if debit_text else 0.0
        credit = float(credit_text) if credit_text else 0.0
    except ValueError:
        messagebox.showerror("Invalid amount", "Debit and Credit must be numbers.")
        return

    if debit < 0 or credit < 0:
        messagebox.showerror("Invalid amount", "Amounts cannot be negative.")
        return
    if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
        messagebox.showerror(
            "Invalid line",
            "Enter an amount on either Debit or Credit, not both."
        )
        return

    journal_lines_tree.insert(
        "", tk.END,
        values=(account_id, choice, money(debit), money(credit))
    )
    journal_account_box.set("")
    journal_debit_entry.delete(0, tk.END)
    journal_credit_entry.delete(0, tk.END)
    update_journal_totals()


def remove_journal_line():
    selected = journal_lines_tree.selection()
    if not selected:
        messagebox.showwarning("Select line", "Select a journal line to remove.")
        return
    for item in selected:
        journal_lines_tree.delete(item)
    update_journal_totals()


def update_journal_totals():
    total_debit = 0.0
    total_credit = 0.0
    for item in journal_lines_tree.get_children():
        values = journal_lines_tree.item(item, "values")
        total_debit += float(values[2].replace(",", ""))
        total_credit += float(values[3].replace(",", ""))
    journal_totals_label.config(
        text=f"Total Debit: {money(total_debit)}    Total Credit: {money(total_credit)}"
    )


def save_journal_entry():
    entry_date = journal_date_entry.get().strip()
    description = journal_description_entry.get().strip()
    lines = []

    for item in journal_lines_tree.get_children():
        values = journal_lines_tree.item(item, "values")
        lines.append((int(values[0]), float(values[2].replace(",", "")),
                      float(values[3].replace(",", ""))))

    if not entry_date or not description:
        messagebox.showwarning("Missing information", "Enter date and description.")
        return
    if len(lines) < 2:
        messagebox.showwarning(
            "More lines needed", "A journal entry must contain at least two account lines."
        )
        return

    total_debit = sum(line[1] for line in lines)
    total_credit = sum(line[2] for line in lines)
    if abs(total_debit - total_credit) > 0.005:
        messagebox.showerror(
            "Entry not balanced",
            f"Debit is {money(total_debit)} but Credit is {money(total_credit)}.\n"
            "Make both totals equal before saving."
        )
        return

    try:
        cursor.execute(
            "INSERT INTO journal_entries (entry_date, description) VALUES (?, ?)",
            (entry_date, description)
        )
        entry_id = cursor.lastrowid
        cursor.executemany("""
            INSERT INTO journal_lines (entry_id, account_id, debit, credit)
            VALUES (?, ?, ?, ?)
        """, [(entry_id, account_id, debit, credit)
              for account_id, debit, credit in lines])
        conn.commit()

        journal_date_entry.delete(0, tk.END)
        journal_date_entry.insert(0, date.today().isoformat())
        journal_description_entry.delete(0, tk.END)
        clear_tree(journal_lines_tree)
        update_journal_totals()
        refresh_all()
        messagebox.showinfo("Success", "Balanced journal entry saved.")
    except sqlite3.Error as error:
        conn.rollback()
        messagebox.showerror("Database error", str(error))


def refresh_journal():
    clear_tree(journal_history_tree)
    cursor.execute("""
        SELECT e.id, e.entry_date, e.description,
               COALESCE(SUM(l.debit), 0), COALESCE(SUM(l.credit), 0)
        FROM journal_entries e
        LEFT JOIN journal_lines l ON l.entry_id = e.id
        GROUP BY e.id
        ORDER BY e.entry_date DESC, e.id DESC
    """)
    for entry_id, entry_date, description, debit, credit in cursor.fetchall():
        journal_history_tree.insert(
            "", tk.END,
            values=(entry_id, entry_date, description, money(debit), money(credit))
        )


# ---------------- LEDGER ----------------
def show_ledger():
    account_id = account_id_from_choice(ledger_account_box.get().strip())
    if not account_id:
        messagebox.showwarning("Choose account", "Choose an account to view its ledger.")
        return

    clear_tree(ledger_tree)
    cursor.execute("""
        SELECT e.entry_date, e.id, e.description, l.debit, l.credit
        FROM journal_lines l
        JOIN journal_entries e ON e.id = l.entry_id
        WHERE l.account_id = ?
        ORDER BY e.entry_date, e.id, l.id
    """, (account_id,))

    running_balance = 0.0
    for entry_date, entry_id, description, debit, credit in cursor.fetchall():
        running_balance += debit - credit
        ledger_tree.insert(
            "", tk.END,
            values=(entry_date, entry_id, description, money(debit),
                    money(credit), money(running_balance))
        )

    ledger_total_label.config(text=f"Closing balance (debit-positive): {money(running_balance)}")


# ---------------- TRIAL BALANCE ----------------
def refresh_trial_balance():
    clear_tree(trial_tree)
    total_debit = 0.0
    total_credit = 0.0

    for account_id, code, name, account_type in account_rows():
        balance = account_balance(account_id)
        debit_balance = balance if balance > 0 else 0.0
        credit_balance = -balance if balance < 0 else 0.0
        total_debit += debit_balance
        total_credit += credit_balance
        trial_tree.insert(
            "", tk.END,
            values=(code, name, account_type, money(debit_balance), money(credit_balance))
        )

    trial_totals_label.config(
        text=f"Total Debit: {money(total_debit)}    Total Credit: {money(total_credit)}"
    )


# ---------------- BALANCE SHEET ----------------
def refresh_balance_sheet():
    clear_tree(balance_sheet_tree)
    assets = liabilities = equity = revenue = expenses = 0.0

    for account_id, code, name, account_type in account_rows():
        balance = account_balance(account_id)

        # Debit-positive balance for assets/expenses; credit-positive for others.
        if account_type == "Asset":
            amount = balance
            assets += amount
        elif account_type == "Liability":
            amount = -balance
            liabilities += amount
        elif account_type == "Equity":
            amount = -balance
            equity += amount
        elif account_type == "Revenue":
            amount = -balance
            revenue += amount
        else:
            amount = balance
            expenses += amount

        balance_sheet_tree.insert(
            "", tk.END, values=(code, name, account_type, money(amount))
        )

    net_income = revenue - expenses
    total_equity = equity + net_income
    total_liabilities_equity = liabilities + total_equity
    difference = assets - total_liabilities_equity

    balance_sheet_summary.config(
        text=(
            f"Total Assets: {money(assets)}    "
            f"Total Liabilities: {money(liabilities)}    "
            f"Equity: {money(equity)}    "
            f"Net Income: {money(net_income)}\n"
            f"Liabilities + Equity: {money(total_liabilities_equity)}    "
            f"Difference (should be 0.00): {money(difference)}"
        )
    )


# ---------------- DASHBOARD / REFRESH ----------------
def refresh_dashboard():
    cursor.execute("SELECT COUNT(*) FROM accounts")
    account_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM journal_entries")
    entry_count = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM journal_lines")
    total_debit, total_credit = cursor.fetchone()

    dashboard_label.config(
        text=(
            f"Accounts: {account_count}\n"
            f"Journal Entries: {entry_count}\n"
            f"Total Posted Debit: {money(total_debit)}\n"
            f"Total Posted Credit: {money(total_credit)}"
        )
    )


def refresh_all():
    refresh_accounts()
    refresh_account_choices()
    refresh_journal()
    refresh_trial_balance()
    refresh_balance_sheet()
    refresh_dashboard()


# ---------------- MAIN WINDOW ----------------
root = tk.Tk()
root.title(" Bilal Simple Accounting Software")
root.geometry("1120x760")
root.minsize(900, 600)

style = ttk.Style()
try:
    style.theme_use("clam")
except tk.TclError:
    pass

header = ttk.Label(
    root, text="SIMPLE ACCOUNTING SOFTWARE",
    font=("Arial", 18, "bold"), anchor="center"
)
header.pack(fill="x", pady=10)

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=10, pady=5)


# Dashboard tab
dashboard_tab = ttk.Frame(notebook)
notebook.add(dashboard_tab, text="Dashboard")
ttk.Label(
    dashboard_tab, text="Accounting Overview",
    font=("Arial", 15, "bold")
).pack(pady=20)
dashboard_label = ttk.Label(
    dashboard_tab, text="", font=("Arial", 12), justify="left"
)
dashboard_label.pack(pady=15)
ttk.Button(dashboard_tab, text="Refresh Summary", command=refresh_all).pack(pady=10)


# Chart of Accounts tab
accounts_tab = ttk.Frame(notebook)
notebook.add(accounts_tab, text="Chart of Accounts")

account_form = ttk.LabelFrame(accounts_tab, text="Add New Account", padding=10)
account_form.pack(fill="x", padx=10, pady=10)

ttk.Label(account_form, text="Account Code").grid(row=0, column=0, padx=5, pady=5)
account_code_entry = ttk.Entry(account_form, width=18)
account_code_entry.grid(row=0, column=1, padx=5, pady=5)

ttk.Label(account_form, text="Account Name").grid(row=0, column=2, padx=5, pady=5)
account_name_entry = ttk.Entry(account_form, width=25)
account_name_entry.grid(row=0, column=3, padx=5, pady=5)

ttk.Label(account_form, text="Account Type").grid(row=0, column=4, padx=5, pady=5)
account_type_box = ttk.Combobox(
    account_form, values=["Asset", "Liability", "Equity", "Revenue", "Expense"],
    state="readonly", width=15
)
account_type_box.grid(row=0, column=5, padx=5, pady=5)

ttk.Button(account_form, text="Add Account", command=add_account).grid(
    row=0, column=6, padx=8, pady=5
)

accounts_tree = make_tree(
    accounts_tab, ("Code", "Name", "Type"),
    {"Code": "Account Code", "Name": "Account Name", "Type": "Account Type"}
)


# General Journal tab
journal_tab = ttk.Frame(notebook)
notebook.add(journal_tab, text="General Journal")

journal_form = ttk.LabelFrame(journal_tab, text="Journal Entry Details", padding=10)
journal_form.pack(fill="x", padx=10, pady=8)

ttk.Label(journal_form, text="Date (YYYY-MM-DD)").grid(row=0, column=0, padx=5, pady=5)
journal_date_entry = ttk.Entry(journal_form, width=16)
journal_date_entry.grid(row=0, column=1, padx=5, pady=5)
journal_date_entry.insert(0, date.today().isoformat())

ttk.Label(journal_form, text="Description").grid(row=0, column=2, padx=5, pady=5)
journal_description_entry = ttk.Entry(journal_form, width=48)
journal_description_entry.grid(row=0, column=3, padx=5, pady=5)

line_form = ttk.LabelFrame(journal_tab, text="Add Account Line", padding=8)
line_form.pack(fill="x", padx=10, pady=5)

ttk.Label(line_form, text="Account").grid(row=0, column=0, padx=5, pady=5)
journal_account_box = ttk.Combobox(line_form, state="readonly", width=28)
journal_account_box.grid(row=0, column=1, padx=5, pady=5)

ttk.Label(line_form, text="Debit").grid(row=0, column=2, padx=5, pady=5)
journal_debit_entry = ttk.Entry(line_form, width=14)
journal_debit_entry.grid(row=0, column=3, padx=5, pady=5)

ttk.Label(line_form, text="Credit").grid(row=0, column=4, padx=5, pady=5)
journal_credit_entry = ttk.Entry(line_form, width=14)
journal_credit_entry.grid(row=0, column=5, padx=5, pady=5)

ttk.Button(line_form, text="Add Line", command=add_journal_line).grid(
    row=0, column=6, padx=5, pady=5
)
ttk.Button(line_form, text="Remove Selected Line", command=remove_journal_line).grid(
    row=0, column=7, padx=5, pady=5
)

journal_lines_tree = make_tree(
    journal_tab, ("Account ID", "Account", "Debit", "Credit"),
    {"Account ID": "ID (internal)", "Account": "Account", "Debit": "Debit",
     "Credit": "Credit"}, height=5
)
journal_lines_tree.column("Account ID", width=90)
journal_totals_label = ttk.Label(journal_tab, text="Total Debit: 0.00    Total Credit: 0.00")
journal_totals_label.pack(pady=3)

ttk.Button(
    journal_tab, text="SAVE BALANCED JOURNAL ENTRY", command=save_journal_entry
).pack(pady=5)

ttk.Label(journal_tab, text="Saved Journal Entries", font=("Arial", 10, "bold")).pack(pady=3)
journal_history_tree = make_tree(
    journal_tab, ("ID", "Date", "Description", "Debit", "Credit"),
    {"ID": "Entry ID", "Date": "Date", "Description": "Description",
     "Debit": "Total Debit", "Credit": "Total Credit"}, height=5
)


# General Ledger tab
ledger_tab = ttk.Frame(notebook)
notebook.add(ledger_tab, text="General Ledger")

ledger_controls = ttk.Frame(ledger_tab)
ledger_controls.pack(fill="x", padx=10, pady=10)
ttk.Label(ledger_controls, text="Choose Account").pack(side="left", padx=5)
ledger_account_box = ttk.Combobox(ledger_controls, state="readonly", width=35)
ledger_account_box.pack(side="left", padx=5)
ttk.Button(ledger_controls, text="Show Ledger", command=show_ledger).pack(side="left", padx=5)

ledger_tree = make_tree(
    ledger_tab, ("Date", "Entry ID", "Description", "Debit", "Credit", "Balance"),
    {"Date": "Date", "Entry ID": "Entry ID", "Description": "Description",
     "Debit": "Debit", "Credit": "Credit", "Balance": "Running Balance"}
)
ledger_total_label = ttk.Label(ledger_tab, text="Closing balance (debit-positive): 0.00")
ledger_total_label.pack(pady=5)


# Trial Balance tab
trial_tab = ttk.Frame(notebook)
notebook.add(trial_tab, text="Trial Balance")

ttk.Label(trial_tab, text="Trial Balance", font=("Arial", 14, "bold")).pack(pady=8)
trial_tree = make_tree(
    trial_tab, ("Code", "Name", "Type", "Debit", "Credit"),
    {"Code": "Account Code", "Name": "Account Name", "Type": "Type",
     "Debit": "Debit Balance", "Credit": "Credit Balance"}
)
trial_totals_label = ttk.Label(trial_tab, text="Total Debit: 0.00    Total Credit: 0.00")
trial_totals_label.pack(pady=8)
ttk.Button(trial_tab, text="Refresh Trial Balance", command=refresh_trial_balance).pack(pady=5)


# Balance Sheet tab
balance_tab = ttk.Frame(notebook)
notebook.add(balance_tab, text="Balance Sheet")

ttk.Label(balance_tab, text="Balance Sheet Account Summary", font=("Arial", 14, "bold")).pack(pady=8)
balance_sheet_tree = make_tree(
    balance_tab, ("Code", "Name", "Type", "Balance"),
    {"Code": "Account Code", "Name": "Account Name", "Type": "Account Type",
     "Balance": "Balance (normal side)"}
)
balance_sheet_summary = ttk.Label(
    balance_tab, text="", justify="center", font=("Arial", 10, "bold")
)
balance_sheet_summary.pack(pady=8)
ttk.Button(balance_tab, text="Refresh Balance Sheet", command=refresh_balance_sheet).pack(pady=5)

# Initial display
refresh_all()
update_journal_totals()


def close_app():
    conn.commit()
    conn.close()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", close_app)
root.mainloop()
