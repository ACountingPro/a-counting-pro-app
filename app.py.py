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
    return f"{today.year - 1}/{today.year}"

def create_pdf(df, total_expense, uniform_amount, lang):
    pdf = FPDF()
    pdf.add_page()

    title = "Mileage & Tax Relief Report" if lang == "EN" else "Raport Przebiegu i Kosztow"
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, text=f"{title} - A Counting Pro", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=9)
    today_str = date.today().strftime("%d/%m/%Y")
    tax_year = get_tax_year()
    line1 = (
        f"Generated: {today_str}  |  Tax Year: {tax_year}"
        if lang == "EN"
        else f"Wygenerowano: {today_str}  |  Rok podatkowy: {tax_year}"
    )
    pdf.cell(0, 7, text=line1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    col_widths = [24, 30, 30, 30, 20, 26, 30]
    headers = (
        ["Date", "From", "To", "Purpose", "Miles", "Agency(p)", "Expense(GBP)"]
        if lang == "EN"
        else ["Data", "Skad", "Dokad", "Cel", "Mile", "Agencja(p)", "Koszt(GBP)"]
    )

    pdf.set_font("Helvetica", "B", 8)
    for w, h in zip(col_widths, headers):
        pdf.cell(w, 9, text=h, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", size=8)
    for _, row in df.iterrows():
        agency_val = "N/A" if float(row["Agency"]) == 0.0 else str(row["Agency"])
        vals = [
            str(row["Date"]),
            str(row.get("From", "")),
            str(row.get("To", "")),
            str(row.get("Purpose", "")),
            str(row["Miles"]),
            agency_val,
            f"{float(row['Expense']):.2f}",
        ]
        for w, v in zip(col_widths, vals):
            pdf.cell(w, 9, text=v[:14], border=1)
        pdf.ln()

    pdf.ln(8)
    pdf.set_font("Helvetica", size=10)
    
    # --- GOTOWE SUMY DLA GOV.UK ---
    total_miles_pdf = df["Miles"].astype(float).sum()
    total_agency_paid = (df["Miles"].astype(float) * (df["Agency"].astype(float) / 100)).sum()
    
    if lang == "EN":
        pdf.cell(0, 6, text=f"Total business miles (enter on Gov.uk): {total_miles_pdf:.1f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=f"Mileage allowance paid by employer (enter on Gov.uk): GBP {total_agency_paid:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        pdf.set_font("Helvetica", size=10)
        miles_line = f"Total allowable expense from miles: GBP {total_expense:.2f}"
    else:
        pdf.cell(0, 6, text=f"Calkowita suma mil (wpisz to na Gov.uk): {total_miles_pdf:.1f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=f"Kwota zwrocona przez pracodawce (wpisz to na Gov.uk): GBP {total_agency_paid:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        pdf.set_font("Helvetica", size=10)
        miles_line = f"Suma kosztow za mile: GBP {total_expense:.2f}"
        
    pdf.cell(0, 6, text=miles_line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    final_expense = total_expense
    if uniform_amount > 0:
        if lang == "EN":
            uni_text = f"+ GBP {uniform_amount:.2f} (Uniform Laundry Flat Rate)"
        else:
            uni_text = f"+ GBP {uniform_amount:.2f} (Zryczaltowany koszt prania uniformu)"
        pdf.cell(0, 6, text=uni_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        final_expense += uniform_amount
        
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    if lang == "EN":
        pdf.cell(0, 8, text=f"TOTAL ALLOWABLE EXPENSE (To declare): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 8, text=f"LACZNY KOSZT DO ODLICZENIA (Wpisz w HMRC): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 13)
    
    # WYLICZENIE 20% GOTÓWKI W RAPORCIE
    cash_refund = final_expense * 0.20
    
    if lang == "EN":
        pdf.cell(0, 10, text=f"ESTIMATED CASH REFUND (20% of Expense): GBP {cash_refund:.2f}*", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 10, text=f"SZACOWANA GOTOWKA NA KONTO (20% z kosztow): GBP {cash_refund:.2f}*", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    if lang == "EN":
        disclaimer = ("*This report is for estimation purposes only. The 20% cash refund assumes you are a basic rate taxpayer "
                      "who earned above the Personal Allowance. HMRC makes the final decision.")
    else:
        disclaimer = ("*Raport ma charakter szacunkowy. Szacowana gotowka (20%) zaklada, ze przekroczyles kwote wolna "
                      "i placisz podstawowa stawke podatku. Ostateczna decyzja nalezy do HMRC.")
    pdf.multi_cell(0, 5, text=disclaimer)

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(
        0, 8, text="Financial health is mental wealth | linktr.ee/ACountingPro",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C"
    )

    return bytes(pdf.output())

if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(
        columns=["Date", "From", "To", "Purpose", "Miles", "Agency", "Expense"]
    )

lang = st.sidebar.selectbox("Choose Language / Wybierz Jezyk", ("EN", "PL"))
EN = lang == "EN"

css = """
<style>
.stApp { background-color: #fcfaf5 !important; }
h1, h2, h3, h4 { color: #002147 !important; font-family: Georgia, serif; }
.stButton>button { background-color: #002147 !important; color: #D4AF37 !important; border-radius: 8px !important; border: 2px solid #D4AF37 !important; font-weight: bold !important; }
.stButton>button:hover { background-color: #D4AF37 !important; color: #002147 !important; }
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { background-color: #002147 !important; color: #D4AF37 !important; }
[data-testid="stMetricValue"] { color: #D4AF37 !important; }
.brand-card { background: #fffdf8; border: 1px solid #e6dcc6; border-radius: 14px; padding: 18px; box-shadow: 0 4px 14px rgba(0, 33, 71, 0.06); }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

_, col_m, _ = st.columns([1, 2, 1])
with col_m:
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()

    logo_candidates = [
        "logo.png", "logo.PNG", "logo.jpg", "logo.jpeg",
        "acountingpro.png", "ACountingPro.png"
    ]

    logo_found = False
    if PIL_AVAILABLE:
        for name in logo_candidates:
            path = os.path.join(script_dir, name)
            if os.path.exists(path):
                st.image(Image.open(path), use_container_width=True)
                logo_found = True
                break

    if not logo_found:
        st.markdown("<h1 style='text-align:center;color:#002147;'>A Counting Pro</h1>", unsafe_allow_html=True)

    st.markdown("<h3 style='text-align:center;color:#D4AF37;font-style:italic;'>Financial health is mental wealth</h3>", unsafe_allow_html=True)
    sub = "Support for Care, Cleaning & Warehouse Professionals" if EN else "Wsparcie dla Care, Cleaning i Magazynow"
    st.markdown(f"<p style='text-align:center;color:#002147;'><b>{sub}</b></p>", unsafe_allow_html=True)

st.write("---")

tab1, tab2, tab3 = st.tabs([
    "🧮 Calculator" if EN else "🧮 Kalkulator",
    "📊 Report & PDF" if EN else "📊 Raport i PDF",
    "📘 E-book & Help" if EN else "📘 E-book i Pomoc",
])

with tab1:
    col_in, col_math = st.columns([1, 1])

    with col_in:
        emp_paye = "Agency Worker (PAYE)" if EN else "Pracownik Agencji (PAYE)"
        emp_se = "Self-Employed (Sole Trader)" if EN else "Samozatrudniony (Self-Employed)"
        emp_status = st.radio("Employment Status" if EN else "Status zatrudnienia", [emp_paye, emp_se])
        st.write("---")

        d = st.date_input("Trip Date" if EN else "Data przejazdu", date.today())

        col_from, col_to = st.columns(2)
        with col_from:
            from_loc = st.text_input("From / Skad" if EN else "Skad", placeholder="e.g. Home / Dom")
        with col_to:
            to_loc = st.text_input("To / Dokad" if EN else "Dokad", placeholder="e.g. Client address")

        purpose = st.text_input("Purpose of trip" if EN else "Cel przejazdu", placeholder="e.g. Client visit / Wizyta u klienta")

        m_raw = st.number_input("Miles (one way)" if EN else "Mile (w jedna strone)", min_value=0.0, value=15.0, step=1.0)
        round_trip = st.checkbox("Round trip — multiply miles x2" if EN else "Powrot — pomnoz mile x2")
        m = m_raw * 2 if round_trip else m_raw
        if round_trip:
            st.caption(f"{'Total miles (×2)' if EN else 'Suma mil (×2)'}: **{m:.1f}**")

        is_paye = "PAYE" in emp_status
        if is_paye:
            a = st.number_input("Agency rate (p/mile)" if EN else "Stawka pracodawcy (p/mile)", min_value=0.0, max_value=100.0, value=25.0, step=0.5)
            if a > 45:
                st.warning("⚠️ Agency rate above 45p — employer reimburses above HMRC limit. Expense = £0." if EN else "⚠️ Stawka powyzej 45p — pracodawca zwraca powyzej limitu HMRC. Koszt = £0.")
            hmrc_total = m * 0.45
            agency_total = m * (a / 100)
            expense = max(0.0, hmrc_total - agency_total)
        else:
            a = 0.0
            st.info("💡 As Self-Employed you deduct the full 45p per mile as a business expense." if EN else "💡 Jako samozatrudniony odliczasz pelne 45p za mile jako koszt firmowy.")
            hmrc_total = m * 0.45
            agency_total = 0.0
            expense = hmrc_total

    with col_math:
        st.write("#### 🔍 Calculation" if EN else "#### 🔍 Wyliczenia")
        st.write(f"**{'Miles counted' if EN else 'Liczba mil'}:** {m:.1f}")
        st.write(f"**{'HMRC Allowance (45p)' if EN else 'Limit HMRC (45p)'}:** £{hmrc_total:.2f}")
        if is_paye:
            st.write(f"**{'Agency Reimbursement' if EN else 'Zwrot z agencji'}:** £{agency_total:.2f}")
        
        st.write("---")
        
        # TWOJA GENIALNA POPRAWKA (BEZPIECZEŃSTWO KLIENTA):
        st.success(f"**{'Tax Relief / Expense' if EN else 'Ulga / Koszt firmowy'}:** £{expense:.2f}")
        st.caption(
            "Estimate only. HMRC makes the final decision on all tax relief claims."
            if EN else
            "Szacunek orientacyjny. Ostateczna decyzja należy do HMRC."
        )

        if is_paye:
            zwrot_gotowka = expense * 0.20
            if EN:
                st.info(f"💷 Estimated cash refund from HMRC (20%): **£{zwrot_gotowka:.2f}**")
                st.caption(
                    "This is the estimated amount that will hit your bank account. "
                    "**Enter the 'Tax Relief / Expense' amount above in your P87 form, NOT this cash figure.**"
                )
            else:
                st.info(f"💷 Szacowany zwrot gotówki od HMRC (20%): **£{zwrot_gotowka:.2f}**")
                st.caption(
                    "To orientacyjna kwota, która trafi na Twoje konto. "
                    "**Wpisz w P87 kwotę 'Ulga / Koszt firmowy' powyżej, nie tę liczbę.**"
                )

        st.info(f"{'Current Tax Year' if EN else 'Aktualny rok podatkowy'}: **{get_tax_year()}**")

    if st.button("➕ Add to Report" if EN else "➕ Dodaj do Raportu", use_container_width=True):
        new_row = pd.DataFrame({
            "Date": [d],
            "From": [from_loc],
            "To": [to_loc],
            "Purpose": [purpose],
            "Miles": [m],
            "Agency": [a],
            "Expense": [expense],
        })
        st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)
        st.toast("✅ Added to report!" if EN else "✅ Dodano do raportu!")

with tab2:
    st.warning("⚠️ Download your PDF & CSV before closing this page — data will not be saved after you leave." if EN else "⚠️ Pobierz PDF i CSV zanim zamkniesz strone — dane nie beda zapisane.")

    if not st.session_state.history.empty:
        total_m_expense = st.session_state.history["Expense"].sum()

        st.write("### 👕 Uniform & Laundry" if EN else "### 👕 Uniform i Pranie")
        add_uniform = st.checkbox("Include annual flat rate for washing uniform at home" if EN else "Dolicz roczny ryczalt za pranie firmowego uniformu w domu")

        if add_uniform:
            sector_options = {
                "Care / Cleaning (£60)": 60.0,
                "NHS Nurse / Midwife (£125)": 125.0,
                "Retail / Warehouse (£60)": 60.0,
                "Police Officer (£140)": 140.0,
                "Other / Inne (enter manually)": None,
            }
            selected = st.selectbox("Select your sector" if EN else "Wybierz swoja branze", list(sector_options.keys()))
            if sector_options[selected] is None:
                uniform_amount = st.number_input("Uniform allowance (£)" if EN else "Kwota ryczaltu (£)", min_value=0.0, value=60.0, step=1.0)
            else:
                uniform_amount = sector_options[selected]
                st.info(f"{'Flat rate for this sector' if EN else 'Ryczalt dla tej branzy'}: **£{uniform_amount:.0f}**")
        else:
            uniform_amount = 0.0

        final_total = total_m_expense + uniform_amount
        cash_back_total = final_total * 0.20
        
        st.write("---")

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Miles" if EN else "Suma Mil", f"{st.session_state.history['Miles'].sum():.1f}")
        c2.metric("Total Expense" if EN else "Suma Kosztów", f"£{final_total:.2f}")
        
        st.markdown(
            f"""
            <div data-testid="stMetricValue" style="text-align:center;">
                <div style="font-size: 1rem; color: #5a5a5a; margin-bottom: -10px;">{'Estimated CASH (20%)' if EN else 'Gotówka na konto (20%)'}</div>
                <div style="font-size: 2rem; color: #28a745; font-weight: bold;">£{cash_back_total:.2f}</div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        st.write("---")
        st.dataframe(st.session_state.history, use_container_width=True)
        st.write("---")

        dl1, dl2 = st.columns(2)
        with dl1:
            pdf_bytes = create_pdf(st.session_state.history, total_m_expense, uniform_amount, lang)
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
            st.session_state.history = pd.DataFrame(columns=["Date", "From", "To", "Purpose", "Miles", "Agency", "Expense"])
            st.rerun()
    else:
        st.info("No data yet. Add your trips in the Calculator tab!" if EN else "Brak danych. Dodaj przejazdy w zakladce Kalkulator!")

with tab3:
    st.markdown("### 📘 A Counting Pro Brand System")
    st.markdown(
        """
<div class="brand-card">
<b>Aplikacja + E-book + Usługa VIP</b><br><br>
Ta aplikacja nie jest osobnym narzędziem. To pierwszy krok w systemie marki A Counting Pro:
<ul>
<li><b>Aplikacja</b> — szybka kalkulacja Twoich kosztów (Expense) i gotówki na konto (20%)</li>
<li><b>Raport PDF</b> — gotowy dokument z poprawnymi kwotami dla urzędu</li>
<li><b>E-book P87</b> — wizualna instrukcja jak bezpiecznie wysłać te dane do HMRC</li>
<li><b>VIP Service</b> — pomoc 1:1 dla osób, które wolą, żeby księgowa zrobiła to za nich</li>
</ul>
</div>
        """,
        unsafe_allow_html=True
    )

    st.write("")
    linktree_url = "https://linktr.ee/ACountingPro"
    if EN:
        st.info("Use the calculator first, then download your report, then use the E-book to submit your HMRC claim safely.")
        st.markdown(f"[👉 GRAB THE E-BOOK OR BOOK VIP SUPPORT]({linktree_url})")
    else:
        st.info("Najpierw wylicz koszty, pobierz raport, a następnie użyj E-booka P87, aby bezpiecznie wysłać wniosek do HMRC.")
        st.markdown(f"[👉 POBIERZ E-BOOK LUB ZAMÓW POMOC VIP]({linktree_url})")

st.markdown("---")
linktree_url = "https://linktr.ee/ACountingPro"

if EN:
    st.error(
        "### 🚨 TAX YEAR END DEADLINE: Only 6 days left!\n"
        "On April 5th, unclaimed tax relief from 2021/2022 will be **lost forever**.\n\n"
        "Got your report? Don't leave cash at HMRC!\n\n"
        "Get our step-by-step Gov.uk visual E-book for **£15.99**. "
        "It shows you exactly where to click to submit safely - for less than the price of a dinner out!\n\n"
        f"[👉 GRAB THE E-BOOK OR BOOK OUR VIP SERVICE]({linktree_url})"
    )
else:
    st.error(
        "### 🚨 KONIEC ROKU PODATKOWEGO: Zostało tylko 6 dni!\n"
        "5 kwietnia przepadnie bezpowrotnie Twoja gotówka z najstarszego roku podatkowego (2021/22).\n\n"
        "Masz już raport? Nie zostawiaj pieniędzy HMRC!\n\n"
        "Moja wizualna instrukcja Gov.uk jest dostępna za **£15.99**. "
        "Dowiedz się, jak wpisać kwoty z raportu by odzyskać swój podatek!\n\n"
        f"[👉 KLIKNIJ — POBIERZ E-BOOK LUB ZLEĆ TO MI (VIP)]({linktree_url})"
    )

st.markdown(
    f"<p style='text-align:center;color:grey;'>"
    f"© {date.today().year} A Counting Pro | Financial health is mental wealth</p>",
    unsafe_allow_html=True,
)
