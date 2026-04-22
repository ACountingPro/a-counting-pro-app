import streamlit as st
import os
import pandas as pd
import requests
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


# ============================================================
# HMRC CONSTANTS (tax year 2025/26 and 2026/27)
# ============================================================
HMRC_RATE_PER_MILE_FIRST_10K = 0.45  # pierwsze 10,000 mil
HMRC_RATE_PER_MILE_ABOVE_10K = 0.25  # powyżej 10,000 mil
PERSONAL_ALLOWANCE = 12570            # kwota wolna od podatku
BASIC_RATE_LIMIT = 50270              # górna granica basic rate
BASIC_RATE_TAX = 0.20
HIGHER_RATE_TAX = 0.40
NI_CLASS4_LOWER = 12570               # próg Class 4 NI
NI_CLASS4_UPPER = 50270
NI_CLASS4_MAIN_RATE = 0.06            # 6% od 2024/25
NI_CLASS4_ADDITIONAL = 0.02           # 2% powyżej górnego progu


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


def get_tax_years():
    """Zwraca listę ostatnich 4 lat podatkowych (HMRC pozwala cofnąć się 4 lata)"""
    today = date.today()
    if today.month > 4 or (today.month == 4 and today.day >= 6):
        current_start_year = today.year
    else:
        current_start_year = today.year - 1

    years = []
    for i in range(5):
        year = current_start_year - i
        years.append(f"{year}/{year + 1}")
    return years


def calculate_mileage_expense(total_miles):
    """
    Liczy koszt mil wg stawek HMRC (45p do 10k, 25p powyżej).
    Stosuje się do obu ścieżek: PAYE (approved mileage allowance) i SE (simplified expenses).
    """
    if total_miles <= 10000:
        return total_miles * HMRC_RATE_PER_MILE_FIRST_10K
    else:
        return (10000 * HMRC_RATE_PER_MILE_FIRST_10K) + \
               ((total_miles - 10000) * HMRC_RATE_PER_MILE_ABOVE_10K)


def calculate_se_tax_saving(total_expenses, annual_profit_estimate):
    """
    Liczy oszczędność podatkową dla Self-Employed.
    Zwraca słownik: {income_tax_saving, ni_saving, total_saving, tax_band}
    """
    if annual_profit_estimate <= PERSONAL_ALLOWANCE:
        # SE poniżej personal allowance - nie płaci podatku ani NI Class 4
        return {
            "income_tax_saving": 0.0,
            "ni_saving": 0.0,
            "total_saving": 0.0,
            "tax_band": "below_allowance"
        }

    # Obliczamy ile z "expenses" zmniejszy dochód w poszczególnych progach
    profit_before = annual_profit_estimate
    profit_after = max(0, annual_profit_estimate - total_expenses)

    income_tax_saving = 0.0
    ni_saving = 0.0

    # Podatek dochodowy
    if profit_before > BASIC_RATE_LIMIT:
        # Część kosztu wpada w higher rate (40%)
        in_higher = max(0, min(total_expenses, profit_before - BASIC_RATE_LIMIT))
        income_tax_saving += in_higher * HIGHER_RATE_TAX
        remaining = total_expenses - in_higher
    else:
        remaining = total_expenses

    # Reszta w basic rate (20%), o ile jest nad Personal Allowance
    if remaining > 0 and profit_after < profit_before:
        in_basic = max(0, min(remaining,
                              min(profit_before, BASIC_RATE_LIMIT) - max(profit_after, PERSONAL_ALLOWANCE)))
        income_tax_saving += in_basic * BASIC_RATE_TAX

    # NI Class 4 (6% w paśmie 12,570 - 50,270, 2% powyżej)
    if profit_before > NI_CLASS4_UPPER:
        in_additional = max(0, min(total_expenses, profit_before - NI_CLASS4_UPPER))
        ni_saving += in_additional * NI_CLASS4_ADDITIONAL
        remaining_ni = total_expenses - in_additional
    else:
        remaining_ni = total_expenses

    if remaining_ni > 0 and profit_after < profit_before:
        in_main = max(0, min(remaining_ni,
                             min(profit_before, NI_CLASS4_UPPER) - max(profit_after, NI_CLASS4_LOWER)))
        ni_saving += in_main * NI_CLASS4_MAIN_RATE

    total_saving = income_tax_saving + ni_saving

    # Określ pasmo dla komunikatu
    if profit_before > BASIC_RATE_LIMIT:
        tax_band = "higher"
    elif profit_before > PERSONAL_ALLOWANCE:
        tax_band = "basic"
    else:
        tax_band = "below_allowance"

    return {
        "income_tax_saving": income_tax_saving,
        "ni_saving": ni_saving,
        "total_saving": total_saving,
        "tax_band": tax_band
    }


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


