import streamlit as st
import time
import os
import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import date
from PIL import Image

# 1. Konfiguracja strony
st.set_page_config(page_title="A Counting Pro", page_icon="💰", layout="wide")

# 2. Funkcja PDF
def create_pdf(df, total_owed, lang):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    
    title = "Mileage & Tax Relief Report" if lang == "EN" else "Raport Przebiegu i Ulgi Podatkowej"
    pdf.cell(200, 10, text=f"{title} - A Counting Pro", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", size=10)
    today = date.today().strftime("%d/%m/%Y")
    date_text = f"Generated: {today}" if lang == "EN" else f"Wygenerowano: {today}"
    pdf.cell(200, 7, text=date_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 10)
    headers = ["Date", "Miles", "Agency (p)", "Relief/Expense (£)"] if lang == "EN" else ["Data", "Mile", "Agencja (p)", "Ulga/Koszt (£)"]
    for h in headers:
        pdf.cell(45, 10, text=h, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", size=10)
    for _, row in df.iterrows():
        pdf.cell(45, 10, text=str(row['Date']), border=1)
        pdf.cell(45, 10, text=str(row['Miles']), border=1)
        
        # Jeśli Self-Employed (agencja = 0), pokazujemy N/A lub 0
        agency_val = "N/A" if row['Agency'] == 0.0 else str(row['Agency'])
        pdf.cell(45, 10, text=agency_val, border=1)
        
        pdf.cell(45, 10, text=f"{row['Relief']:.2f}", border=1)
        pdf.ln()

    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 12)
    total_text = f"TOTAL RELIEF/EXPENSE: GBP {total_owed:.2f}" if lang == "EN" else f"LACZNA ULGA/KOSZT: GBP {total_owed:.2f}"
    pdf.cell(200, 10, text=total_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.ln(20)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(200, 10, text="Financial health is mental wealth", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    
    return bytes(pdf.output())

# 3. Inicjalizacja pamięci
if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['Date', 'Miles', 'Agency', 'Relief'])

# 4. Design & Sidebar
lang = st.sidebar.selectbox("Choose Language / Wybierz Język", ("EN", "PL"))

st.markdown("""
    <style>
    .stApp { background-color: #fcfaf5 !important; }
    h1, h2, h3, h4 { color: #002147 !important; font-family: 'Georgia', serif; }
    .stButton>button {
        background-color: #002147 !important;
        color: #D4AF37 !important;
        border-radius: 25px !important;
        border: 2px solid #D4AF37 !important;
        font-weight: bold !important;
    }
    .stButton>button:hover { background-color: #D4AF37 !important; color: #002147 !important; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        background-color: #002147 !important;
        color: #D4AF37 !important;
    }
    [data-testid="stMetricValue"] { color: #D4AF37 !important; }
    </style>
    """, unsafe_allow_html=True)

t = {
    "motto": "Financial health is mental wealth",
    "sub": "Support for Care & Cleaning Professionals" if lang == "EN" else "Wsparcie dla Specjalistów Opieki i Sprzątania",
    "tab1": "🧮 Calculator" if lang == "EN" else "🧮 Kalkulator",
    "tab2": "📊 History" if lang == "EN" else "📊 Historia",
    "tab3": "💡 Expert Tips" if lang == "EN" else "💡 Ekspert radzi",
    "tab4": "🧘 Calm" if lang == "EN" else "🧘 Spokój",
    
    "trip_details": "#### 🚗 Trip Details" if lang == "EN" else "#### 🚗 Szczegóły przejazdu",
    "emp_status_lbl": "Employment Status" if lang == "EN" else "Status zatrudnienia",
    "emp_paye": "Agency Worker (PAYE)" if lang == "EN" else "Pracownik Agencji (PAYE)",
    "emp_se": "Self-Employed (Sole Trader)" if lang == "EN" else "Samozatrudniony (Self-Employed)",
    "date_lbl": "Trip Date" if lang == "EN" else "Data przejazdu",
    "miles_lbl": "Total Miles" if lang == "EN" else "Suma mil",
    "agency_lbl": "Agency rate (p/mile)" if lang == "EN" else "Stawka agencji (pensy/mila)",
    "btn_add": "Add to Calculation" if lang == "EN" else "Dodaj do obliczeń",
    
    "math_h": "#### 🔍 Calculation Breakdown" if lang == "EN" else "#### 🔍 Rozbicie matematyczne",
    "hmrc_step": "HMRC Allowance (45p):" if lang == "EN" else "Limit HMRC (45p):",
    "paid_step": "Agency Reimbursement:" if lang == "EN" else "Zwrot z agencji:",
    "relief_step": "Final Tax Relief:" if lang == "EN" else "Końcowa ulga podatkowa:",
    "se_step": "Allowable Business Expense:" if lang == "EN" else "Koszt firmowy obniżający podatek:",
    "se_info": "💡 As Self-Employed, you can deduct the full 45p per mile as a business expense!" if lang == "EN" else "💡 Jako samozatrudniony odliczasz pełne 45p za milę jako koszt uzyskania przychodu!",
    "toast_add": "Trip added to history!" if lang == "EN" else "Dodano przejazd do historii!",
    
    "metric_miles": "Total Miles" if lang == "EN" else "Suma Mil",
    "metric_relief": "Total Relief / Expense" if lang == "EN" else "Suma Ulgi / Kosztów",
    "chart_h": "### Analysis" if lang == "EN" else "### Analiza",
    "btn_pdf": "📥 Download PDF Report" if lang == "EN" else "📥 Pobierz Raport PDF",
    "btn_clear": "Clear History" if lang == "EN" else "Wyczyść historię",
    "no_data": "No data in history." if lang == "EN" else "Brak danych w historii.",
    
    "tips_h": "### What can you deduct?" if lang == "EN" else "### Co możesz odliczyć od podatku?",
    "tip1": "• **Cleaning supplies & equipment** (detergents, vacuums, mops)" if lang == "EN" else "• **Środki czystości i sprzęt** (detergenty, odkurzacze, mopy)",
    "tip2": "• **Work uniforms & laundry** (cost of buying and washing protective clothing)" if lang == "EN" else "• **Odzież robocza i pranie** (koszt zakupu i prania ubrań ochronnych)",
    "tip3": "• **PPE** (gloves, masks, overshoes)" if lang == "EN" else "• **Środki Ochrony Indywidualnej (PPE)** (rękawiczki, maski, ochraniacze na buty)",
    "tip4": "• **Business Insurance** (Public Liability)" if lang == "EN" else "• **Ubezpieczenie zawodowe** (Public Liability Insurance)",
    "tip5": "• **Phone & Internet bills** (business percentage only)" if lang == "EN" else "• **Rachunki za telefon i internet** (tylko część służbowa)",
    "tip6": "• **Professional fees & DBS checks** (if required for work)" if lang == "EN" else "• **Opłaty członkowskie i certyfikaty DBS** (jeśli są wymagane do pracy)",
    "tip7": "• **Marketing & Stationery** (flyers, business cards, diaries)" if lang == "EN" else "• **Koszty biurowe i marketing** (ulotki, wizytówki, kalendarze)",
    "tip_warn": "⚠️ **Remember:** Keep all your business receipts and invoices for at least 5 years!" if lang == "EN" else "⚠️ **Pamiętaj:** Zachowaj wszystkie paragony i faktury firmowe przez co najmniej 5 lat!",
    
    "mindset_h": "Mindset" if lang == "EN" else "Nastawienie",
    "btn_breathe": "Breathe with me" if lang == "EN" else "Oddychaj ze mną",
    "inhale": "Inhale deeply..." if lang == "EN" else "Głęboki wdech...",
    "exhale": "Exhale slowly..." if lang == "EN" else "Spokojny wydech..."
}

# 5. Nagłówek i Logo
_, col_m, _ = st.columns([1, 2, 1])
with col_m:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logo_found = False
    for name in ["logo.png", "logo", "logo.png.png"]:
        path = os.path.join(script_dir, name)
        if os.path.exists(path):
            st.image(Image.open(path), use_container_width=True)
            logo_found = True
            break
    if not logo_found:
        st.info("A Counting Pro")
    st.markdown(f"<h3 style='text-align: center; color: #D4AF37; font-style: italic;'>{t['motto']}</h3>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: #002147;'>{t['sub']}</p>", unsafe_allow_html=True)

st.write("---")

# 6. ZAKŁADKI
tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])

