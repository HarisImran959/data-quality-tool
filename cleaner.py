import streamlit as st
import pandas as pd
import re

st.title("Advanced Data Quality Tool")

# -----------------------------
# Upload File
# -----------------------------
uploaded_file = st.file_uploader("Upload CSV or Excel file")

# -----------------------------
# CLEAN FUNCTION
# -----------------------------
def clean_value(value, remove_chars=None):
    if pd.isna(value):
        return value

    value = str(value).strip()
    value = " ".join(value.split())

    if remove_chars:
        for ch in remove_chars:
            value = value.replace(ch, "")

    return value

# -----------------------------
# TYPE VALIDATION
# -----------------------------
def validate_type(value, dtype):

    if pd.isna(value):
        return True

    val = str(value)

    if dtype == "number":
        return val.isdigit()

    elif dtype == "alphanumeric":
        return val.isalnum()

    elif dtype == "email":
        return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", val))

    elif dtype == "phone":
        return bool(re.match(r"^[0-9+\- ]+$", val))

    elif dtype == "date":
        try:
            pd.to_datetime(val)
            return True
        except:
            return False

    elif dtype == "string":
        return True

    return True

# -----------------------------
# VALIDATION ENGINE
# -----------------------------
def validate_data(df, schema, global_remove_chars=None):

    issues = []
    cleaned_df = df.copy()

    for col, rules in schema.items():

        if col not in df.columns:
            continue

        remove_chars = rules.get("remove_chars", global_remove_chars)

        for i, value in df[col].items():

            cleaned_value = clean_value(value, remove_chars)
            cleaned_df.at[i, col] = cleaned_value

            if pd.isna(value):
                if not rules.get("nullable", True):
                    issues.append([i, col, value, "Null Not Allowed"])
                continue

            if not validate_type(value, rules["type"]):
                issues.append([i, col, value, f"Invalid {rules['type']}"])

            if "max_length" in rules:
                if len(str(value)) > rules["max_length"]:
                    issues.append([i, col, value, "Max Length Exceeded"])

    return cleaned_df, issues

# -----------------------------
# DUPLICATE DETECTION
# -----------------------------
def detect_duplicates(df, columns):
    if not columns:
        return pd.DataFrame()

    return df[df.duplicated(subset=columns, keep=False)]

# -----------------------------
# MAIN APP LOGIC
# -----------------------------
if not uploaded_file:
    st.info("Upload a file to begin")
else:

    # Read file
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, encoding="latin1")
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("Raw Data")
    st.dataframe(df)

    st.subheader("Global Cleaning Rule")
    global_chars = st.text_input("Characters to remove from ALL columns (e.g. *,-,?)")
    global_chars = list(global_chars) if global_chars else None

    st.subheader("Define Column Rules")

    schema = {}

    for col in df.columns:

        st.markdown(f"### {col}")

        col_type = st.selectbox(
            f"Type",
            ["string", "number", "alphanumeric", "email", "phone", "date"],
            key=f"type_{col}"
        )

        max_length = st.number_input(
            f"Max Length",
            min_value=1,
            value=50,
            key=f"len_{col}"
        )

        nullable = st.checkbox(
            f"Allow NULL",
            value=True,
            key=f"null_{col}"
        )

        remove_chars = st.text_input(
            f"Remove specific characters (optional)",
            key=f"char_{col}"
        )

        schema[col] = {
            "type": col_type,
            "max_length": max_length,
            "nullable": nullable,
            "remove_chars": list(remove_chars) if remove_chars else None
        }

    st.subheader("Duplicate Detection")

    dup_cols = st.multiselect(
        "Select columns to check duplicates",
        df.columns.tolist()
    )

    if st.button("Run Data Quality Check"):

        cleaned_df, issues = validate_data(df, schema, global_chars)

        st.subheader("Issues Found")

        if issues:
            issue_df = pd.DataFrame(
                issues,
                columns=["Row", "Column", "Value", "Issue"]
            )
            st.dataframe(issue_df)
        else:
            st.success("No issues found 🎉")

        st.subheader("Duplicates")

        dup_df = detect_duplicates(df, dup_cols)
        if not dup_df.empty:
            st.dataframe(dup_df)
        else:
            st.success("No duplicates found")

        st.subheader("Raw vs Cleaned Comparison")

        comparison_df = pd.DataFrame()

        for col in df.columns:
            comparison_df[col + " (Raw)"] = df[col]
            comparison_df[col + " (Cleaned)"] = cleaned_df[col]

        st.dataframe(comparison_df)