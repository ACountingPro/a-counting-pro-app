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

st.set_page_config(page_title="A Counting Pro System", page_icon="💰", layout="wide")

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

    total_miles_pdf = df["Miles"].astype(float).sum()
    total_agency_paid = (df["Miles"].astype(float) * (df["Agency"].astype(float) / 100)).sum()

    if lang == "EN":
        pdf.cell(0, 6, text=f"Total business miles (enter on Gov.uk): {total_miles_pdf:.1f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=f"Mileage allowance paid by employer (enter on Gov.uk): GBP {total_agency_paid:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        miles_line = f"Total allowable expense from miles: GBP {total_expense:.2f}"
    else:
        pdf.cell(0, 6, text=f"Calkowita suma mil (wpisz to na Gov.uk): {total_miles_pdf:.1f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=f"Kwota zwrocona przez pracodawce (wpisz to na Gov.uk): GBP {total_agency_paid:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        miles_line = f"Suma kosztow za mile: GBP {total_expense:.2f}"

    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, text=miles_line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    final_expense = total_expense
    if uniform_amount > 0:
        uni_text = (
            f"+ GBP {uniform_amount:.2f} (Uniform Laundry Flat Rate)"
            if lang == "EN"
            else f"+ GBP {uniform_amount:.2f} (Zryczaltowany koszt prania uniformu)"
        )
        pdf.cell(0, 6, text=uni_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        final_expense += uniform_amount

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    if lang == "EN":
        pdf.cell(0, 8, text=f"TOTAL ALLOWABLE EXPENSE (Enter in P87 form): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 8, text=f"LACZNY KOSZT DO WPISANIA W P87 (Gov.uk): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    cash_refund = final_expense * 0.20
    if lang == "EN":
        pdf.cell(0, 10, text=f"ESTIMATED CASH REFUND TO YOUR ACCOUNT (20%): GBP {cash_refund:.2f} *", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 10, text=f"SZACOWANA GOTOWKA NA TWOJE KONTO (20%): GBP {cash_refund:.2f} *", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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
            "* WAZNE: 'Laczny Koszt do Wpisania w P87' to wartosc, ktora wpisujesz w formularzu na Gov.uk. "
            "HMRC nastepnie wyplaci Ci 20% tej kwoty jako gotowke na konto (stawka podstawowa). "
            "Zaklada zarobki powyzej kwoty wolnej (GBP 12,570) i zaplacony podatek. "
            "Ostateczna decyzja nalezy do HMRC."
        )
    pdf.multi_cell(0, 5, text=disclaimer)

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 8, text="Financial health is mental wealth | linktr.ee/ACountingPro",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    return bytes(pdf.output())

# Zabezpieczenie przed starymi sesjami w przeglądarkach klientów
if "history" not in st.session_state or "Expense" not in st.session_state.history.columns:
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
.cash-box { background-color: #e8f5e9; border-left: 5px solid #28a745; padding: 15px; border-radius: 5px; margin-top: 15px; }
.expense-box { background-color: #e3f2fd; border-left: 5px solid #1565c0; padding: 12px; border-radius: 5px; margin-top: 10px; }
.alert-box-red { background-color: #ffebee; border-left: 5px solid #f44336; padding: 15px; border-radius: 5px; margin-top: 15px; }
.alert-box-green { background-color: #e8f5e9; border-left: 5px solid #4caf50; padding: 15px; border-radius: 5px; margin-top: 15px; }
.alert-box-gold { background-color: #fff8e1; border-left: 5px solid #ffb300; padding: 15px; border-radius: 5px; margin-top: 15px; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 🕵️‍♀️ SKANER LOGO
# ==========================================
_, col_m, _ = st.columns([1, 2, 1])
with col_m:
    logo_found = False
    wszystkie_pliki = []
    
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
    except Exception as e:
        pass

    if not logo_found:
        st.markdown("<h1 style='text-align:center;color:#002147;'>💰 A Counting Pro</h1>", unsafe_allow_html=True)

    st.markdown("<h3 style='text-align:center;color:#D4AF37;font-style:italic;'>Financial health is mental wealth</h3>", unsafe_allow_html=True)
    sub = "Tax Claim System for Care, Cleaning & NHS" if EN else "System Zwrotu Podatku (Care, Cleaning, NHS)"
    st.markdown(f"<p style='text-align:center;color:#002147;'><b>{sub}</b></p>", unsafe_allow_html=True)

st.write("---")

tab1, tab2, tab3 = st.tabs([
    "🧮 Calculator" if EN else "🧮 Kalkulator",
    "📊 Report & Decision" if EN else "📊 Raport i Opłacalność",
    "📘 How to Claim?" if EN else "📘 Jak odzyskać?",
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
        
        if lang == "EN":
            st.markdown(f"""
            <div class="expense-box">
                <b>Allowable Expense (enter in P87 on Gov.uk):</b> £{expense:.2f}<br>
                <small>This is the number you type into the HMRC form</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="expense-box">
                <b>Koszt do wpisania w P87 (Gov.uk):</b> £{expense:.2f}<br>
                <small>Te liczbe wpisujesz w formularzu na stronie urzedu HMRC</small>
            </div>
            """, unsafe_allow_html=True)

        if is_paye:
            cash_estimate = expense * 0.20
            if lang == "EN":
                st.markdown(f"""
                <div class="cash-box">
                    <h4 style="color:#155724; margin:0;">💸 Estimated CASH to your account (20%): £{cash_estimate:.2f}</h4>
                </div>
                """, unsafe_allow_html=True)
                st.caption("Assumes basic rate (20%) taxpayer, earnings above £12,570. Final decision: HMRC.")
            else:
                st.markdown(f"""
                <div class="cash-box">
                    <h4 style="color:#155724; margin:0;">💸 Szacowana GOTÓWKA na konto (20%): £{cash_estimate:.2f}</h4>
                </div>
                """, unsafe_allow_html=True)
                st.caption("Dotyczy platnikow 20%, zarobki powyzej kwoty wolnej. Decyzja należy do HMRC.")

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
    st.warning("⚠️ Download your PDF & CSV before closing this page." if EN else "⚠️ Pobierz PDF i CSV zanim zamkniesz stronę.")

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
        c2.metric("Total Expense (P87)" if EN else "Koszt P87", f"£{final_total:.2f}")
        
        st.markdown(
            f"""
            <div data-testid="stMetricValue" style="text-align:center;">
                <div style="font-size: 1rem; color: #5a5a5a; margin-bottom: -10px;">{'Estimated CASH (20%)' if EN else 'Gotówka na konto (20%)'}</div>
                <div style="font-size: 2rem; color: #28a745; font-weight: bold;">£{cash_back_total:.2f}</div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        # ==========================================
        # 🔥 SILNIK REKOMENDACJI (LEJEK SPRZEDAŻOWY)
        # ==========================================
        st.write("---")
        st.write("### 💡 " + ("Is it worth claiming?" if EN else "Weryfikacja Opłacalności"))
        
        ebook_price = 15.99
        profit = cash_back_total - ebook_price
        link_ebook = "https://linktr.ee/ACountingPro"
        link_vip = "https://linktr.ee/ACountingPro"

        if cash_back_total == 0:
            if EN:
                st.info("Add some trips or uniform allowance to see your recommendation.")
            else:
                st.info("Dodaj przejazdy lub pranie uniformu, aby zobaczyć rekomendację.")
                
        elif cash_back_total < 25.0:
            if EN:
                st.markdown(f"""
                <div class="alert-box-red">
                    <h4 style="color:#b71c1c; margin-top:0;">🛑 NOT WORTH BUYING</h4>
                    Estimated cash: <b>£{cash_back_total:.2f}</b> | E-book cost: £{ebook_price}.<br>
                    <b>Your Profit: £{profit:.2f}</b><br><br>
                    <b>Honestly? Do not buy our E-book.</b> Your return for a single year is too small. We value honesty over a quick sale. Download your free PDF below and try submitting it yourself, or multiply this by 4 years if applicable!
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="alert-box-red">
                    <h4 style="color:#b71c1c; margin-top:0;">🛑 NIE OPŁACA CI SIĘ (Nie kupuj)</h4>
                    Szacowana gotówka: <b>£{cash_back_total:.2f}</b> | Koszt E-booka: £{ebook_price}.<br>
                    <b>Twój czysty zysk: £{profit:.2f}</b><br><br>
                    <b>Szczerze? Nie kupuj naszej instrukcji.</b> Jeśli to kwota tylko za 1 rok, Twój zysk jest znikomy. Gramy w otwarte karty - szkoda Twoich pieniędzy. Pobierz darmowy raport, spróbuj zrobić to sam/a, chyba że masz do rozliczenia 4 lata wstecz (wtedy pomnóż ten wynik x4)!
                </div>
                """, unsafe_allow_html=True)
                
        elif cash_back_total < 150.0:
            if EN:
                st.markdown(f"""
                <div class="alert-box-green">
                    <h4 style="color:#1b5e20; margin-top:0;">✅ GREAT ROI: DO IT YOURSELF</h4>
                    Estimated cash: <b>£{cash_back_total:.2f}</b> | E-book cost: £{ebook_price}.<br>
                    <b>Pure Profit: £{profit:.2f}</b> (Multiply by up to 4 years!)<br><br>
                    It is highly profitable for you to claim this! Don't pay an agency 30% commission. Invest in our visual step-by-step E-book and submit your claim safely in 15 minutes.
                </div>
                """, unsafe_allow_html=True)
                st.link_button("📘 BUY E-BOOK (£15.99)", link_ebook, type="primary", use_container_width=True)
            else:
                st.markdown(f"""
                <div class="alert-box-green">
                    <h4 style="color:#1b5e20; margin-top:0;">✅ IDEALNIE: ZRÓB TO SAM I ZYSKAJ</h4>
                    Szacowana gotówka: <b>£{cash_back_total:.2f}</b> | Koszt E-booka: £{ebook_price}.<br>
                    <b>Czysty zysk: £{profit:.2f}</b> (A pomnóż to przez 4 lata wstecz!).<br><br>
                    Zdecydowanie opłaca Ci się po to schylić! Nie oddawaj prowizji pośrednikom. Zainwestuj w E-book Premium i wyślij wniosek bezbłędnie z własnej kanapy.
                </div>
                """, unsafe_allow_html=True)
                st.link_button("📘 KUP E-BOOK (£15.99)", link_ebook, type="primary", use_container_width=True)
                
        else:
            if EN:
                st.markdown(f"""
                <div class="alert-box-gold">
                    <h4 style="color:#e65100; margin-top:0;">🔥 HUGE CLAIM: DON'T LEAVE THIS AT HMRC</h4>
                    Estimated cash: <b>£{cash_back_total:.2f}</b> | E-book cost: £{ebook_price}.<br>
                    <b>Pure Profit: £{profit:.2f}</b> (Multiply by up to 4 years!)<br><br>
                    This is a serious amount of money! Because your claim is so high, you have two safe options to get it back:
                </div>
                """, unsafe_allow_html=True)
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    st.link_button("📘 DO IT MYSELF (E-book £15.99)", link_ebook, use_container_width=True)
                with c_btn2:
                    st.link_button("👑 DO IT FOR ME (VIP Service)", link_vip, type="primary", use_container_width=True)
            else:
                st.markdown(f"""
                <div class="alert-box-gold">
                    <h4 style="color:#e65100; margin-top:0;">🔥 GIGANTYCZNY ZWROT: £{cash_back_total:.2f}</h4>
                    Szacowana gotówka: <b>£{cash_back_total:.2f}</b> | Koszt E-booka: £{ebook_price}.<br>
                    <b>Czysty zysk: £{profit:.2f}</b> (A pomnóż to przez 4 lata wstecz!).<br><br>
                    Zostawienie tych pieniędzy w urzędzie byłoby grzechem! Przy tak ogromnej kwocie masz dwie bezpieczne opcje odzyskania gotówki:
                </div>
                """, unsafe_allow_html=True)
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    st.link_button("📘 ZROBIĘ TO SAM/A (E-book £15.99)", link_ebook, use_container_width=True)
                with c_btn2:
                    st.link_button("👑 ZRÓBCIE TO ZA MNIE (Usługa VIP)", link_vip, type="primary", use_container_width=True)

        st.write("---")
        st.dataframe(st.session_state.history, use_container_width=True)
        st.write("---")

        dl1, dl2 = st.columns(2)
        with dl1:
            pdf_bytes = create_pdf(st.session_state.history, total_m_expense, uniform_amount, lang)
            st.download_button(
                label="📥 Download PDF for HMRC" if EN else "📥 Pobierz bezpłatny Raport PDF",
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
    if EN:
        st.markdown("### 📘 A Counting Pro Claim System")
        st.markdown(
            """
<div class="brand-card">
<b>This app is the first step in our HMRC claim system:</b><br><br>
<ul>
<li><b>Step 1: Free App</b> — Filters your eligibility. Calculates your accurate Claim & Estimated Net Profit.</li>
<li><b>Step 2: Free PDF Report</b> — Generates your evidence document for HMRC.</li>
<li><b>Step 3: P87 E-book</b> — Premium visual Gov.uk guide. Do it yourself, avoid mistakes and 30% agency fees.</li>
<li><b>Step 4: VIP Service</b> — Done-for-you support where an accountant does it all for you (best for high value claims).</li>
</ul>
</div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("### 📘 System Odzyskiwania Podatku A Counting Pro")
        st.markdown(
            """
<div class="brand-card">
<b>Nasza darmowa aplikacja to 1. krok w Twojej drodze po podatek:</b><br><br>
<ul>
<li><b>Krok 1: Aplikacja (Filtr)</b> — Szczerze weryfikuje opłacalność. Zlicza Twój szacowany zysk na czysto.</li>
<li><b>Krok 2: Raport PDF</b> — Pobierasz darmowy, bezpieczny dowód z kwotami dla urzędu.</li>
<li><b>Krok 3: E-book P87 (£15.99)</b> — Kupujesz wizualną instrukcję Gov.uk. Składasz wniosek samodzielnie i bezpiecznie, omijając drogie agencje.</li>
<li><b>Krok 4: VIP Service</b> — Jeśli masz potężny zwrot i wolisz, żeby wzięła to na siebie licencjonowana księgowa.</li>
</ul>
</div>
            """,
            unsafe_allow_html=True
        )

st.markdown("---")

if EN:
    st.error(
        "### 🚨 TAX YEAR END DEADLINE!\n"
        "On April 5th, unclaimed tax relief from 2021/2022 will be **lost forever**.\n\n"
        "Got your report? Don't leave cash at HMRC and don't pay accountants a 30% commission!\n\n"
    )
else:
    st.error(
        "### 🚨 KONIEC ROKU PODATKOWEGO!\n"
        "5 kwietnia przepadnie bezpowrotnie Twoja gotówka z najstarszego roku podatkowego (2021/22).\n\n"
        "Masz już raport? Aplikacja dała Ci zielone światło? Nie zostawiaj pieniędzy w urzędzie i nie płać pośrednikom!\n\n"
    )

st.markdown(
    f"<p style='text-align:center;color:grey;'>"
    f"© {date.today().year} A Counting Pro | Financial health is mental wealth</p>",
    unsafe_allow_html=True,
)