with tab1:
    col_in, col_math = st.columns([1, 1.2])
    
    with col_in:
        st.write(t["trip_details"])
        
        # --- NOWOŚĆ: WYBÓR STATUSU ZATRUDNIENIA ---
        emp_status = st.radio(t["emp_status_lbl"], [t["emp_paye"], t["emp_se"]])
        st.write("---")
        
        d = st.date_input(t["date_lbl"], date.today())
        m = st.number_input(t["miles_lbl"], min_value=0.0, value=100.0, step=1.0)
        
        if emp_status == t["emp_paye"]:
            a = st.number_input(t["agency_lbl"], min_value=0.0, value=25.0, step=1.0)
            hmrc_total = m * 0.45
            agency_total = m * (a / 100)
            relief = max(0.0, hmrc_total - agency_total)
        else:
            a = 0.0 # Brak stawki agencji przy samozatrudnieniu
            st.info(t["se_info"])
            hmrc_total = m * 0.45
            agency_total = 0.0
            relief = hmrc_total # Całość wrzucamy w koszty

    with col_math:
        st.write(t["math_h"])
        if emp_status == t["emp_paye"]:
            st.latex(r"Relief = (Miles \times 0.45) - (Miles \times \frac{Agency\_Rate}{100})")
            st.write(f"**1. {t['hmrc_step']}** £{hmrc_total:.2f}")
            st.write(f"**2. {t['paid_step']}** £{agency_total:.2f}")
            st.success(f"**3. {t['relief_step']}** £{relief:.2f}")
        else:
            st.latex(r"Expense = Miles \times 0.45")
            st.write(f"**1. {t['hmrc_step']}** £{hmrc_total:.2f}")
            st.success(f"**2. {t['se_step']}** £{relief:.2f}")

    if st.button(t["btn_add"], use_container_width=True):
        new_row = pd.DataFrame({'Date': [d], 'Miles': [m], 'Agency': [a], 'Relief': [relief]})
        st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)
        st.toast(t["toast_add"])

