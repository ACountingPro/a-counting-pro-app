import streamlit as st
import os
import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import date
import io

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

st.set_page_config(page_title="A Counting Pro", page_icon="💰", layout="wide")

def get_tax_year():
    today = date.today()
    if today.month > 4 or (today.month == 4 and today.day >= 6):
        return f"{today.year}/{today.year + 1}"
    else:
        return f"{today.year - 1}/{today.year}"

def create_pdf(df, total_miles_relief, uniform_amount, lang):
    pdf = FPDF()
    pdf.add_page()
    title = "Mileage & Tax Relief Report" if lang == "EN" else "Raport Przebiegu i Ulgi Podatkowej"
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, text=f"{title} - A Counting Pro", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", size=9)
    today_str = date.today().strftime("%d/%m/%Y")
    tax_year = get_tax_year()
    line1 = f"Generated: {today_str}  |  Tax Year: {tax_year}" if lang == "EN" \
            else f"Wygenerowano: {today_str}  |  Rok podatkowy: {tax_year}"
    pdf.cell(0, 7, text=line1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    COL = [24, 30, 30, 30, 20, 26, 30]
    headers = (["Date", "From", "To", "Purpose", "Miles", "Agency(p)", "Relief(GBP)"] if lang == "EN"
               else ["Data", "Skad", "Dokad", "Cel", "Mile", "Agencja(p)", "Ulga(GBP)"])
    pdf.set_font("Helvetica", "B", 8)
    for w, h in zip(COL, headers):
        pdf.cell(w, 9, text=h, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", size=8)
    for _, row in df.iterrows():
        agency_val = "N/A" if float(row["Agency"]) == 0.0 else str(row["Agency"])
        vals = [str(row["Date"]), str(row.get("From", "")), str(row.get("To", "")),
                str(row.get("Purpose", "")), str(row["Miles"]), agency_val,
                f"{float(row['Relief']):.2f}"]
        for w, v in zip(COL, vals):
            pdf.cell(w, 9, text=v[:14], border=1)
        pdf.ln()
    pdf.ln(8)
    pdf.set_font("Helvetica", size=10)
    miles_line = (f"Total relief from miles: GBP {total_miles_relief:.2f}" if lang == "EN"
                  else f"Suma ulgi za mile: GBP {total_miles_relief:.2f}")
    pdf.cell(0, 6, text=miles_line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    final_total = total_miles_relief
    if uniform_amount > 0:
        uni_text = (f"+ GBP {uniform_amount:.2f} (Uniform Laundry Flat Rate)" if lang == "EN"
                    else f"+ GBP {uniform_amount:.2f} (Zryczaltowany koszt prania uniformu)")
        pdf.cell(0, 6, text=uni_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        final_total += uniform_amount
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    total_label = (f"TOTAL RELIEF / EXPENSE: GBP {final_total:.2f}" if lang == "EN"
                   else f"LACZNA ULGA / KOSZT: GBP {final_total:.2f}")
    pdf.cell(0, 10, text=total_label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    disclaimer = ("This report is for estimation purposes only. HMRC makes the final decision on all tax relief claims."
                  if lang == "EN" else
                  "Raport ma charakter szacunkowy. Ostateczna decyzja o przyznaniu ulgi nalezy do HMRC.")
    pdf.multi_cell(0, 6, text=disclaimer)
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 8, text="Financial health is mental wealth | linktr.ee/ACountingPro",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    return bytes(pdf.output())


if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(
        columns=["Date", "From", "To", "Purpose", "Miles", "Agency", "Relief"])

lang = st.sidebar.selectbox("Choose Language / Wybierz Jezyk", ("EN", "PL"))
EN = lang == "EN"

css = """
<style>
.stApp { background-color: #fcfaf5 !important; }
h1, h2, h3, h4 { color: #002147 !important; font-family: Georgia, serif; }
.stButton>button {
    background-color: #002147 !important; color: #D4AF37 !important;
    border-radius: 8px !important; border: 2px solid #D4AF37 !important; font-weight: bold !important;
}
.stButton>button:hover { background-color: #D4AF37 !important; color: #002147 !important; }
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    background-color: #002147 !important; color: #D4AF37 !important;
}
[data-testid="stMetricValue"] { color: #D4AF37 !important; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

_, col_m, _ = st.columns([1, 2, 1])
with col_m:
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()
    logo_found = False
    if PIL_AVAILABLE:
        for name in ["logo.png", "logo.PNG", "logo.jpg"]:
            path = os.path.join(script_dir, name)
            if os.path.exists(path):
                st.image(Image.open(path), use_container_width=True)
                logo_found = True
                break
    if not logo_found:
        st.markdown("<h1 style='text-align:center;color:#002147;'>A Counting Pro</h1>",
                    unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;color:#D4AF37;font-style:italic;'>Financial health is mental wealth</h3>",
                unsafe_allow_html=True)
    sub = "Support for Care, Cleaning & Warehouse Professionals" if EN else "Wsparcie dla Care, Cleaning i Magazynow"
    st.markdown(f"<p style='text-align:center;color:#002147;'><b>{sub}</b></p>", unsafe_allow_html=True)

st.write("---")

tab1, tab2 = st.tabs([
    "🧮 Calculator" if EN else "🧮 Kalkulator",
    "📊 Report & PDF" if EN else "📊 Raport i PDF",
])

with tab1:
    col_in, col_math = st.columns([1, 1])

    with col_in:
        emp_paye = "Agency Worker (PAYE)" if EN else "Pracownik Agencji (PAYE)"
        emp_se   = "Self-Employed (Sole Trader)" if EN else "Samozatrudniony (Self-Employed)"
        emp_status = st.radio("Employment Status" if EN else "Status zatrudnienia", [emp_paye, emp_se])
        st.write("---")

        d = st.date_input("Trip Date" if EN else "Data przejazdu", date.today())

        col_from, col_to = st.columns(2)
        with col_from:
            from_loc = st.text_input("From / Skad" if EN else "Skad", placeholder="e.g. Home / Dom")
        with col_to:
            to_loc = st.text_input("To / Dokad" if EN else "Dokad", placeholder="e.g. Client address")

        purpose = st.text_input("Purpose of trip" if EN else "Cel przejazdu",
                                placeholder="e.g. Client visit / Wizyta u klienta")

        m_raw = st.number_input("Miles (one way)" if EN else "Mile (w jedna strone)",
                                min_value=0.0, value=15.0, step=1.0)
        round_trip = st.checkbox("Round trip — multiply miles x2" if EN else "Powrot — pomnoz mile x2")
        m = m_raw * 2 if round_trip else m_raw
        if round_trip:
            st.caption(f"{'Total miles (×2)' if EN else 'Suma mil (×2)'}: **{m:.1f}**")

        is_paye = "PAYE" in emp_status
        if is_paye:
            a = st.number_input("Agency rate (p/mile)" if EN else "Stawka pracodawcy (p/mile)",
                                min_value=0.0, max_value=100.0, value=25.0, step=0.5)
            if a > 45:
                st.warning("⚠️ Agency rate above 45p — employer reimburses above HMRC limit. Relief = £0." if EN
                           else "⚠️ Stawka powyzej 45p — pracodawca zwraca powyzej limitu HMRC. Ulga = £0.")
            hmrc_total   = m * 0.45
            agency_total = m * (a / 100)
            relief = max(0.0, hmrc_total - agency_total)
        else:
            a = 0.0
            st.info("💡 As Self-Employed you deduct the full 45p per mile as a business expense." if EN
                    else "💡 Jako samozatrudniony odliczasz pelne 45p za mile jako koszt firmowy.")
            hmrc_total   = m * 0.45
            agency_total = 0.0
            relief = hmrc_total

    with col_math:
        st.write("#### 🔍 Calculation" if EN else "#### 🔍 Wyliczenia")
        st.write(f"**{'Miles counted' if EN else 'Liczba mil'}:** {m:.1f}")
        st.write(f"**{'HMRC Allowance (45p)' if EN else 'Limit HMRC (45p)'}:** £{hmrc_total:.2f}")
        if is_paye:
            st.write(f"**{'Agency Reimbursement' if EN else 'Zwrot z agencji'}:** £{agency_total:.2f}")
        st.success(f"**{'Tax Relief / Expense' if EN else 'Ulga / Koszt firmowy'}:** £{relief:.2f}")
        st.caption("ℹ️ Estimate only. HMRC makes the final decision on all tax relief claims." if EN
                   else "ℹ️ Szacunek orientacyjny. Ostateczna decyzja nalezy do HMRC.")
        st.info(f"{'Current Tax Year' if EN else 'Aktualny rok podatkowy'}: **{get_tax_year()}**")

    if st.button("➕ Add to Report" if EN else "➕ Dodaj do Raportu", use_container_width=True):
        new_row = pd.DataFrame({
            "Date": [d], "From": [from_loc], "To": [to_loc],
            "Purpose": [purpose], "Miles": [m], "Agency": [a], "Relief": [relief],
        })
        st.session_state.history = pd.concat(
            [st.session_state.history, new_row], ignore_index=True)
        st.toast("✅ Added to report!" if EN else "✅ Dodano do raportu!")

with tab2:
    st.warning(
        "⚠️ Download your PDF & CSV before closing this page — data will not be saved after you leave."
        if EN else
        "⚠️ Pobierz PDF i CSV zanim zamkniesz strone — dane nie beda dostepne po wyjsciu z aplikacji."
    )

    if not st.session_state.history.empty:
        total_m_relief = st.session_state.history["Relief"].sum()

        st.write("### 👕 Uniform & Laundry" if EN else "### 👕 Uniform i Pranie")
        add_uniform = st.checkbox("Include annual flat rate for washing uniform at home" if EN
                                  else "Dolicz roczny ryczalt za pranie firmowego uniformu w domu")
        if add_uniform:
            sector_options = {
                "Care / Cleaning (£60)":         60.0,
                "NHS Nurse / Midwife (£185)":    185.0,
                "Retail / Warehouse (£60)":      60.0,
                "Police Officer (£140)":         140.0,
                "Other / Inne (enter manually)": None,
            }
            selected = st.selectbox("Select your sector" if EN else "Wybierz swoja branze",
                                    list(sector_options.keys()))
            if sector_options[selected] is None:
                uniform_amount = st.number_input(
                    "Uniform allowance (£)" if EN else "Kwota ryczaltu (£)",
                    min_value=0.0, value=60.0, step=1.0)
            else:
                uniform_amount = sector_options[selected]
                st.info(f"{'Flat rate for this sector' if EN else 'Ryczalt dla tej branzy'}: **£{uniform_amount:.0f}**")
            st.caption("ℹ️ Only if employer does NOT reimburse laundry. No receipts needed for flat rate." if EN
                       else "ℹ️ Tylko jesli pracodawca NIE zwraca kosztow prania. Przy ryczalcie nie trzeba paragonow.")
        else:
            uniform_amount = 0.0

        final_total = total_m_relief + uniform_amount
        st.write("---")

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Miles" if EN else "Suma Mil",
                  f"{st.session_state.history['Miles'].sum():.1f}")
        c2.metric("Total Relief" if EN else "Suma Ulgi", f"£{final_total:.2f}")
        c3.metric("Tax Year" if EN else "Rok Podatkowy", get_tax_year())

        st.dataframe(st.session_state.history, use_container_width=True)
        st.write("---")

        dl1, dl2 = st.columns(2)
        with dl1:
            pdf_bytes = create_pdf(st.session_state.history, total_m_relief, uniform_amount, lang)
            st.download_button(
                label="📥 Download PDF for HMRC" if EN else "📥 Pobierz PDF dla Urzedu",
                data=pdf_bytes,
                file_name=f"HMRC_Mileage_{get_tax_year().replace('/','_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
        with dl2:
            csv_df = st.session_state.history.copy()
            csv_df["Date"] = pd.to_datetime(csv_df["Date"]).dt.strftime("%d/%m/%Y")
            csv_buffer = io.StringIO()
            csv_df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="📊 Export to Excel / CSV" if EN else "📊 Eksportuj do Excel / CSV",
                data=csv_buffer.getvalue(),
                file_name=f"HMRC_Mileage_{get_tax_year().replace('/','_')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if st.button("🗑 Clear All Data" if EN else "🗑 Wyczysc wszystkie dane"):
            st.session_state.history = pd.DataFrame(
                columns=["Date", "From", "To", "Purpose", "Miles", "Agency", "Relief"])
            st.rerun()
    else:
        st.info("No data yet. Add your trips in the Calculator tab!" if EN
                else "Brak danych. Dodaj przejazdy w zakladce Kalkulator!")

st.markdown("---")
linktree_url = "https://linktr.ee/ACountingPro"

if EN:
    st.error(
        "### 🚨 WEEKEND FLASH SALE (-50%)! Only 8 days left until Tax Year End!\n"
        "Got your report? Don't leave money at HMRC — don't pay accountants £100 for a simple form!\n\n"
        "Until **Sunday midnight only**, get our E-book for just **£9.99** (was £39.00). "
        "It shows you exactly where to click on Gov.uk to submit safely.\n\n"
        f"[👉 GRAB THE E-BOOK OR BOOK OUR VIP SERVICE]({linktree_url})"
    )
else:
    st.error(
        "### 🚨 WEEKENDOWA WYPRZEDAZ (-50%)! Zostalo tylko 8 dni do konca roku podatkowego!\n"
        "Masz raport? Nie zostawiaj pieniedzy w urzedzie i nie plac posrednikom £100!\n\n"
        "Tylko do **niedzieli o polnocy**, moj e-book za **£9.99** (zamiast £39.00). "
        "Pokazuje na zdjeciach z Gov.uk jak bezpiecznie wyslac wniosek.\n\n"
        f"[👉 KLIKNIJ — E-BOOK LUB USLUGA VIP]({linktree_url})"
    )

st.markdown(
    f"<p style='text-align:center;color:grey;'>© {date.today().year} A Counting Pro | Financial health is mental wealth</p>",
    unsafe_allow_html=True)
