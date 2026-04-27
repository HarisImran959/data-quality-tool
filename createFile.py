import pandas as pd
import random
import string

rows = 200

names = ["Ali Khan", "Sara Ahmed", "John Doe", "Fatima Noor", "Usman Tariq", "Ayesha Malik", "", None]
domains = ["gmail.com", "yahoo.com", "outlook.com", "invalid", ""]
orders = ["Order#123", "ORD-456", "789", "", "OrderXYZ", None]

def random_phone():
    return random.choice([
        "03001234567",
        "+92-300-1234567",
        "3001234567",
        "invalid",
        "",
        None
    ])

def random_email(name):
    if not name or random.random() < 0.25:
        return random.choice(["invalid_email", "test@", "@domain.com", ""])
    return name.lower().replace(" ", ".") + "@" + random.choice(domains)

def random_desc():
    if random.random() < 0.2:
        return "".join(random.choices(string.ascii_letters + " ", k=1100))  # too long
    return random.choice([
        "Short desc",
        "   Leading spaces",
        "Trailing spaces   ",
        "",
        None
    ])

data = []

for i in range(rows):
    name = random.choice(names)
    email = random_email(name)
    phone = random_phone()
    
    # 90% IDs filled but duplicates exist
    if random.random() < 0.9:
        id_val = random.choice([f"ID{i}", f"ID{random.randint(0,50)}"])
    else:
        id_val = random.choice(["", None, " "])
    
    order = random.choice(orders)
    desc = random_desc()
    
    row = {
        "Name": name,
        "Email": email,
        "Phone Number": phone,
        "ID": id_val,
        "Order Details": order,
        "Description": desc
    }
    
    # Column contamination (real-world issue)
    if random.random() < 0.15:
        row["Email"], row["Phone Number"] = row["Phone Number"], row["Email"]
    
    data.append(row)

df = pd.DataFrame(data)
df.to_csv("messy_200_rows.csv", index=False)

print("File created: messy_200_rows.csv")