with tab2:
    if not st.session_state.history.empty:
        total_r = st.session_state.history['Relief'].sum()
        
        m1, m2 = st.columns(2)
        m1.metric(t["metric_miles"], f"{st.session_state.history['Miles'].sum():.1f}")
        m2.metric(t["metric_relief"], f"£{total_r:.2f}")
        
        st.write("---")
        st.write(t["chart_h"])
        st.bar_chart(st.session_state.history, x="Date", y="Relief")
        st.dataframe(st.session_state.history, use_container_width=True)
        
        pdf_bytes = create_pdf(st.session_state.history, total_r, lang)
        st.download_button(t["btn_pdf"], pdf_bytes, f"ACountingPro_{date.today()}.pdf")
        
        if st.button(t["btn_clear"]):
            st.session_state.history = pd.DataFrame(columns=['Date', 'Miles', 'Agency', 'Relief'])
            st.rerun()
    else:
        st.info(t["no_data"])

with tab3:
    st.write(t["tips_h"])
    st.write(t["tip1"])
    st.write(t["tip2"])
    st.write(t["tip3"])
    st.write(t["tip4"])
    st.write(t["tip5"])
    st.write(t["tip6"])
    st.write(t["tip7"])
    st.warning(t["tip_warn"])

with tab4:
    st.subheader(t["mindset_h"])
    if st.button(t["btn_breathe"]):
        ph = st.empty()
        for i in range(5):
            ph.info(f"🧘 {t['inhale']} {i+1}/5")
            time.sleep(3)
            ph.success(f"✨ {t['exhale']} {i+1}/5")
            time.sleep(3)
        st.balloons()

st.markdown("---")

# 🔥🔥🔥 CZYSTY BANER BIZNESOWY (Z PRZYCISKIEM WHATSAPP) 🔥🔥🔥
whatsapp_number = "447000000000" # <--- ZMIEŃ NA SWÓJ BRYTYJSKI NUMER BEZ PLUSA (np. 447717219718)

if lang == "EN":
    st.error(f"""
    ### 🚨 TAX YEAR ENDS ON APRIL 5TH! Don't leave your money with HMRC. 🚨
    Whether you are an Agency Worker or **Self-Employed**, you could be owed hundreds of pounds in tax relief for mileage, uniforms, and work expenses.
    
    Need help claiming your tax refund or filing your Self-Assessment before the deadline? I can do it for you quickly and securely.
    
    👉 **[CLICK HERE TO WHATSAPP ME NOW](https://wa.me/{whatsapp_number})** | A Counting Pro
    """)
else:
    st.error(f"""
    ### 🚨 ROK PODATKOWY KOŃCZY SIĘ 5 KWIETNIA! Nie zostawiaj pieniędzy w urzędzie. 🚨
    Nieważne czy pracujesz przez agencję (PAYE) czy jesteś **Self-Employed**. HMRC prawdopodobnie wisi Ci setki funtów zwrotu za mile, pranie uniformu i koszty pracy.
    
    Nie wiesz jak wypełnić formularz P87 lub poprawnie złożyć rozliczenie Self-Assessment? Zrobię to za Ciebie szybko i bezbłędnie przed upływem terminu.
    
    👉 **[KLIKNIJ TU I NAPISZ DO MNIE NA WHATSAPP](https://wa.me/{whatsapp_number})** | A Counting Pro
    """)

st.markdown(f"<p style='text-align: center; color: grey;'>© {date.today().year} A Counting Pro | Financial health is mental wealth</p>", unsafe_allow_html=True)
