import streamlit as st
from supabase import create_client, Client
import pandas as pd
from fpdf import FPDF
from datetime import datetime
import os

# Load Supabase credentials (from Streamlit Secrets or .env for local testing)
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Invoice Generator", layout="centered")

# Session state for logged in user
if "user" not in st.session_state:
    st.session_state.user = None

# ------------- AUTH SECTION -------------
def login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])

    if st.button(action):
        try:
            if action == "Login":
                user = supabase.auth.sign_in_with_password({"email": email, "password": password})
            else:
                user = supabase.auth.sign_up({"email": email, "password": password})
            st.session_state.user = user.user
            st.success(f"{action} successful!")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Error: {e}")

if not st.session_state.user:
    login()
    st.stop()

# ------------- MAIN APP -------------
st.sidebar.title(f"Welcome, {st.session_state.user.email}")
if st.sidebar.button("Log out"):
    supabase.auth.sign_out()
    st.session_state.user = None
    st.experimental_rerun()

st.title("Invoice Entry System")

# --- Form to log time/materials ---
with st.form("entry_form"):
    client = st.text_input("Client Name", placeholder="e.g., ACME Corp")
    date = st.date_input("Date")
    description = st.text_area("Work Description")
    hours = st.number_input("Hours Worked", min_value=0.0, step=0.25)
    rate = st.number_input("Hourly Rate (€)", min_value=0.0, step=1.0)
    materials = st.text_input("Materials Used")
    material_cost = st.number_input("Material Cost (€)", min_value=0.0, step=1.0)
    submit = st.form_submit_button("Add Entry")

if submit:
    supabase.table("entries").insert({
        "user_id": st.session_state.user.id,
        "client": client,
        "date": date.isoformat(),
        "description": description,
        "hours": hours,
        "rate": rate,
        "materials": materials,
        "material_cost": material_cost,
        "billed": False
    }).execute()
    st.success("Entry added successfully!")

# --- Show unbilled entries ---
st.subheader("Unbilled Entries")
entries_resp = supabase.table("entries").select("*").eq("user_id", st.session_state.user.id).eq("billed", False).execute()
entries = pd.DataFrame(entries_resp.data)

if not entries.empty:
    st.dataframe(entries)

    if st.button("Generate Invoices"):
        # Group by client and generate PDFs
        grouped = entries.groupby("client")
        pdf_links = []

        for client_name, group in grouped:
            invoice_num = f"INV-{datetime.today().strftime('%Y%m%d')}-{client_name[:3].upper()}"
            total_hours = (group["hours"] * group["rate"]).sum()
            total_materials = group["material_cost"].sum()
            total = total_hours + total_materials

            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt=f"INVOICE for {client_name}", ln=True, align='C')
            pdf.cell(200, 10, txt=f"Invoice #: {invoice_num}", ln=True)
            pdf.cell(200, 10, txt=f"Date: {datetime.today().strftime('%Y-%m-%d')}", ln=True)
            pdf.ln(10)

            for _, row in group.iterrows():
                line = f"{row['date']} | {row['description']} | {row['hours']}h @ €{row['rate']}/h | Materials: {row['materials']} (€{row['material_cost']})"
                pdf.multi_cell(0, 10, txt=line)

            pdf.ln(10)
            pdf.cell(200, 10, txt=f"Total Labor: €{total_hours:.2f}", ln=True)
            pdf.cell(200, 10, txt=f"Total Materials: €{total_materials:.2f}", ln=True)
            pdf.cell(200, 10, txt=f"TOTAL: €{total:.2f}", ln=True)

            filename = f"{client_name.replace(' ', '_')}_{invoice_num}.pdf"
            pdf.output(filename)
            pdf_links.append(filename)

        # Mark entries as billed
        ids = entries["id"].tolist()
        for id_ in ids:
            supabase.table("entries").update({"billed": True}).eq("id", id_).execute()

        # Show download buttons
        st.success("Invoices generated!")
        for f in pdf_links:
            with open(f, "rb") as file:
                st.download_button(f"Download {f}", data=file, file_name=f, mime="application/pdf")
else:
    st.info("No unbilled entries yet.")
