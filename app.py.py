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

st.set_page_config(page_title="Refund Checker | A Counting Pro", page_icon="💰", layout="wide")

def get_tax_year():
    today = date.today()
    if today.month > 4 or (today.month == 4 and today.day >= 6):
        return f"{today.year}/{today.year + 1}"
    return f"{today.year - 1}/{today.year}"

def create_pdf(df, total_expense, uniform_amount, lang):
    pdf = FPDF()
    pdf.add_page()

    title = "Mileage & Tax Relief Report" if lang == "EN" else "Raport Przebiegu i Kosztów"
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, text=f"{title} - A Counting Pro", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=9)
    today_str = date.today().strftime("%d/%m/%Y")
    tax_year = get_tax_year()
    line1 = (
        f"Generated: {today_str}  |  Current Tax Year: {tax_year}"
        if lang == "EN"
        else f"Wygenerowano: {today_str}  |  Aktualny Rok Podatkowy: {tax_year}"
    )
    pdf.cell(0, 7, text=line1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    col_widths = [24, 30, 30, 30, 20, 26, 30]
    headers = (
        ["Date", "From", "To", "Purpose", "Miles", "Agency(p)", "Expense(GBP)"]
        if lang == "EN"
        else ["Data", "Skąd", "Dokąd", "Cel", "Mile", "Agencja(p)", "Koszt(GBP)"]
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

    total_miles_pdf = df["Miles"].astype(float).sum()
    total_agency_paid = (df["Miles"].astype(float) * (df["Agency"].astype(float) / 100)).sum()

    if lang == "EN":
        pdf.cell(0, 6, text=f"Total business miles (enter on Gov.uk): {total_miles_pdf:.1f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=f"Mileage allowance paid by employer (enter on Gov.uk): GBP {total_agency_paid:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        miles_line = f"Total allowable expense from miles: GBP {total_expense:.2f}"
    else:
        pdf.cell(0, 6, text=f"Całkowita suma mil (wpisz to na Gov.uk): {total_miles_pdf:.1f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=f"Kwota zwrócona przez pracodawcę (wpisz to na Gov.uk): GBP {total_agency_paid:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        miles_line = f"Suma kosztów za mile: GBP {total_expense:.2f}"

    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, text=miles_line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    final_expense = total_expense
    if uniform_amount > 0:
        uni_text = (
            f"+ GBP {uniform_amount:.2f} (Uniform Laundry Flat Rate)"
            if lang == "EN"
            else f"+ GBP {uniform_amount:.2f} (Zryczałtowany koszt prania uniformu)"
        )
        pdf.cell(0, 6, text=uni_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        final_expense += uniform_amount

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    if lang == "EN":
        pdf.cell(0, 8, text=f"TOTAL ALLOWABLE EXPENSE (Enter in P87 form): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 8, text=f"ŁĄCZNY KOSZT DO WPISANIA W P87 (Gov.uk): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    cash_refund = final_expense * 0.20
    if lang == "EN":
        pdf.cell(0, 10, text=f"ESTIMATED CASH REFUND TO YOUR ACCOUNT (20%): GBP {cash_refund:.2f} *", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 10, text=f"SZACOWANA GOTÓWKA NA TWOJE KONTO (20%): GBP {cash_refund:.2f} *", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    if lang == "EN":
        disclaimer = (
            "* IMPORTANT: 'Total Allowable Expense' is what you enter into the P87 form on Gov.uk. "
            "HMRC then pays you 20% of that amount as cash (basic rate taxpayer). "
            "Assumes earnings above Personal Allowance (GBP 12,570) and Income Tax paid. "
            "Final decision rests with HMRC."
        )
    else:
        disclaimer = (
            "* WAŻNE: 'Łączny Koszt do Wpisania w P87' to wartość, którą wpisujesz w formularzu na Gov.uk. "
            "HMRC następnie wypłaci Ci 20% tej kwoty jako gotówkę na konto (stawka podstawowa). "
            "Zakłada zarobki powyżej kwoty wolnej (GBP 12,570) i zapłacony podatek. "
            "Ostateczna decyzja należy do HMRC."
        )
    pdf.multi_cell(0, 5, text=disclaimer)

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 8, text="Financial health is mental wealth | linktr.ee/ACountingPro",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    return bytes(pdf.output())

if "history" not in st.session_state or "Expense" not in st.session_state.history.columns:
    st.session_state.history = pd.DataFrame(
        columns=["Date", "From", "To", "Purpose", "Miles", "Agency", "Expense"]
    )

lang = st.sidebar.selectbox("Choose Language / Wybierz Język", ("EN", "PL"))
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
.cash-box { background-color: #e8f5e9; border-left: 5px solid #28a745; padding: 15px; border-radius: 5px; margin-top: 15px; }
.expense-box { background-color: #e3f2fd; border-left: 5px solid #1565c0; padding: 12px; border-radius: 5px; margin-top: 10px; }
.alert-box-grey { background-color: #f5f5f5; border-left: 5px solid #9e9e9e; padding: 15px; border-radius: 5px; margin-top: 15px; }
.alert-box-green { background-color: #e8f5e9; border-left: 5px solid #4caf50; padding: 15px; border-radius: 5px; margin-top: 15px; }
.alert-box-gold { background-color: #fff8e1; border-left: 5px solid #ffb300; padding: 15px; border-radius: 5px; margin-top: 15px; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

_, col_m, _ = st.columns([1, 2, 1])
with col_m:
    logo_found = False
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        wszystkie_pliki = os.listdir(script_dir)
        for plik in wszystkie_pliki:
            plik_lower = plik.lower()
            if ("logo" in plik_lower or "acounting" in plik_lower) and plik_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
                sciezka = os.path.join(script_dir, plik)
                st.image(sciezka, use_container_width=True)
                logo_found = True
                break
    except Exception:
        pass

    if not logo_found:
        st.markdown("<h1 style='text-align:center;color:#002147;'>💰 A Counting Pro</h1>", unsafe_allow_html=True)

    st.markdown("<h2 style='text-align:center;color:#D4AF37;'>Refund Checker</h2>", unsafe_allow_html=True)
    sub = "For Care Workers, Cleaners & NHS Professionals" if EN else "Dla branży Care, Cleaning i NHS"
    st.markdown(f"<p style='text-align:center;color:#002147;'><b>{sub}</b></p>", unsafe_allow_html=True)

st.write("---")

tab1, tab2, tab3 = st.tabs([
    "🧮 Calculator" if EN else "🧮 Kalkulator",
    "📊 Decision & Report" if EN else "📊 Wynik i Decyzja",
    "📘 How to Claim?" if EN else "📘 Twój Plan Działania",
])

with tab1:
    if EN:
        st.markdown("##### New Tax Year has started! Check how much you can reclaim for the last 4 years.")
    else:
        st.markdown("##### Nowy rok podatkowy właśnie ruszył! Sprawdź ile możesz odzyskać nawet za 4 lata wstecz.")
        
    col_in, col_math = st.columns([1, 1])

    with col_in:
        emp_paye = "Agency Worker (PAYE)" if EN else "Pracownik Agencji (PAYE)"
        emp_se = "Self-Employed (Sole Trader)" if EN else "Samozatrudniony (Self-Employed)"
        emp_status = st.radio("Employment Status" if EN else "Status zatrudnienia", [emp_paye, emp_se])
        st.write("---")

        d = st.date_input("Trip Date" if EN else "Data przejazdu", date.today())

        col_from, col_to = st.columns(2)
        with col_from:
            from_loc = st.text_input("From" if EN else "Skąd", placeholder="e.g. Home")
        with col_to:
            to_loc = st.text_input("To" if EN else "Dokąd", placeholder="e.g. Client address")

        purpose = st.text_input("Purpose of trip" if EN else "Cel przejazdu", placeholder="e.g. Client visit")

        m_raw = st.number_input("Miles (one way)" if EN else "Mile (w jedną stronę)", min_value=0.0, value=15.0, step=1.0)
        round_trip = st.checkbox("Round trip (x2)" if EN else "Powrót (pomnóż mile x2)")
        m = m_raw * 2 if round_trip else m_raw
        
        is_paye = "PAYE" in emp_status
        if is_paye:
            a = st.number_input("Agency rate (p/mile)" if EN else "Stawka pracodawcy (p/mile)", min_value=0.0, max_value=100.0, value=25.0, step=0.5)
            hmrc_total = m * 0.45
            agency_total = m * (a / 100)
            expense = max(0.0, hmrc_total - agency_total)
        else:
            a = 0.0
            hmrc_total = m * 0.45
            agency_total = 0.0
            expense = hmrc_total

    with col_math:
        st.write("#### 🔍 Calculation" if EN else "#### 🔍 Wyliczenia")
        st.write(f"**{'Miles counted' if EN else 'Liczba mil'}:** {m:.1f}")
        st.write(f"**{'HMRC Allowance (45p)' if EN else 'Limit HMRC (45p)'}:** £{hmrc_total:.2f}")
        
        st.write("---")
        
        if lang == "EN":
            st.markdown(f"""
            <div class="expense-box">
                <b>Allowable Expense (enter in P87):</b> £{expense:.2f}<br>
                <small>This number goes to the HMRC form</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="expense-box">
                <b>Koszt do wpisania w P87:</b> £{expense:.2f}<br>
                <small>Tę liczbę wpisujesz w formularzu HMRC</small>
            </div>
            """, unsafe_allow_html=True)

        if is_paye:
            cash_estimate = expense * 0.20
            label = "Estimated CASH to your account" if EN else "Szacowana GOTÓWKA na konto"
            st.markdown(f"""
            <div class="cash-box">
                <h4 style="color:#155724; margin:0;">💸 {label}: £{cash_estimate:.2f}</h4>
            </div>
            """, unsafe_allow_html=True)

    if st.button("➕ Add to Report" if EN else "➕ Dodaj do Raportu", use_container_width=True):
        new_row = pd.DataFrame({
            "Date": [d], "From": [from_loc], "To": [to_loc], "Purpose": [purpose],
            "Miles": [m], "Agency": [a], "Expense": [expense],
        })
        st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)
        st.toast("✅ Added!" if EN else "✅ Dodano!")

with tab2:
    if not st.session_state.history.empty:
        total_m_expense = st.session_state.history["Expense"].sum()
        add_uniform = st.checkbox("Include uniform laundry rate" if EN else "Dolicz ryczałt za pranie uniformu")
        uniform_amount = 60.0 if add_uniform else 0.0

        final_total = total_m_expense + uniform_amount
        cash_back_total = final_total * 0.20
        
        st.write("---")
        c1, c2 = st.columns(2)
        c1.metric("Total Expense (P87)" if EN else "Koszt P87", f"£{final_total:.2f}")
        c2.metric("Estimated Refund" if EN else "Szacowany Zwrot", f"£{cash_back_total:.2f}")

        st.write("---")
        
        # DECISION ENGINE
        roadmap_price = 24.99
        link_url = "https://linktr.ee/ACountingPro"

        if cash_back_total < 25.0:
            msg = "Your claim is small. Use the free PDF below and try it yourself." if EN else "Twój zwrot jest niewielki. Pobierz darmowy raport i spróbuj rozliczyć się samodzielnie."
            st.info(msg)
        elif cash_back_total <= 120.0:
            msg = f"It is profitable to claim this! Get our Roadmap for £{roadmap_price}." if EN else f"Zdecydowanie opłaca się po to sięgnąć! Kup nasz Roadmap za £{roadmap_price}."
            st.success(msg)
            st.link_button("📘 GET ROADMAP" if EN else "📘 KUP ROADMAP", link_url, type="primary")
        else:
            msg = "Serious money! You can do it yourself with our Roadmap or choose VIP." if EN else "To poważne pieniądze! Zrób to sam z Roadmapem lub wybierz opcję VIP."
            st.warning(msg)
            st.link_button("👑 VIP CLAIM SERVICE", link_url, type="primary")

        st.write("---")
        pdf_bytes = create_pdf(st.session_state.history, total_m_expense, uniform_amount, lang)
        st.download_button(label="📥 Download FREE PDF" if EN else "📥 Pobierz DARMOWY PDF", data=pdf_bytes, file_name="A_Counting_Pro_Report.pdf", mime="application/pdf")
    else:
        st.info("Add data in Calculator first." if EN else "Najpierw dodaj dane w Kalkulatorze.")

with tab3:
    st.markdown("### 📘 A Counting Pro System")
    if EN:
        st.write("1. Check for free. 2. Get Roadmap to do it yourself. 3. Or let us do it for you (VIP).")
    else:
        st.write("1. Sprawdź za darmo. 2. Kup Roadmap, by zrobić to samemu. 3. Lub zleć to nam (VIP).")

st.markdown("---")
# AKTUALIZACJA PO 5 KWIETNIA
if EN:
    st.error("### 🚀 NEW TAX YEAR 2026/27 IS HERE!\nYou can now claim for the past 4 years. Don't leave your money at HMRC.")
else:
    st.error("### 🚀 NOWY ROK PODATKOWY 2026/27!\nMożesz teraz odzyskać pieniądze za ostatnie 4 lata podatkowe. Nie zostawiaj gotówki w urzędzie.")

st.markdown(f"<p style='text-align:center;color:grey;'>© {date.today().year} A Counting Pro | Financial health is mental wealth</p>", unsafe_allow_html=True)