def create_pdf_paye(df, total_expense, uniform_amount, lang, tax_year):
    """PDF dla PAYE - raport do formularza P87"""
    pdf = FPDF()
    pdf.add_page()

    title = "P87 Tax Refund Report" if lang == "EN" else "Raport Zwrotu Podatku P87"
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, text=f"{title} - A Counting Pro", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 10)
    subtitle = "For PAYE workers (agency employees)" if lang == "EN" else "Dla pracownikow PAYE (agencyjnych)"
    pdf.cell(0, 6, text=remove_polish_chars(subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=9)
    today_str = date.today().strftime("%d/%m/%Y")
    line1 = (
        f"Generated: {today_str}  |  Tax Year: {tax_year}"
        if lang == "EN"
        else f"Wygenerowano: {today_str}  |  Rok Podatkowy: {tax_year}"
    )
    pdf.cell(0, 7, text=remove_polish_chars(line1), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    col_widths = [24, 30, 30, 30, 20, 26, 30]
    headers = (
        ["Date", "From", "To", "Purpose", "Miles", "Employer(p)", "Relief(GBP)"]
        if lang == "EN"
        else ["Data", "Skad", "Dokad", "Cel", "Mile", "Pracod.(p)", "Ulga(GBP)"]
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
        pdf.cell(0, 6, text=f"Total business miles: {total_miles_pdf:.1f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=f"Mileage allowance paid by employer: GBP {total_agency_paid:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        miles_line = f"Mileage Allowance Relief (for P87): GBP {total_expense:.2f}"
    else:
        pdf.cell(0, 6, text=remove_polish_chars(f"Calkowita suma mil: {total_miles_pdf:.1f}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=remove_polish_chars(f"Kwota zwrocona przez pracodawce: GBP {total_agency_paid:.2f}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        miles_line = f"Ulga podatkowa na przejazdy (do P87): GBP {total_expense:.2f}"

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
        pdf.cell(0, 8, text=f"TOTAL RELIEF (Enter in P87 form on Gov.uk): GBP {final_expense:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 8, text=remove_polish_chars(f"LACZNA ULGA (Wpisz w P87 na Gov.uk): GBP {final_expense:.2f}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    cash_refund = final_expense * BASIC_RATE_TAX
    if lang == "EN":
        pdf.cell(0, 10, text=f"ESTIMATED CASH REFUND TO YOUR ACCOUNT (20%): GBP {cash_refund:.2f} *", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 10, text=remove_polish_chars(f"SZACOWANA GOTOWKA NA TWOJE KONTO (20%): GBP {cash_refund:.2f} *"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    if lang == "EN":
        disclaimer = (
            "* IMPORTANT: This assumes you are on PAYE (agency employee) and pay Income Tax at basic rate. "
            "'Total Relief' is what you enter in the P87 form on Gov.uk. HMRC then refunds you 20% in cash. "
            "Assumes earnings above Personal Allowance (GBP 12,570). Final decision rests with HMRC."
        )
    else:
        disclaimer = (
            "* WAZNE: Zaklada zatrudnienie PAYE (pracownik agencji) i stawke podstawowa podatku. "
            "'Laczna Ulga' to wartosc do wpisania w formularzu P87 na Gov.uk. HMRC zwraca 20% w gotowce. "
            "Zaklada zarobki powyzej kwoty wolnej (GBP 12,570). Ostateczna decyzja nalezy do HMRC."
        )
    pdf.multi_cell(0, 5, text=remove_polish_chars(disclaimer))

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 8, text="Financial health is mental wealth | linktr.ee/ACountingPro",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    return bytes(pdf.output())


def create_pdf_se(total_miles, total_mileage_expense, other_expenses, annual_profit, tax_result, lang, tax_year):
    """PDF dla Self-Employed - szacowana oszczędność Self Assessment"""
    pdf = FPDF()
    pdf.add_page()

    title = "Self Assessment Tax Saving Estimate" if lang == "EN" else "Szacowana Oszczednosc Self Assessment"
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, text=f"{title} - A Counting Pro", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 10)
    subtitle = "For Self-Employed (Sole Traders)" if lang == "EN" else "Dla Samozatrudnionych (Sole Trader)"
    pdf.cell(0, 6, text=remove_polish_chars(subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", size=9)
    today_str = date.today().strftime("%d/%m/%Y")
    line1 = (
        f"Generated: {today_str}  |  Tax Year: {tax_year}"
        if lang == "EN"
        else f"Wygenerowano: {today_str}  |  Rok Podatkowy: {tax_year}"
    )
    pdf.cell(0, 7, text=remove_polish_chars(line1), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    # Sekcja: dane wejściowe
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, text=remove_polish_chars("Your input:" if lang == "EN" else "Twoje dane:"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"Business miles: {total_miles:.0f}" if lang == "EN" else f"Mile biznesowe: {total_miles:.0f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"Other business expenses: GBP {other_expenses:.2f}" if lang == "EN" else f"Inne koszty firmowe: GBP {other_expenses:.2f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"Estimated annual profit: GBP {annual_profit:.2f}" if lang == "EN" else f"Szacowany roczny zysk: GBP {annual_profit:.2f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    # Sekcja: koszty
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, text=remove_polish_chars(
        "Allowable expenses (Self Assessment):" if lang == "EN" else "Koszty uzyskania przychodu (Self Assessment):"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"Mileage (simplified expenses): GBP {total_mileage_expense:.2f}" if lang == "EN" else f"Mile (uproszczone koszty): GBP {total_mileage_expense:.2f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"Other expenses: GBP {other_expenses:.2f}" if lang == "EN" else f"Inne koszty: GBP {other_expenses:.2f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    total_expenses = total_mileage_expense + other_expenses
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"TOTAL expenses (enter in SA103): GBP {total_expenses:.2f}" if lang == "EN" else f"RAZEM koszty (do SA103): GBP {total_expenses:.2f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)

    # Sekcja: oszczędność
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, text=remove_polish_chars(
        "Estimated tax saving:" if lang == "EN" else "Szacowana oszczednosc podatkowa:"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"Income Tax saved: GBP {tax_result['income_tax_saving']:.2f}" if lang == "EN" else f"Oszczednosc na Income Tax: GBP {tax_result['income_tax_saving']:.2f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, text=remove_polish_chars(
        f"Class 4 NI saved: GBP {tax_result['ni_saving']:.2f}" if lang == "EN" else f"Oszczednosc na NI Class 4: GBP {tax_result['ni_saving']:.2f}"
    ), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    if lang == "EN":
        pdf.cell(0, 10, text=f"TOTAL ESTIMATED SAVING: GBP {tax_result['total_saving']:.2f} *",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 10, text=remove_polish_chars(f"LACZNA SZACOWANA OSZCZEDNOSC: GBP {tax_result['total_saving']:.2f} *"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    if lang == "EN":
        disclaimer = (
            "* IMPORTANT: Self-Employed do NOT file P87. You file Self Assessment (SA100 + SA103) annually. "
            "This is an estimate of tax saving, not a cash refund. You pay less tax because your profit is lower. "
            "Assumes Class 4 NI at main rate (6%). Final decision rests with HMRC. "
            "For accurate records throughout the year, use A Counting Go app (acountinggo.netlify.app)."
        )
    else:
        disclaimer = (
            "* WAZNE: Samozatrudnieni NIE skladaja P87. Skladasz Self Assessment (SA100 + SA103) raz w roku. "
            "To jest szacunek oszczednosci, nie zwrot gotowki. Placisz mniej podatku, bo Twoj zysk jest nizszy. "
            "Zaklada NI Class 4 w stawce podstawowej (6%). Ostateczna decyzja nalezy do HMRC. "
            "Do codziennej ewidencji przez caly rok uzyj aplikacji A Counting Go (acountinggo.netlify.app)."
        )
    pdf.multi_cell(0, 5, text=remove_polish_chars(disclaimer))

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 8, text="Financial health is mental wealth | linktr.ee/ACountingPro",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    return bytes(pdf.output())


# ============================================================
# SESSION STATE
# ============================================================
if "history" not in st.session_state or "Expense" not in st.session_state.history.columns:
    st.session_state.history = pd.DataFrame(
        columns=["Date", "From", "To", "Purpose", "Miles", "Agency", "Expense", "TaxYear"]
    )

if "email_submitted" not in st.session_state:
    st.session_state.email_submitted = False

# ============================================================
# SIDEBAR
# ============================================================
lang = st.sidebar.selectbox("Choose Language / Wybierz Język", ("EN", "PL"))
EN = lang == "EN"

tax_years_list = get_tax_years()
selected_tax_year = st.sidebar.selectbox(
    "Tax Year / Rok Podatkowy" if EN else "Rok Podatkowy / Tax Year",
    tax_years_list,
    help="HMRC allows claims up to 4 years back" if EN else "HMRC pozwala rozliczyć się do 4 lat wstecz"
)

# ============================================================
# CSS
# ============================================================
css = """
<style>
/* ====== THEME RESET: wymuszamy spójny wygląd niezależnie od dark/light mode ====== */
.stApp { background-color: #fcfaf5 !important; color: #002147 !important; }
.stApp * { color: #002147 !important; }

/* Brand: tytuły i nagłówki */
h1, h2, h3, h4, h5, h6 { color: #002147 !important; font-family: Georgia, serif; }

/* Standardowe paragrafy i teksty */
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span { color: #002147 !important; }

/* Przyciski: granat + złoto */
.stButton>button { background-color: #002147 !important; color: #D4AF37 !important; border-radius: 8px !important; border: 2px solid #D4AF37 !important; font-weight: bold !important; }
.stButton>button:hover { background-color: #D4AF37 !important; color: #002147 !important; }
.stButton>button * { color: inherit !important; }

/* Link buttons (nasza promocja) */
.stLinkButton>a, a[data-testid="stLinkButton-secondary"], a[data-testid="stLinkButton-primary"] {
    background-color: #002147 !important;
    color: #D4AF37 !important;
    border: 2px solid #D4AF37 !important;
    font-weight: bold !important;
}
.stLinkButton>a *, a[data-testid^="stLinkButton"] * { color: #D4AF37 !important; }

/* Taby */
.stTabs [data-baseweb="tab-list"] button { color: #002147 !important; }
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { background-color: #002147 !important; color: #D4AF37 !important; }
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] * { color: #D4AF37 !important; }

/* Metryki */
[data-testid="stMetricValue"] { color: #D4AF37 !important; }
[data-testid="stMetricLabel"] { color: #002147 !important; }

/* Radio buttons */
.stRadio label, .stRadio div { color: #002147 !important; }

/* Inputy: pola tekstowe, liczbowe, daty, selectboxy */
.stTextInput input, .stNumberInput input, .stDateInput input, .stSelectbox, .stSelectbox * {
    color: #002147 !important;
    background-color: #ffffff !important;
}
.stTextInput label, .stNumberInput label, .stDateInput label, .stSelectbox label {
    color: #002147 !important;
}

/* Checkbox */
.stCheckbox label, .stCheckbox span { color: #002147 !important; }

/* Sidebar też jasny */
section[data-testid="stSidebar"] { background-color: #f5f0e1 !important; }
section[data-testid="stSidebar"] * { color: #002147 !important; }

/* Alerty Streamlit: info / success / warning / error */
div[data-baseweb="notification"] { color: #002147 !important; }
div[data-baseweb="notification"] * { color: #002147 !important; }
.stAlert { color: #002147 !important; }
.stAlert * { color: #002147 !important; }

/* Karty brandowe */
.brand-card { background: #fffdf8 !important; border: 1px solid #e6dcc6; border-radius: 14px; padding: 18px; box-shadow: 0 4px 14px rgba(0, 33, 71, 0.06); color: #002147 !important; }
.brand-card * { color: #002147 !important; }

/* Boxy promocyjne i informacyjne */
.cash-box, .saving-box { background-color: #e8f5e9 !important; border-left: 5px solid #28a745; padding: 15px; border-radius: 5px; margin-top: 15px; color: #155724 !important; }
.cash-box *, .saving-box * { color: #155724 !important; }

.expense-box { background-color: #e3f2fd !important; border-left: 5px solid #1565c0; padding: 12px; border-radius: 5px; margin-top: 10px; color: #0d3561 !important; }
.expense-box * { color: #0d3561 !important; }

.info-warning-box { background-color: #fff3cd !important; border-left: 5px solid #ffc107; padding: 15px; border-radius: 5px; margin-top: 15px; color: #664d03 !important; }
.info-warning-box * { color: #664d03 !important; }

.se-redirect-box { background-color: #e8f5e9 !important; border: 2px solid #28a745; padding: 20px; border-radius: 10px; margin-top: 20px; margin-bottom: 20px; color: #155724 !important; }
.se-redirect-box * { color: #155724 !important; }

.email-gate-box { background-color: #fff8e1 !important; border: 2px solid #D4AF37; padding: 20px; border-radius: 10px; margin-top: 20px; margin-bottom: 20px; color: #002147 !important; }
.email-gate-box * { color: #002147 !important; }

.app-promo-box { background-color: #e8f5e9 !important; border-left: 5px solid #28a745; padding: 20px; border-radius: 5px; margin-top: 20px; margin-bottom: 15px; color: #155724 !important; }
.app-promo-box * { color: #155724 !important; }

.ebook-promo-box { background-color: #fff8e1 !important; border-left: 5px solid #D4AF37; padding: 20px; border-radius: 5px; margin-top: 20px; margin-bottom: 15px; color: #002147 !important; }
.ebook-promo-box * { color: #002147 !important; }

.linktree-promo-box { background-color: #e3f2fd !important; border-left: 5px solid #1565c0; padding: 20px; border-radius: 5px; margin-top: 20px; margin-bottom: 15px; color: #0d3561 !important; }
.linktree-promo-box * { color: #0d3561 !important; }

/* Formularze wewnątrz boxów muszą pozostać czytelne */
.stForm { background-color: transparent !important; }
.stForm input, .stForm textarea { color: #002147 !important; background-color: #ffffff !important; }
.stForm label { color: #002147 !important; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================
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
    sub = "For Care, Cleaning, NHS & self-employed" if EN else "Dla branży Care, Cleaning, NHS i samozatrudnionych"
    st.markdown(f"<p style='text-align:center;color:#002147;'><b>{sub}</b></p>", unsafe_allow_html=True)

st.write("---")

# ============================================================
# STATUS SELECTION (przed tabami)
# ============================================================
if EN:
    st.markdown("### 👤 Choose your situation")
    emp_status = st.radio(
        "Your employment status:",
        ["I'm PAYE (agency employee) — care, cleaning, NHS, delivery",
         "I'm Self-Employed (Sole Trader) — cleaner, carer, driver on my own"],
        help="PAYE workers claim via P87 form. Self-Employed claim via Self Assessment (SA103)."
    )
else:
    st.markdown("### 👤 Wybierz swoją sytuację")
    emp_status = st.radio(
        "Twój status zatrudnienia:",
        ["Jestem na PAYE (pracownik agencji) — opieka, sprzątanie, NHS, dostawy",
         "Jestem Self-Employed (Sole Trader) — sprzątaczka, opiekunka, kurier na swoim"],
        help="PAYE rozlicza się przez P87. Self-Employed przez Self Assessment (SA103)."
    )

is_paye = "PAYE" in emp_status
st.write("---")

# ============================================================
# PAYE PATH
# ============================================================
if is_paye:

    if EN:
        st.info(f"📅 PAYE Refund Checker — tax year **{selected_tax_year}**. Calculate your P87 refund. HMRC allows claims up to 4 years back.")
    else:
        st.info(f"📅 Kalkulator zwrotu PAYE — rok podatkowy **{selected_tax_year}**. Policz swój zwrot P87. HMRC pozwala rozliczyć się do 4 lat wstecz.")

    tab1, tab2, tab3 = st.tabs([
        "🧮 Calculator" if EN else "🧮 Kalkulator",
        "📊 Result & Report" if EN else "📊 Wynik i Raport",
        "📘 How to Claim" if EN else "📘 Jak odzyskać",
    ])

    with tab1:
        if EN:
            st.markdown(f"##### Calculating P87 refund for tax year {selected_tax_year}")
        else:
            st.markdown(f"##### Liczymy zwrot P87 dla roku podatkowego {selected_tax_year}")

        col_in, col_math = st.columns([1, 1])

        with col_in:
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

            a = st.number_input("Employer rate (p/mile)" if EN else "Stawka pracodawcy (p/mile)",
                                min_value=0.0, max_value=100.0, value=25.0, step=0.5,
                                help="How much your employer/agency pays per mile"
                                if EN else "Ile agencja/pracodawca płaci za milę")

            hmrc_total = calculate_mileage_expense(m)
            agency_total = m * (a / 100)
            expense = max(0.0, hmrc_total - agency_total)

        with col_math:
            st.write("#### 🔍 Calculation" if EN else "#### 🔍 Wyliczenia")
            st.write(f"**{'Miles counted' if EN else 'Liczba mil'}:** {m:.1f}")
            st.write(f"**{'HMRC Allowance' if EN else 'Limit HMRC'}:** £{hmrc_total:.2f}")
            st.write(f"**{'Employer paid' if EN else 'Pracodawca zapłacił'}:** £{agency_total:.2f}")

            st.write("---")

            if lang == "EN":
                st.markdown(f"""
                <div class="expense-box">
                    <b>Relief to enter in P87:</b> £{expense:.2f}<br>
                    <small>This number goes to the HMRC P87 form</small>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="expense-box">
                    <b>Ulga do wpisania w P87:</b> £{expense:.2f}<br>
                    <small>Tę liczbę wpisujesz w formularzu HMRC P87</small>
                </div>
                """, unsafe_allow_html=True)

            cash_estimate = expense * BASIC_RATE_TAX
            label = "Estimated CASH refund" if EN else "Szacowana GOTÓWKA na konto"
            st.markdown(f"""
            <div class="cash-box">
                <h4 style="color:#155724; margin:0;">💸 {label}: £{cash_estimate:.2f}</h4>
            </div>
            """, unsafe_allow_html=True)

        if st.button("➕ Add to Report" if EN else "➕ Dodaj do Raportu", use_container_width=True):
            new_row = pd.DataFrame({
                "Date": [d], "From": [from_loc], "To": [to_loc], "Purpose": [purpose],
                "Miles": [m], "Agency": [a], "Expense": [expense], "TaxYear": [selected_tax_year]
            })
            st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)
            st.toast("✅ Added!" if EN else "✅ Dodano!")

    with tab2:
        if "TaxYear" in st.session_state.history.columns:
            df_filtered = st.session_state.history[st.session_state.history["TaxYear"] == selected_tax_year]
        else:
            df_filtered = st.session_state.history

        if not df_filtered.empty:
            total_m_expense = df_filtered["Expense"].sum()
            add_uniform = st.checkbox("Include uniform laundry rate (Care £60)" if EN
                                     else "Dolicz ryczałt za pranie uniformu (Care £60)")
            uniform_amount = 60.0 if add_uniform else 0.0

            final_total = total_m_expense + uniform_amount
            cash_back_total = final_total * BASIC_RATE_TAX

            st.write(f"**{'Tax Year' if EN else 'Rok podatkowy'}: {selected_tax_year}**")
            st.write("---")

            c1, c2 = st.columns(2)
            c1.metric("Total Relief (P87)" if EN else "Ulga P87", f"£{final_total:.2f}")
            c2.metric("Estimated Cash Refund" if EN else "Szacowana Gotówka", f"£{cash_back_total:.2f}")

            st.write("---")

            if cash_back_total < 25.0:
                msg = "Your claim is small, but still worth recovering!" if EN else "Twój zwrot jest niewielki, ale wciąż warto go odzyskać!"
                st.info(msg)
            elif cash_back_total <= 120.0:
                msg = "It is profitable to claim this!" if EN else "Zdecydowanie opłaca się po to sięgnąć!"
                st.success(msg)
            else:
                msg = "Serious money! Worth claiming back." if EN else "To poważne pieniądze! Warto je odzyskać."
                st.warning(msg)

            st.write("---")

            # EMAIL GATE
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

                with st.form("email_form_paye", clear_on_submit=False):
                    email_input = st.text_input("Email" if EN else "Twój email", placeholder="twoj@email.com")
                    checkbox_consent = st.checkbox(
                        "I agree to receive HMRC tips from A Counting Pro" if EN
                        else "Zgadzam się na otrzymywanie wskazówek HMRC od A Counting Pro"
                    )
                    submit_btn = st.form_submit_button(
                        "📧 Send me the PDF" if EN else "📧 Wyślij mi PDF",
                        use_container_width=True, type="primary"
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
                pdf_bytes = create_pdf_paye(df_filtered, total_m_expense, uniform_amount, lang, selected_tax_year)
                st.download_button(
                    label="📥 Download FREE PDF" if EN else "📥 Pobierz DARMOWY PDF",
                    data=pdf_bytes,
                    file_name=f"A_Counting_Pro_P87_{selected_tax_year.replace('/', '-')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

                st.write("---")

                # Promocje dla PAYE
                if EN:
                    st.markdown("""
                    <div class="ebook-promo-box">
                        <h4 style='color: #002147; margin-top: 0;'>📘 Want step-by-step guidance?</h4>
                        <p style='color: #002147;'>The P87 E-book walks you through the HMRC form, screen by screen.</p>
                        <p style='color: #002147; margin-bottom: 0;'><b>Only £7.99 — save hours of stress.</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("📘 Get P87 E-book — £7.99", "https://linktr.ee/ACountingPro", use_container_width=True)
                else:
                    st.markdown("""
                    <div class="ebook-promo-box">
                        <h4 style='color: #002147; margin-top: 0;'>📘 Potrzebujesz przewodnika krok po kroku?</h4>
                        <p style='color: #002147;'>E-book P87 prowadzi Cię przez formularz HMRC, ekran po ekranie.</p>
                        <p style='color: #002147; margin-bottom: 0;'><b>Tylko £7.99, oszczędzisz godziny stresu.</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("📘 Kup E-book P87 — £7.99", "https://linktr.ee/ACountingPro", use_container_width=True)

                if EN:
                    st.markdown("""
                    <div class="linktree-promo-box">
                        <h4 style='color: #002147; margin-top: 0;'>👑 Need more help?</h4>
                        <p style='color: #002147;'>Check all my services on Linktree.</p>
                        <p style='color: #002147; margin-bottom: 0;'><b>Financial health is mental wealth 🧘‍♀️</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("👑 See all services", "https://linktr.ee/ACountingPro", use_container_width=True)
                else:
                    st.markdown("""
                    <div class="linktree-promo-box">
                        <h4 style='color: #002147; margin-top: 0;'>👑 Potrzebujesz większego wsparcia?</h4>
                        <p style='color: #002147;'>Sprawdź wszystkie moje usługi na Linktree.</p>
                        <p style='color: #002147; margin-bottom: 0;'><b>Financial health is mental wealth 🧘‍♀️</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("👑 Zobacz wszystkie usługi", "https://linktr.ee/ACountingPro", use_container_width=True)

        else:
            if EN:
                st.info(f"No data for tax year {selected_tax_year} yet. Add a trip in the Calculator first.")
            else:
                st.info(f"Brak danych dla roku podatkowego {selected_tax_year}. Najpierw dodaj trasę w Kalkulatorze.")

    with tab3:
        st.markdown("### 📘 How to claim P87 refund" if EN else "### 📘 Jak odzyskać zwrot z P87")
        if EN:
            st.write("1. **Check for free** — use this calculator")
            st.write("2. **Get P87 E-book (£7.99)** — do it yourself with step-by-step guidance")
            st.write("3. **Or let us do it for you** — VIP Service (£149) or full bookkeeping")
            st.write("")
            st.link_button("👉 See all options", "https://linktr.ee/ACountingPro", use_container_width=True)
        else:
            st.write("1. **Sprawdź za darmo** — użyj tego kalkulatora")
            st.write("2. **Kup E-book P87 (£7.99)** — zrób to samodzielnie z przewodnikiem krok po kroku")
            st.write("3. **Lub zleć to nam** — Usługa VIP (£149) lub pełna księgowość")
            st.write("")
            st.link_button("👉 Zobacz wszystkie opcje", "https://linktr.ee/ACountingPro", use_container_width=True)


# ============================================================
# SELF-EMPLOYED PATH (NOWA LOGIKA)
# ============================================================
else:

    if EN:
        st.info(f"📅 Self Assessment estimate for tax year **{selected_tax_year}**. See your estimated tax saving based on business miles and expenses.")
    else:
        st.info(f"📅 Szacunek Self Assessment dla roku podatkowego **{selected_tax_year}**. Zobacz szacowaną oszczędność podatkową z mil biznesowych i kosztów.")

    tab1, tab2, tab3 = st.tabs([
        "🧮 Calculator" if EN else "🧮 Kalkulator",
        "📊 Your Saving" if EN else "📊 Twoja oszczędność",
        "📘 Next Steps" if EN else "📘 Co dalej",
    ])

    with tab1:
        if EN:
            st.markdown("##### Quick Self Assessment estimate")
            st.markdown("*This is a quick estimate. For daily tracking of miles and receipts all year round, use **A Counting Go** (£4.99/month).*")
        else:
            st.markdown("##### Szybki szacunek Self Assessment")
            st.markdown("*To jest szybki szacunek. Do codziennego zapisywania mil i paragonów przez cały rok użyj **A Counting Go** (£4.99/mc).*")

        st.write("---")

        col_in, col_math = st.columns([1, 1])

        with col_in:
            st.markdown("#### 🚗 " + ("Business miles" if EN else "Mile biznesowe"))
            annual_miles = st.number_input(
                "Estimated business miles this year" if EN else "Szacowane mile biznesowe w tym roku",
                min_value=0.0, value=4000.0, step=100.0,
                help="Miles driven for work (to clients, between jobs, etc.)"
                if EN else "Mile przejechane w pracy (do klientów, między zleceniami itp.)"
            )

            st.markdown("#### 🧾 " + ("Other expenses" if EN else "Inne koszty firmowe"))
            other_expenses = st.number_input(
                "Other business expenses (£)" if EN else "Inne koszty firmowe (£)",
                min_value=0.0, value=0.0, step=50.0,
                help="Cleaning products, uniform, professional fees, phone bills (business %), etc."
                if EN else "Środki czystości, uniform, składki zawodowe, część telefonu itp."
            )

            st.markdown("#### 💰 " + ("Estimated profit" if EN else "Szacowany zysk"))
            annual_profit = st.number_input(
                "Estimated annual profit BEFORE expenses (£)" if EN else "Szacowany roczny zysk PRZED odliczeniem kosztów (£)",
                min_value=0.0, value=20000.0, step=500.0,
                help="Your estimated total income from self-employment, before deducting expenses"
                if EN else "Twój szacowany całkowity dochód z samozatrudnienia, przed odliczeniem kosztów"
            )

        with col_math:
            mileage_expense = calculate_mileage_expense(annual_miles)
            total_expenses = mileage_expense + other_expenses
            tax_result = calculate_se_tax_saving(total_expenses, annual_profit)

            st.write("#### 🔍 " + ("Your numbers" if EN else "Twoje liczby"))
            st.write(f"**{'Business miles' if EN else 'Mile biznesowe'}:** {annual_miles:.0f}")
            st.write(f"**{'Mileage expense (simplified)' if EN else 'Koszt mil (uproszczony)'}:** £{mileage_expense:.2f}")
            st.write(f"**{'Other expenses' if EN else 'Inne koszty'}:** £{other_expenses:.2f}")
            st.write(f"**{'TOTAL expenses' if EN else 'RAZEM koszty'}:** £{total_expenses:.2f}")

            st.write("---")

            if lang == "EN":
                st.markdown(f"""
                <div class="expense-box">
                    <b>Total allowable expenses (SA103):</b> £{total_expenses:.2f}<br>
                    <small>This number reduces your taxable profit in Self Assessment</small>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="expense-box">
                    <b>Łączne koszty uzyskania (SA103):</b> £{total_expenses:.2f}<br>
                    <small>Ta kwota zmniejsza Twój dochód do opodatkowania w Self Assessment</small>
                </div>
                """, unsafe_allow_html=True)

            if tax_result["tax_band"] == "below_allowance":
                if EN:
                    st.markdown("""
                    <div class="info-warning-box">
                        <b>📌 Below tax threshold</b><br>
                        Your profit is below the Personal Allowance (£12,570). You don't pay Income Tax or Class 4 NI.
                        Still file Self Assessment to stay compliant.
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="info-warning-box">
                        <b>📌 Poniżej progu podatkowego</b><br>
                        Twój zysk jest poniżej kwoty wolnej (£12,570). Nie płacisz Income Tax ani NI Class 4.
                        Nadal musisz złożyć Self Assessment.
                    </div>
                    """, unsafe_allow_html=True)
            else:
                saving_label = "Estimated tax saving" if EN else "Szacowana oszczędność podatkowa"
                st.markdown(f"""
                <div class="saving-box">
                    <h4 style="color:#155724; margin:0;">💸 {saving_label}: £{tax_result['total_saving']:.2f}</h4>
                    <small>
                    Income Tax: £{tax_result['income_tax_saving']:.2f}
                    • NI Class 4: £{tax_result['ni_saving']:.2f}
                    </small>
                </div>
                """, unsafe_allow_html=True)

        st.session_state.se_data = {
            "annual_miles": annual_miles,
            "mileage_expense": mileage_expense,
            "other_expenses": other_expenses,
            "annual_profit": annual_profit,
            "tax_result": tax_result,
            "total_expenses": total_expenses
        }

    with tab2:
        if "se_data" not in st.session_state:
            if EN:
                st.info("Fill in the calculator first, then come back here for your full saving summary.")
            else:
                st.info("Najpierw wypełnij kalkulator, potem wróć tutaj po pełne podsumowanie.")
        else:
            se = st.session_state.se_data
            tax_result = se["tax_result"]

            st.write(f"**{'Tax Year' if EN else 'Rok podatkowy'}: {selected_tax_year}**")
            st.write("---")

            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Business miles" if EN else "Mile biznesowe",
                f"{se['annual_miles']:.0f}"
            )
            c2.metric(
                "Total expenses" if EN else "Łączne koszty",
                f"£{se['total_expenses']:.2f}"
            )
            c3.metric(
                "Tax saving" if EN else "Oszczędność",
                f"£{tax_result['total_saving']:.2f}"
            )

            st.write("---")

            # INFO BOX: różnica PAYE vs SE
            if EN:
                st.markdown("""
                <div class="info-warning-box">
                    <b>🔑 Important: how Self-Employed tax relief works</b><br><br>
                    Unlike PAYE workers, you do NOT get a cash refund from HMRC for your miles.<br><br>
                    Instead: your mileage is a <b>business expense</b> that reduces your taxable profit.
                    You pay less Income Tax and Class 4 NI because your profit is lower.<br><br>
                    You file this in <b>Self Assessment (SA103)</b> once a year, not P87.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="info-warning-box">
                    <b>🔑 Ważne: jak działa ulga dla Self-Employed</b><br><br>
                    W odróżnieniu od pracowników PAYE, NIE dostajesz gotówki zwrotem od HMRC za swoje mile.<br><br>
                    Zamiast tego: mile są <b>kosztem firmowym</b>, który zmniejsza Twój dochód do opodatkowania.
                    Płacisz mniej Income Tax i NI Class 4, bo Twój zysk jest niższy.<br><br>
                    Wpisujesz to w <b>Self Assessment (SA103)</b> raz w roku, nie w P87.
                </div>
                """, unsafe_allow_html=True)

            st.write("---")

            # EMAIL GATE
            if not st.session_state.email_submitted:
                if EN:
                    st.markdown("""
                    <div class="email-gate-box">
                        <h3 style='color: #002147; margin-top: 0;'>📧 Your estimate PDF is ready!</h3>
                        <p style='color: #002147; margin-bottom: 0;'>Enter your email below and I'll send you the PDF estimate + next steps.</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="email-gate-box">
                        <h3 style='color: #002147; margin-top: 0;'>📧 Twój PDF z szacunkiem jest gotowy!</h3>
                        <p style='color: #002147; margin-bottom: 0;'>Podaj email, a wyślę Ci PDF + wskazówki co dalej.</p>
                    </div>
                    """, unsafe_allow_html=True)

                with st.form("email_form_se", clear_on_submit=False):
                    email_input = st.text_input("Email" if EN else "Twój email", placeholder="twoj@email.com")
                    checkbox_consent = st.checkbox(
                        "I agree to receive Self Assessment tips from A Counting Pro" if EN
                        else "Zgadzam się na otrzymywanie wskazówek Self Assessment od A Counting Pro"
                    )
                    submit_btn = st.form_submit_button(
                        "📧 Send me the PDF" if EN else "📧 Wyślij mi PDF",
                        use_container_width=True, type="primary"
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
                pdf_bytes = create_pdf_se(
                    se["annual_miles"], se["mileage_expense"], se["other_expenses"],
                    se["annual_profit"], tax_result, lang, selected_tax_year
                )
                st.download_button(
                    label="📥 Download FREE PDF estimate" if EN else "📥 Pobierz DARMOWY PDF",
                    data=pdf_bytes,
                    file_name=f"A_Counting_Pro_SE_Estimate_{selected_tax_year.replace('/', '-')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

                st.write("---")

                # GŁÓWNY CTA DLA SE: A Counting Go
                if EN:
                    st.markdown("""
                    <div class="se-redirect-box">
                        <h3 style='color: #155724; margin-top: 0;'>🚗 Your next step: track everything, all year</h3>
                        <p style='color: #155724;'>This calculator is a quick estimate. For accurate Self Assessment, you need a record of EVERY business mile and receipt throughout the year.</p>
                        <p style='color: #155724;'><b>A Counting Go does it automatically:</b></p>
                        <ul style='color: #155724;'>
                            <li>GPS mileage tracking (no manual input)</li>
                            <li>Photograph receipts on the go</li>
                            <li>Year-end report ready for SA103</li>
                        </ul>
                        <p style='color: #155724; margin-bottom: 0;'><b>7 days free, then £4.99/month.</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("🚗 Start A Counting Go — 7 days free", "https://acountinggo.netlify.app", use_container_width=True)
                else:
                    st.markdown("""
                    <div class="se-redirect-box">
                        <h3 style='color: #155724; margin-top: 0;'>🚗 Twój następny krok: zapisuj wszystko, cały rok</h3>
                        <p style='color: #155724;'>Ten kalkulator to szybki szacunek. Do rzetelnego Self Assessment potrzebujesz ewidencji KAŻDEJ biznesowej mili i paragonu przez cały rok.</p>
                        <p style='color: #155724;'><b>A Counting Go robi to automatycznie:</b></p>
                        <ul style='color: #155724;'>
                            <li>GPS śledzi mile (nie musisz wpisywać ręcznie)</li>
                            <li>Zdjęcia paragonów w telefonie</li>
                            <li>Roczny raport gotowy do SA103</li>
                        </ul>
                        <p style='color: #155724; margin-bottom: 0;'><b>7 dni za darmo, potem £4.99/miesiąc.</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("🚗 Zacznij A Counting Go — 7 dni za darmo", "https://acountinggo.netlify.app", use_container_width=True)

                # CTA DODATKOWY: pełna obsługa
                if EN:
                    st.markdown("""
                    <div class="linktree-promo-box">
                        <h4 style='color: #002147; margin-top: 0;'>👑 Want me to file Self Assessment for you?</h4>
                        <p style='color: #002147;'>As your HMRC agent, I can prepare and submit SA100 + SA103 on your behalf. You send me your records, I do the rest.</p>
                        <p style='color: #002147; margin-bottom: 0;'><b>Financial health is mental wealth 🧘‍♀️</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("👑 Book a free consultation", "https://linktr.ee/ACountingPro", use_container_width=True)
                else:
                    st.markdown("""
                    <div class="linktree-promo-box">
                        <h4 style='color: #002147; margin-top: 0;'>👑 Chcesz, żebym złożyła za Ciebie Self Assessment?</h4>
                        <p style='color: #002147;'>Jako Agent HMRC mogę przygotować i wysłać SA100 + SA103 w Twoim imieniu. Ty podsyłasz dokumenty, resztę robię ja.</p>
                        <p style='color: #002147; margin-bottom: 0;'><b>Financial health is mental wealth 🧘‍♀️</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("👑 Umów bezpłatną konsultację", "https://linktr.ee/ACountingPro", use_container_width=True)

    with tab3:
        st.markdown("### 📘 " + ("Next steps for Self-Employed" if EN else "Co dalej, gdy jesteś Self-Employed"))
        if EN:
            st.write("1. **Register with HMRC** as Self-Employed (if not already)")
            st.write("2. **Track miles and receipts** throughout the year (use A Counting Go)")
            st.write("3. **File Self Assessment** (SA100 + SA103) by 31 January each year")
            st.write("4. **Pay any tax owed** by the same date")
            st.write("")
            st.write("**Tip**: MTD for Income Tax starts 6 April 2026 for those with income over £50,000. Quarterly reporting to HMRC.")
            st.write("")
            st.link_button("👉 See all options", "https://linktr.ee/ACountingPro", use_container_width=True)
        else:
            st.write("1. **Zarejestruj się w HMRC** jako Self-Employed (jeśli jeszcze tego nie zrobiłaś)")
            st.write("2. **Zapisuj mile i paragony** przez cały rok (użyj A Counting Go)")
            st.write("3. **Złóż Self Assessment** (SA100 + SA103) do 31 stycznia każdego roku")
            st.write("4. **Zapłać należny podatek** do tej samej daty")
            st.write("")
            st.write("**Ważne**: MTD for Income Tax startuje 6 kwietnia 2026 dla dochodów powyżej £50,000. Raportowanie kwartalne do HMRC.")
            st.write("")
            st.link_button("👉 Zobacz wszystkie opcje", "https://linktr.ee/ACountingPro", use_container_width=True)


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
if EN:
    st.error("### 🚀 NEW TAX YEAR 2026/27 IS HERE!\nYou can claim for the past 4 years. Don't leave your money at HMRC.")
else:
    st.error("### 🚀 NOWY ROK PODATKOWY 2026/27!\nMożesz odzyskać pieniądze za ostatnie 4 lata podatkowe. Nie zostawiaj gotówki w urzędzie.")

st.markdown(f"<p style='text-align:center;color:grey;'>© {date.today().year} A Counting Pro | Financial health is mental wealth</p>", unsafe_allow_html=True)