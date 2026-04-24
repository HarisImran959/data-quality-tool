"""
Advanced Data Quality Tool — v3
================================
Cleaning functions applied per column type:
  - ALL columns : strip leading/trailing whitespace, collapse multiple spaces,
                  remove any user-defined forbidden characters
  - number      : must match digits / decimal / negative sign only
  - alphanumeric: accepts everything unless user explicitly defines forbidden chars
  - email       : must contain exactly one '@' and a dotted domain
  - phone       : must contain only digits, spaces, +, -, (, )
  - date        : must be parseable by pandas
  - string      : accepts everything unless user explicitly defines forbidden chars

Output CSV structure per original column:
  Raw_<ColumnName>     — original value from uploaded file (never modified)
  Cleaned_<ColumnName> — value after all cleaning rules are applied
"""

import re
import io
import pandas as pd
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Data Quality Tool", page_icon="🔬", layout="wide")

# ── Minimal CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
.stApp { background-color: #f7f8fa; }
h1 {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 1.7rem !important; letter-spacing: -0.03em !important;
    color: #111 !important; border-bottom: 3px solid #111;
    padding-bottom: 10px; margin-bottom: 0 !important;
}
h2, h3 {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #111 !important; font-size: 1rem !important;
}
[data-testid="metric-container"] {
    background: white; border: 1px solid #e0e0e0;
    border-radius: 8px; padding: 16px !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem !important;
    color: #666 !important; text-transform: uppercase; letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', monospace; font-size: 1.8rem !important; color: #111 !important;
}
.stButton > button[kind="primary"] {
    background: #111 !important; color: white !important;
    border: none !important; border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.85rem !important; padding: 0.55rem 1.5rem !important;
}
.stButton > button[kind="primary"]:hover { background: #333 !important; }
[data-testid="stDataFrame"] { border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.stTabs [data-baseweb="tab"] { font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; }
[data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e5e7eb; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — CLEANING
#  Applied to every cell before validation runs.
# ══════════════════════════════════════════════════════════════════════════════

def clean_value(value, forbidden_chars: list | None = None) -> str:
    """
    Universal cell cleaner (runs on all column types):
      1. Strip leading/trailing whitespace
      2. Collapse multiple internal spaces into one
      3. Remove any characters the user explicitly listed as forbidden
    Returns the original value unchanged if it is null/NaN.
    """
    if pd.isna(value):
        return value
    val = " ".join(str(value).split())          # strip + collapse spaces in one step
    if forbidden_chars:
        for ch in forbidden_chars:
            val = val.replace(ch, "")
    return val


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — VALIDATION
#  Each dtype check returns (is_valid: bool, plain-English explanation: str).
#  "string" and "alphanumeric" only flag characters the USER defined as forbidden.
# ══════════════════════════════════════════════════════════════════════════════

def validate_type(value, dtype: str, forbidden: set | None = None) -> tuple[bool, str]:
    """
    Validate a cleaned cell value against the declared column type.

    Parameters
    ----------
    value    : raw cell value (pre-clean)
    dtype    : one of number | alphanumeric | email | phone | date | string
    forbidden: set of characters the user marked as not allowed (may be empty)

    Returns (True, "") if valid, or (False, human-readable message) if not.
    """
    if pd.isna(value) or str(value).strip() == "":
        return True, ""     # empty cells are handled by the nullable check

    val     = str(value).strip()
    fb      = forbidden or set()

    if dtype == "number":
        if re.match(r"^-?\d+(\.\d+)?$", val):
            return True, ""
        bad = sorted(set(c for c in val if not c.isdigit() and c not in ".-"))
        detail = f" It contains {', '.join(repr(c) for c in bad)} which are not allowed." if bad else ""
        return False, (
            f"[{val}] is not a valid number.{detail} "
            "Numbers should contain digits only — e.g. 42 or 3.14"
        )

    if dtype in ("string", "alphanumeric"):
        # Nothing is forbidden unless the user explicitly said so
        if not fb:
            return True, ""
        bad = sorted(set(c for c in val if c in fb))
        if not bad:
            return True, ""
        return False, (
            f"[{val}] contains {', '.join(repr(c) for c in bad)} "
            "which you marked as not allowed. Please remove those character(s)."
        )

    if dtype == "email":
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", val):
            return True, ""
        if "@" not in val:
            reason = "it is missing the '@' symbol"
        elif val.count("@") > 1:
            reason = f"it has {val.count('@')} '@' symbols — only one is allowed"
        elif "." not in val.split("@")[-1]:
            reason = f"the domain '{val.split('@')[-1]}' is missing a dot (e.g. .com)"
        else:
            reason = "it does not match a valid email pattern"
        return False, f"[{val}] is not a valid email — {reason}. Example: name@example.com"

    if dtype == "phone":
        if re.match(r"^[0-9+\-\s().]+$", val):
            return True, ""
        bad = sorted(set(c for c in val if not re.match(r"[0-9+\-\s().]", c)))
        return False, (
            f"[{val}] is not a valid phone number — "
            f"it contains {', '.join(repr(c) for c in bad)} which are not allowed. "
            "Phone numbers may only contain digits, spaces, +, -, ( or )"
        )

    if dtype == "date":
        try:
            pd.to_datetime(val)
            return True, ""
        except Exception:
            return False, (
                f"[{val}] could not be read as a date. "
                "Use a standard format like YYYY-MM-DD (e.g. 2024-01-31) "
                "or DD/MM/YYYY (e.g. 31/01/2024)."
            )

    return True, ""     # unknown dtype — pass through


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — PIPELINE
#  Runs cleaning + validation and builds the output DataFrame.
#  Output columns: Raw_<col> (original) and Cleaned_<col> (after cleaning).
# ══════════════════════════════════════════════════════════════════════════════

SEVERITY_ORDER = {"Error": 0, "Warning": 1, "Info": 2}


@st.cache_data
def run_pipeline(df: pd.DataFrame, schema_items: tuple, global_forbidden: tuple) -> tuple:
    """
    For every column defined in schema_items:
      - Clean the value (strip, collapse spaces, remove forbidden chars)
      - Validate the cleaned value against the declared type
      - Record issues with plain-English descriptions

    Output DataFrame columns per original column:
      Raw_<col>     — untouched original value
      Cleaned_<col> — value after cleaning

    Returns (output_df, issues_list).
    Cached by Streamlit so repeated button clicks are instant.
    """
    gfb = set(global_forbidden)

    # Build schema dict from hashable tuple
    schema = {
        col: {
            "type":     dtype,
            "max_len":  max_len,
            "nullable": nullable,
            "forbidden": set(list(fb_str) if fb_str else []) | gfb,
        }
        for col, dtype, max_len, nullable, fb_str in schema_items
    }

    issues    = []
    out_cols  = {}      # column_name → list of cleaned values

    for col, rules in schema.items():
        if col not in df.columns:
            continue

        fb       = rules["forbidden"]
        fb_list  = list(fb) if fb else None
        cleaned_values = []

        for i, raw in enumerate(df[col]):
            cleaned = clean_value(raw, fb_list)
            # Type-specific post-clean: lowercase emails (case-insensitive by standard)
            if rules["type"] == "email" and isinstance(cleaned, str):
                cleaned = cleaned.lower()
            cleaned_values.append(cleaned)
            row_num = i + 2     # 1-based + skip header row

            # ── Null / empty check ────────────────────────────────────────
            if pd.isna(raw) or str(raw).strip() == "":
                if not rules["nullable"]:
                    issues.append({
                        "Row": row_num, "Column": col, "Value": "(empty)",
                        "Issue": "This cell is empty but the column requires a value — please fill it in.",
                        "Severity": "Error",
                    })
                continue

            # ── Type validation ────────────────────────────────────────────
            valid, msg = validate_type(raw, rules["type"], forbidden=fb)
            if not valid:
                issues.append({
                    "Row": row_num, "Column": col, "Value": str(raw),
                    "Issue": msg, "Severity": "Error",
                })

            # ── Max length check ───────────────────────────────────────────
            if len(str(raw)) > rules["max_len"]:
                issues.append({
                    "Row": row_num, "Column": col, "Value": str(raw)[:50],
                    "Issue": (
                        f"This value is {len(str(raw))} characters long but the "
                        f"maximum allowed is {rules['max_len']}. Please shorten it."
                    ),
                    "Severity": "Warning",
                })

        out_cols[col] = cleaned_values

    # Build output DataFrame: Raw_<col> then Cleaned_<col> for every column
    output_df = pd.DataFrame()
    for col in schema:
        if col not in df.columns:
            continue
        output_df[f"Raw_{col}"]     = df[col].values
        output_df[f"Cleaned_{col}"] = out_cols[col]

    issues.sort(key=lambda x: (SEVERITY_ORDER.get(x["Severity"], 9), x["Row"]))
    return output_df, issues


@st.cache_data
def detect_duplicates(df: pd.DataFrame, columns: tuple) -> pd.DataFrame:
    if not columns:
        return pd.DataFrame()
    return df[df.duplicated(subset=list(columns), keep=False)].copy()


@st.cache_data
def load_file(data: bytes, name: str) -> pd.DataFrame:
    if name.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="latin1")
    return pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🔬 Advanced Data Quality Tool")
st.caption("Upload → Define rules → Run check → Download cleaned data")
st.divider()

# ── File upload ────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "Upload CSV or Excel file", type=["csv", "xlsx", "xls"],
    help="UTF-8 or Latin-1 CSV, or any Excel file.",
)

if not uploaded_file:
    st.info("👆 Upload a file to begin.")
    st.stop()

try:
    df = load_file(uploaded_file.read(), uploaded_file.name)
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

st.success(f"✅ Loaded **{len(df):,} rows × {len(df.columns)} columns** from `{uploaded_file.name}`")

with st.expander("📄 Preview raw data (first 10 rows)"):
    st.dataframe(df.head(10), use_container_width=True)

st.divider()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Global Options")
    global_chars_raw = st.text_input(
        "Remove these characters from ALL columns",
        placeholder="e.g. * ? #",
        help="Every character listed is stripped from every cell before validation.",
    )
    global_forbidden = tuple(global_chars_raw.replace(" ", "")) if global_chars_raw else ()

    st.divider()
    st.markdown("### 🔍 Duplicate Detection")
    dup_cols = st.multiselect(
        "Check duplicates across columns", options=df.columns.tolist(),
        help="Rows sharing identical values across ALL selected columns are flagged.",
    )

    st.divider()
    st.markdown("### 📘 Type Reference")
    st.markdown(
        "| Type | What is accepted |\n|---|---|\n"
        "| `string` | Any text |\n"
        "| `number` | Digits, decimal, negative |\n"
        "| `alphanumeric` | Any text* |\n"
        "| `email` | name@domain.com |\n"
        "| `phone` | Digits + `+`,`-`,`(`,`)` |\n"
        "| `date` | Any standard date format |\n\n"
        "_*Only flags characters you explicitly forbid_"
    )

# ── Column rule builder ────────────────────────────────────────────────────────
st.subheader("📋 Define Column Rules")
st.caption("Set the type, max length, and nullable setting for each column.")

schema_items = []
pairs = [df.columns.tolist()[i:i+2] for i in range(0, len(df.columns), 2)]

for pair in pairs:
    ui_cols = st.columns(len(pair))
    for ui_col, col in zip(ui_cols, pair):
        with ui_col:
            with st.container(border=True):
                st.markdown(f"**`{col}`**")
                col_type = st.selectbox(
                    "Type",
                    ["string", "number", "alphanumeric", "email", "phone", "date"],
                    key=f"type_{col}",
                )
                c1, c2 = st.columns(2)
                max_len  = c1.number_input("Max length", min_value=1, value=100, key=f"len_{col}")
                nullable = c2.checkbox("Allow NULL", value=True, key=f"null_{col}")
                fb_input = st.text_input("Forbidden chars", placeholder="e.g. $ %", key=f"fb_{col}")
                schema_items.append((
                    col, col_type, int(max_len), nullable,
                    fb_input.replace(" ", ""),
                ))

st.divider()

# ── Run ────────────────────────────────────────────────────────────────────────
if not st.button("🚀 Run Data Quality Check", type="primary", use_container_width=True):
    st.stop()

with st.spinner("Cleaning and validating…"):
    output_df, issues = run_pipeline(df, tuple(schema_items), global_forbidden)
    dup_df = detect_duplicates(df, tuple(dup_cols))

# ── Summary metrics ────────────────────────────────────────────────────────────
st.divider()
st.subheader("📊 Summary")

errors   = [i for i in issues if i["Severity"] == "Error"]
warnings = [i for i in issues if i["Severity"] == "Warning"]

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total rows",       f"{len(df):,}")
m2.metric("Errors",           f"{len(errors):,}",
          delta=f"−{len(errors)}"   if errors   else None, delta_color="inverse")
m3.metric("Warnings",         f"{len(warnings):,}",
          delta=f"−{len(warnings)}" if warnings else None, delta_color="inverse")
m4.metric("Duplicate rows",   f"{len(dup_df):,}",
          delta=f"−{len(dup_df)}"   if not dup_df.empty else None, delta_color="inverse")
m5.metric("Columns checked",  f"{len(df.columns):,}")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_issues, tab_dupes, tab_preview, tab_download = st.tabs([
    f"⚠️ Issues ({len(issues)})",
    f"🔁 Duplicates ({len(dup_df)})",
    "🔀 Raw vs Cleaned",
    "⬇️ Download",
])

# Issues tab
with tab_issues:
    if not issues:
        st.success("🎉 No issues found — data looks clean!")
    else:
        issue_df = pd.DataFrame(issues)
        f1, f2, f3 = st.columns(3)
        sev_filter = f1.multiselect(
            "Severity", ["Error", "Warning", "Info"],
            default=["Error", "Warning", "Info"],
        )
        col_filter = f2.multiselect("Column", df.columns.tolist())
        search     = f3.text_input("Search", placeholder="e.g. @, empty…")

        filtered = issue_df[issue_df["Severity"].isin(sev_filter)]
        if col_filter:
            filtered = filtered[filtered["Column"].isin(col_filter)]
        if search:
            mask = (
                filtered["Value"].str.contains(search, case=False, na=False) |
                filtered["Issue"].str.contains(search, case=False, na=False)
            )
            filtered = filtered[mask]

        st.caption(f"Showing {len(filtered):,} of {len(issue_df):,} issues")

        def style_severity(val):
            colour = {"Error": ("#fff0f0", "#c0392b"),
                      "Warning": ("#fffbea", "#b7770d"),
                      "Info":    ("#eef4ff", "#2563eb")}.get(val, ("", ""))
            return f"background-color:{colour[0]};color:{colour[1]};font-weight:600;font-family:monospace"

        st.dataframe(
            filtered.style.map(style_severity, subset=["Severity"]),
            use_container_width=True, hide_index=True,
        )

        with st.expander("📈 Breakdown by column"):
            st.dataframe(
                issue_df.groupby(["Column", "Severity"]).size()
                        .reset_index(name="Count")
                        .sort_values(["Column", "Severity"]),
                use_container_width=True, hide_index=True,
            )

# Duplicates tab
with tab_dupes:
    if dup_df.empty:
        msg = "Select columns in the sidebar to enable duplicate detection." if not dup_cols \
              else f"🎉 No duplicates found across: {', '.join(dup_cols)}"
        st.info(msg) if not dup_cols else st.success(msg)
    else:
        st.warning(f"Found **{len(dup_df):,} duplicate rows** across: `{'`, `'.join(dup_cols)}`")
        st.dataframe(dup_df, use_container_width=True)

# Raw vs Cleaned preview tab
with tab_preview:
    # Count how many cells actually changed
    changed_count = sum(
        1
        for col in df.columns
        for raw, cln in zip(
            output_df[f"Raw_{col}"].astype(str),
            output_df[f"Cleaned_{col}"].astype(str),
        )
        if raw != cln
    )
    st.caption(f"**{changed_count:,} cell(s)** changed by cleaning.  Green = modified.")

    def highlight_cleaned(row):
        """Highlight Cleaned_ cells that differ from their Raw_ counterpart."""
        styles = [""] * len(row)
        for j, col_name in enumerate(row.index):
            if col_name.startswith("Cleaned_"):
                raw_col = "Raw_" + col_name[len("Cleaned_"):]
                if raw_col in row.index and row[col_name] != row[raw_col]:
                    styles[j] = "background-color:#d4edda;color:#155724;font-weight:600"
        return styles

    st.dataframe(
        output_df.head(200).style.apply(highlight_cleaned, axis=1),
        use_container_width=True,
    )
    if len(output_df) > 200:
        st.caption(f"Showing first 200 of {len(output_df):,} rows.")

# Download tab
with tab_download:
    base = uploaded_file.name.rsplit(".", 1)[0]
    d1, d2 = st.columns(2)

    with d1:
        st.markdown("**Full output file**")
        st.caption(
            "Contains `Raw_<column>` (original) and `Cleaned_<column>` "
            "(after cleaning) for every column."
        )
        st.download_button(
            "⬇️ Download cleaned CSV",
            data=output_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{base}_cleaned.csv",
            mime="text/csv", type="primary", use_container_width=True,
        )

    with d2:
        st.markdown("**Issues report**")
        st.caption(f"{len(issues)} issue(s) logged during validation.")
        if issues:
            st.download_button(
                "⬇️ Download issues CSV",
                data=pd.DataFrame(issues).to_csv(index=False).encode("utf-8"),
                file_name=f"{base}_issues.csv",
                mime="text/csv", use_container_width=True,
            )
        else:
            st.success("No issues to export 🎉")