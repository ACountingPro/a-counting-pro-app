import streamlit as st
import os
import pandas as pd
import requests
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import date
import io
import unicodedata

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

st.set_page_config(page_title="Refund Checker | A Counting Pro", page_icon="💰", layout="wide")


def remove_polish_chars(text):
    """Zamienia polskie znaki na odpowiedniki ASCII dla PDF"""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N',
        'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
    }
    for pl, en in replacements.items():
        text = text.replace(pl, en)
    return text


def get_tax_year():
    today = date.today()
    if today.month > 4 or (today.month == 4 and today.day >= 6):
        return f"{today.year}/{today.year + 1}"
    return f"{today.year - 1}/{today.year}"


def save_to_mailerlite(email):
    """Zapisuje email do MailerLite, zwraca True jeśli sukces"""
    try:
        api_key = st.secrets["MAILERLITE_API_KEY"]
        group_id = st.secrets["MAILERLITE_GROUP_ID"]
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {"email": email, "groups": [group_id]}
        response = requests.post(
            "https://connect.mailerlite.com/api/subscribers",
            headers=headers, json=data, timeout=10
        )
        return response.status_code in [200, 201]
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return False


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
        f"Generated: {today_str}  |  Current Tax Year: {tax_year}"
        if lang == "EN"
        else f"Wygenerowano: {today_str}  |  Aktualny Rok Podatkowy: {tax_year}"
    )
    pdf.cell(0, 7, text=remove_polish_chars(line1), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    col_widths = [24, 30, 30, 30, 20, 26, 30]
    headers = (
        ["Date", "From", "To", "Purpose", "Miles", "Agency(p)", "Expense(GBP)"]
        if lang == "EN"
        else ["Data", "Skad", "Dokad", "Cel", "Mile", "Agencja(p)", "Koszt(GBP)"]
    )

    pdf.set_font("Helvetica", "B", 8)
    for w, h in zip(col_widths, headers):
        pdf.cell(w, 9, text=remove_polish_chars(h), border=1)
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
            pdf.cell(w, 9, text=remove_polish_chars(v[:14]), border=1)
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
        pdf.cell(0, 6, text=remove_polish_chars(f"Calkowita suma mil (wpisz to na Gov.uk): {total_miles_pdf:.1f}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=remove_polish_chars(f"Kwota zwrocona przez pracodawce (wpisz to na Gov.uk): GBP {total_agency_paid:.2f}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        miles_line = f"Suma kosztow za mile: GBP {total_expense:.2f}"

    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, text=remove_polish_chars(miles_line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    final_expense = total_expense
    if uniform_amount > 0:
        uni_text = (
            f"+ GBP {uniform_amount:.2f} (Uniform Laundry Flat Rate)"
            if lang == "EN"
            else f"+ GBP {uniform_amount:.2f} (Zryczaltowany koszt prania uniformu)"
        )
        pdf.cell(0, 6, text=remove_polish_chars(uni_text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        final_expense += uniform_amount

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    if lang == "EN":
        pdf.cell(0, 8, text=f"TOTAL ALLOWABLE EXPENSE (Enter in P87 form): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 8, text=remove_polish_chars(f"LACZNY KOSZT DO WPISANIA W P87 (Gov.uk): GBP {final_expense:.2f}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    cash_refund = final_expense * 0.20
    if lang == "EN":
        pdf.cell(0, 10, text=f"ESTIMATED CASH REFUND TO YOUR ACCOUNT (20%): GBP {cash_refund:.2f} *", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 10, text=remove_polish_chars(f"SZACOWANA GOTOWKA NA TWOJE KONTO (20%): GBP {cash_refund:.2f} *"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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
    pdf.multi_cell(0, 5, text=remove_polish_chars(disclaimer))

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 8, text="Financial health is mental wealth | linktr.ee/ACountingPro",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    return bytes(pdf.output())


# Inicjalizacja stanu sesji
if "history" not in st.session_state or "Expense" not in st.session_state.history.columns:
    st.session_state.history = pd.DataFrame(
        columns=["Date", "From", "To", "Purpose", "Miles", "Agency", "Expense"]
    )

if "email_submitted" not in st.session_state:
    st.session_state.email_submitted = False

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
.email-gate-box { background-color: #fff8e1; border: 2px solid #D4AF37; padding: 20px; border-radius: 10px; margin-top: 20px; margin-bottom: 20px; }
.app-promo-box { background-color: #e8f5e9; border-left: 5px solid #28a745; padding: 20px; border-radius: 5px; margin-top: 20px; }
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
        
        # DECISION ENGINE - komunikat w zależności od kwoty
        ebook_price = 7.99
        link_url = "https://linktr.ee/ACountingPro"

        if cash_back_total < 25.0:
            msg = "Your claim is small, but still worth recovering!" if EN else "Twój zwrot jest niewielki, ale wciąż warto go odzyskać!"
            st.info(msg)
        elif cash_back_total <= 120.0:
            msg = f"It is profitable to claim this! Get our P87 E-book for £{ebook_price}." if EN else f"Zdecydowanie opłaca się po to sięgnąć! Kup nasz E-book P87 za £{ebook_price}."
            st.success(msg)
            st.link_button("📘 GET P87 E-BOOK" if EN else "📘 KUP E-BOOK P87", link_url, type="primary")
        else:
            msg = "Serious money! You can do it yourself with our E-book or choose VIP." if EN else "To poważne pieniądze! Zrób to sam z E-bookiem lub wybierz opcję VIP."
            st.warning(msg)
            st.link_button("👑 VIP CLAIM SERVICE", link_url, type="primary")

        st.write("---")
        
        # EMAIL GATE - dla WSZYSTKICH, zawsze przed PDF
        if not st.session_state.email_submitted:
            if EN:
                st.markdown("""
                <div class="email-gate-box">
                    <h3 style='color: #002147; margin-top: 0;'>📧 Your PDF is ready!</h3>
                    <p style='color: #002147; margin-bottom: 0;'>Enter your email below and I'll send you the PDF + a free checklist of documents you need for HMRC.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="email-gate-box">
                    <h3 style='color: #002147; margin-top: 0;'>📧 Twój PDF jest gotowy!</h3>
                    <p style='color: #002147; margin-bottom: 0;'>Podaj email, a wyślę Ci PDF + darmową listę dokumentów do HMRC.</p>
                </div>
                """, unsafe_allow_html=True)
            
            with st.form("email_form", clear_on_submit=False):
                email_input = st.text_input(
                    "Email" if EN else "Twój email",
                    placeholder="twoj@email.com"
                )
                
                checkbox_consent = st.checkbox(
                    "I agree to receive HMRC tips from A Counting Pro" if EN else "Zgadzam się na otrzymywanie wskazówek HMRC od A Counting Pro"
                )
                
                submit_btn = st.form_submit_button(
                    "📧 Send me the PDF" if EN else "📧 Wyślij mi PDF",
                    use_container_width=True,
                    type="primary"
                )
                
                if submit_btn:
                    if not email_input or "@" not in email_input:
                        st.error("Please enter a valid email" if EN else "Wpisz poprawny email")
                    elif not checkbox_consent:
                        st.error("Please accept the terms" if EN else "Zaakceptuj regulamin")
                    else:
                        if save_to_mailerlite(email_input):
                            st.session_state.email_submitted = True
                            st.rerun()
                        else:
                            st.error("Something went wrong. Please try again." if EN else "Coś poszło nie tak. Spróbuj ponownie.")
        
        else:
            # Po podaniu emaila - PDF + promo A Counting Go
            pdf_bytes = create_pdf(st.session_state.history, total_m_expense, uniform_amount, lang)
            st.download_button(
                label="📥 Download FREE PDF" if EN else "📥 Pobierz DARMOWY PDF",
                data=pdf_bytes,
                file_name="A_Counting_Pro_Report.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            # Promo A Counting Go
            if EN:
                st.markdown("""
                <div class="app-promo-box">
                    <h4 style='color: #002147; margin-top: 0;'>🎯 Great, you have your report!</h4>
                    <p style='color: #002147;'>You've just calculated how much HMRC owes you for the past 4 years.</p>
                    <p style='color: #002147;'>But the new tax year 2026/27 has already started. Don't repeat the same January stress next year.</p>
                    <p style='color: #002147; margin-bottom: 0;'><b>A Counting Go tracks your miles and receipts automatically - all year round. 7 days free.</b></p>
                </div>
                """, unsafe_allow_html=True)
                st.link_button("🚗 Try A Counting Go - 7 days free", "https://acountinggo.netlify.app", type="primary", use_container_width=True)
            else:
                st.markdown("""
                <div class="app-promo-box">
                    <h4 style='color: #002147; margin-top: 0;'>🎯 Świetnie, masz swój raport!</h4>
                    <p style='color: #002147;'>Właśnie policzyłaś ile HMRC jest Ci winny za ostatnie 4 lata.</p>
                    <p style='color: #002147;'>Ale nowy rok podatkowy 2026/27 już się zaczął. Nie powtarzaj styczniowego stresu w przyszłym roku.</p>
                    <p style='color: #002147; margin-bottom: 0;'><b>A Counting Go zapisuje mile i paragony automatycznie, przez cały rok. 7 dni za darmo.</b></p>
                </div>
                """, unsafe_allow_html=True)
                st.link_button("🚗 Testuj A Counting Go - 7 dni za darmo", "https://acountinggo.netlify.app", type="primary", use_container_width=True)
    
    else:
        st.info("Add data in Calculator first." if EN else "Najpierw dodaj dane w Kalkulatorze.")

with tab3:
    st.markdown("### 📘 A Counting Pro System")
    if EN:
        st.write("1. Check for free. 2. Get P87 E-book to do it yourself. 3. Or let us do it for you (VIP).")
    else:
        st.write("1. Sprawdź za darmo. 2. Kup E-book P87, by zrobić to samemu. 3. Lub zleć to nam (VIP).")

st.markdown("---")
if EN:
    st.error("### 🚀 NEW TAX YEAR 2026/27 IS HERE!\nYou can now claim for the past 4 years. Don't leave your money at HMRC.")
else:
    st.error("### 🚀 NOWY ROK PODATKOWY 2026/27!\nMożesz teraz odzyskać pieniądze za ostatnie 4 lata podatkowe. Nie zostawiaj gotówki w urzędzie.")

st.markdown(f"<p style='text-align:center;color:grey;'>© {date.today().year} A Counting Pro | Financial health is mental wealth</p>", unsafe_allow_html=True)