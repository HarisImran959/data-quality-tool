"""
Advanced Data Quality Tool — v3.2
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

Output CSV structure:
  Raw_<ColumnName>     — original value
  Cleaned_<ColumnName> — cleaned value
  Validation_Summary   — adjacent error/warning log for each specific row

Fixes in v3.2:
  - Download no longer resets the session; results persist until user clicks Cancel
  - Validation_Summary column contains both Errors and Warnings inline per row
  - Cancel Session button explicitly clears all state and resets to upload screen
"""

import re
import io
import pandas as pd
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Data Quality Tool", page_icon="🔬", layout="wide")

# ── CSS ────────────────────────────────────────────────────────────────────────
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
.stButton > button[kind="secondary"] {
    background: white !important; color: #c00 !important;
    border: 1.5px solid #c00 !important; border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.85rem !important; padding: 0.55rem 1.5rem !important;
}
.stButton > button[kind="secondary"]:hover {
    background: #fff5f5 !important;
}
[data-testid="stDataFrame"] { border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.stTabs [data-baseweb="tab"] { font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; }
[data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e5e7eb; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — CLEANING
# ══════════════════════════════════════════════════════════════════════════════

def clean_value(value, forbidden_chars: list | None = None) -> str:
    if pd.isna(value):
        return value
    val = " ".join(str(value).split())
    if forbidden_chars:
        for ch in forbidden_chars:
            val = val.replace(ch, "")
    return val


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_type(value, dtype: str, forbidden: set | None = None) -> tuple[bool, str]:
    if pd.isna(value) or str(value).strip() == "":
        return True, ""

    val = str(value).strip()
    fb = forbidden or set()

    if dtype == "number":
        if re.match(r"^-?\d+(\.\d+)?$", val):
            return True, ""
        return False, f"[{val}] is not a valid number."

    if dtype in ("string", "alphanumeric") and fb:
        bad = sorted(set(c for c in val if c in fb))
        if bad:
            return False, f"Contains forbidden chars: {', '.join(repr(c) for c in bad)}"

    if dtype == "email":
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", val):
            return True, ""
        return False, f"[{val}] is not a valid email format."

    if dtype == "phone":
        if re.match(r"^[0-9+\-\s().]+$", val):
            return True, ""
        return False, f"[{val}] contains invalid phone characters."

    if dtype == "date":
        try:
            pd.to_datetime(val)
            return True, ""
        except Exception:
            return False, f"[{val}] is an unparseable date."

    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

SEVERITY_ORDER = {"Error": 0, "Warning": 1, "Info": 2}


@st.cache_data
def run_pipeline(df: pd.DataFrame, schema_items: tuple, global_forbidden: tuple) -> tuple:
    gfb = set(global_forbidden)
    schema = {
        col: {
            "type": dtype,
            "max_len": max_len,
            "nullable": nullable,
            "forbidden": set(list(fb_str) if fb_str else []) | gfb,
        }
        for col, dtype, max_len, nullable, fb_str in schema_items
    }

    issues = []
    out_cols = {}

    # Per-row tracker: stores dicts with severity + message
    row_entries: dict[int, list[dict]] = {i: [] for i in range(len(df))}

    for col, rules in schema.items():
        if col not in df.columns:
            continue

        fb_list = list(rules["forbidden"]) if rules["forbidden"] else None
        cleaned_values = []

        for i, raw in enumerate(df[col]):
            cleaned = clean_value(raw, fb_list)
            if rules["type"] == "email" and isinstance(cleaned, str):
                cleaned = cleaned.lower()
            cleaned_values.append(cleaned)

            row_num = i + 2  # Excel-style row number (1-indexed + header)

            # ── Null / empty check ──
            if pd.isna(raw) or str(raw).strip() == "":
                if not rules["nullable"]:
                    msg = f"Column '{col}': Required value is missing."
                    issues.append({
                        "Row": row_num, "Column": col,
                        "Value": "(empty)", "Issue": msg, "Severity": "Error",
                    })
                    row_entries[i].append({"severity": "Error", "msg": msg})
                continue

            # ── Type validation ──
            valid, type_msg = validate_type(raw, rules["type"], forbidden=rules["forbidden"])
            if not valid:
                full_msg = f"Column '{col}': {type_msg}"
                issues.append({
                    "Row": row_num, "Column": col,
                    "Value": str(raw), "Issue": full_msg, "Severity": "Error",
                })
                row_entries[i].append({"severity": "Error", "msg": full_msg})

            # ── Max length check ──
            if len(str(raw)) > rules["max_len"]:
                warn_msg = (
                    f"Column '{col}': Length {len(str(raw))} exceeds limit {rules['max_len']}."
                )
                issues.append({
                    "Row": row_num, "Column": col,
                    "Value": str(raw)[:50], "Issue": warn_msg, "Severity": "Warning",
                })
                row_entries[i].append({"severity": "Warning", "msg": warn_msg})

        out_cols[col] = cleaned_values

    # ── Build output DataFrame ──
    output_df = pd.DataFrame()
    for col in schema:
        if col not in df.columns:
            continue
        output_df[f"Raw_{col}"] = df[col].values
        output_df[f"Cleaned_{col}"] = out_cols[col]

    # ── Validation_Summary: errors first, then warnings, pipe-separated ──
    def build_summary(entries: list[dict]) -> str:
        if not entries:
            return "Pass"
        errors   = [e["msg"] for e in entries if e["severity"] == "Error"]
        warnings = [e["msg"] for e in entries if e["severity"] == "Warning"]
        parts = []
        if errors:
            parts.append("ERRORS: " + " | ".join(errors))
        if warnings:
            parts.append("WARNINGS: " + " | ".join(warnings))
        return " || ".join(parts)

    output_df["Validation_Summary"] = [
        build_summary(row_entries[idx]) for idx in range(len(df))
    ]

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
        return pd.read_csv(
            io.BytesIO(data), dtype=str, keep_default_na=False, encoding="latin1"
        )
    return pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — SESSION STATE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def reset_session():
    """Wipe all app-level session keys and trigger a clean rerun."""
    for key in ["output_df", "issues", "dup_df", "pipeline_ran", "raw_df", "file_name"]:
        st.session_state.pop(key, None)
    st.cache_data.clear()
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🔬 Data Quality Tool")
st.caption("Upload → Define rules → Run check → Download cleaned data")
st.divider()

# ── File upload (only shown when no file loaded yet in session) ──
if "raw_df" not in st.session_state:
    uploaded_file = st.file_uploader(
        "Upload CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="UTF-8 or Latin-1 CSV, or any Excel file.",
    )

    if not uploaded_file:
        st.info("👆 Upload a file to begin.")
        st.stop()

    try:
        raw_bytes = uploaded_file.read()
        df = load_file(raw_bytes, uploaded_file.name)
        st.session_state["raw_df"] = df
        st.session_state["file_name"] = uploaded_file.name
    except Exception as e:
        st.error(f"Could not read file: {e}")
        st.stop()
else:
    df = st.session_state["raw_df"]

file_name = st.session_state.get("file_name", "output.csv")

st.success(
    f"✅ Loaded **{len(df):,} rows × {len(df.columns)} columns** from `{file_name}`"
)

with st.expander("📄 Preview raw data (first 10 rows)"):
    st.dataframe(df.head(10), use_container_width=True)

st.divider()

# ── Sidebar ──
with st.sidebar:
    st.markdown("### ⚙️ Global Options")
    global_chars_raw = st.text_input(
        "Remove these characters from ALL columns",
        placeholder="e.g. * ? #",
    )
    global_forbidden = tuple(global_chars_raw.replace(" ", "")) if global_chars_raw else ()

    st.divider()
    st.markdown("### 🔍 Duplicate Detection")
    dup_cols = st.multiselect(
        "Check duplicates across columns",
        options=df.columns.tolist(),
        help="Rows sharing identical values across ALL selected columns are flagged.",
    )

    st.divider()
    # ── Cancel / Reset button lives in sidebar ──
    st.markdown("### 🔄 Session")
    if st.button("✖ Cancel & Reset Session", type="secondary", use_container_width=True):
        reset_session()

# ── Column rule builder ──
st.subheader("📋 Define Column Rules")
schema_items = []
pairs = [df.columns.tolist()[i : i + 2] for i in range(0, len(df.columns), 2)]

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
                schema_items.append(
                    (col, col_type, int(max_len), nullable, fb_input.replace(" ", ""))
                )

st.divider()

# ── Run button (always visible so user can re-run with new rules) ──
run_clicked = st.button(
    "🚀 Run Data Quality Check", type="primary", use_container_width=True
)

if run_clicked:
    with st.spinner("Cleaning and validating…"):
        output_df, issues = run_pipeline(df, tuple(schema_items), global_forbidden)
        dup_df = detect_duplicates(df, tuple(dup_cols))
    # Persist results in session state so download doesn't wipe them
    st.session_state["output_df"]    = output_df
    st.session_state["issues"]       = issues
    st.session_state["dup_df"]       = dup_df
    st.session_state["pipeline_ran"] = True

# ── Results section — rendered from session state, survives reruns ──
if st.session_state.get("pipeline_ran"):
    output_df = st.session_state["output_df"]
    issues    = st.session_state["issues"]
    dup_df    = st.session_state["dup_df"]

    # ── Summary metrics ──
    st.divider()
    st.subheader("📊 Summary")

    errors   = [i for i in issues if i["Severity"] == "Error"]
    warnings = [i for i in issues if i["Severity"] == "Warning"]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total rows",      f"{len(df):,}")
    m2.metric(
        "Errors", f"{len(errors):,}",
        delta=f"−{len(errors)}" if errors else None,
        delta_color="inverse",
    )
    m3.metric(
        "Warnings", f"{len(warnings):,}",
        delta=f"−{len(warnings)}" if warnings else None,
        delta_color="inverse",
    )
    m4.metric("Duplicate rows",  f"{len(dup_df):,}")
    m5.metric("Columns checked", f"{len(df.columns):,}")

    st.divider()

    # ── Tabs ──
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
            st.dataframe(issue_df, use_container_width=True, hide_index=True)

    # Duplicates tab
    with tab_dupes:
        if not dup_cols:
            st.info("No duplicate rule defined by the User.")
        elif dup_df.empty:
            st.success(f"🎉 No duplicates found across: {', '.join(dup_cols)}")
        else:
            st.warning(
                f"Found **{len(dup_df):,} duplicate rows** across: "
                f"`{'`, `'.join(dup_cols)}`"
            )
            st.dataframe(dup_df, use_container_width=True)

    # Raw vs Cleaned preview tab
    with tab_preview:
        st.caption(
            "Errors and Warnings are embedded in the **`Validation_Summary`** column "
            "(last column). `ERRORS:` are listed before `WARNINGS:`, separated by `||`."
        )
        st.dataframe(output_df.head(200), use_container_width=True)

    # Download tab
    with tab_download:
        st.info(
            "💡 The downloaded file contains **Raw**, **Cleaned**, and "
            "**Validation_Summary** columns in one place. "
            "Your session remains active after downloading — click "
            "**✖ Cancel & Reset Session** in the sidebar to start over."
        )
        base = file_name.rsplit(".", 1)[0]
        st.download_button(
            label="⬇️ Download Cleaned Data (with Validation Summary)",
            data=output_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{base}_cleaned_with_report.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )
