from PyPDF2 import PdfFileReader
from PyPDF2 import utils as pdf_utils
import re
from bs4 import BeautifulSoup, NavigableString
import requests
import datetime
import pandas as pd
import logging


class ExtractTextFromPDFError(Exception):
    """Raised when there are no words in pdf"""
    pass


########## FUNCTIONS ##########


def get_element_text_only(element):
    """returns the text of this specific element only without children text"""
    text_list = [child_elem for child_elem in element if isinstance(child_elem, NavigableString)]
    text_list = list(filter(('\n').__ne__, text_list))
    text = text_list[0].replace('\n', '')
    return text.lstrip()


def get_n_pages(soup):
    try:
        n_pages = soup.find('a', title="Go to last page", href=True)['href'].split("=")[-1]
        return int(n_pages) + 1
    except:
        return 1


def get_soup_for_date_and_page(start_date: str, end_date: str, page: int):
    try:
        url_str = f'https://www.finra.org/arbitration-mediation/arbitration-awards-online?aao_radios=all&field_case_id_text=&search=&field_forum_tax=All&field_special_case_type_tax=All&field_core_official_dt%5Bmin%5D={start_date}&field_core_official_dt%5Bmax%5D={end_date}&page={page}'
        html_txt = requests.get(url_str).text
        return BeautifulSoup(html_txt, 'lxml')
    except requests.exceptions.ConnectionError:
        msg = 'Could Not Reach Finra\'s website. Check internet conection'
        logging.critical(msg)
        print(msg)
        exit(1)


def get_hearing_site(document):
    str_elements = [str(elem) for elem in document.find_all('div')]
    hearing_site_bool = ['Hearing Site' in elem for elem in str_elements]
    hearing_site_idx = [i for i, elem in enumerate(hearing_site_bool) if elem][-1]
    hearing_site = doc.find_all('div')[hearing_site_idx].text.split(':')[1]
    return hearing_site


def download_pdf(pdf_url):
    try:
        pdf_name = pdf_url.split('/')[-1]
        pdf_response = requests.get(pdf_url)
        path = '../documents/' + pdf_name
        with open(path, 'wb') as pdf:
            pdf.write(pdf_response.content)
        return path
    except requests.exceptions.ConnectionError:
        msg = f'{pdf_name}: Could not download file it might be because the internet connection failed during runtime'
        logging.error(msg)
        print(msg)
        pass


def clean_page_header_from_text(txt_to_clean: str):
    txt_to_clean = txt_to_clean.replace("\n", "")
    pattern = re.compile(
        r'FINRA Dispute Resolution Services\s?Arbitration No.  \d{1,2}-\d{3,5}\s?Award Page (\d{1,2}) of (\d{1,2})')
    matches = pattern.finditer(txt_to_clean)
    matches_list = [match for match in matches]
    for match in reversed(matches_list):
        txt_to_clean = txt_to_clean[0:match.span()[0]] + txt_to_clean[match.span()[1]:]
    return txt_to_clean


def extract_text_from_pdf(pdf_url):
    pdf_path = download_pdf(pdf_url)
    try:
        reader = PdfFileReader(pdf_path)
    except pdf_utils.PdfReadError:
        raise ExtractTextFromPDFError('Could not extract text from file')

    n_pages = reader.numPages

    # PDF to String
    text = ""
    for page in reader.pages:
        text += page.extractText()

    clean_text = clean_page_header_from_text(text)

    # Check text validity
    if re.search('\w', clean_text) is None or len(clean_text) < 200 * n_pages:
        raise ExtractTextFromPDFError('Could not extract text from file')
    return clean_text


def fill_award(txt: str, data_dict: dict):
    try:
        award_str = re.search(r"AWARD(.*)FEES|ARBITRATOR", txt).group(1)
        data_dict['Award'] = award_str.strip()
    except AttributeError:
        msg = f"{data_dict['Doc Num']}: Could not extract the field: award"
        logging.error(msg)
        print(msg)
        pass


def fill_nature_of_dispute(txt: str, data_dict: dict):
    try:
        nod_str = re.search(
            rf"Nature of the Dispute:[ ]*{ntr_dispt_opt} [a-z.]+ {ntr_dispt_opt}( [a-z.]+ {ntr_dispt_opt})?", txt).group(0)
        nod_str = nod_str.split(':')[1]
        data_dict['Nature of Dispute'] = nod_str.strip()
    except AttributeError:
        msg = f"{data_dict['Doc Num']}: Could not extract the field: nature of dispute"
        logging.error(msg)
        print(msg)
        pass


def fill_statement_of_claim_date(txt: str, data_dict: dict):
    try:
        case_info_str = re.search(r"CASE INFORMATION(.*)CASE SUMMARY", txt).group(1)
        soc_str = re.search(r"Statement of Claim(.*?)\.", case_info_str).group(0)
        soc_date = soc_str.split(":")[1]
        data_dict['Statement of Claim'] = soc_date.strip()
    except AttributeError:
        msg = f"{data_dict['Doc Num']}: Could not extract the field: statement of claim date"
        logging.error(msg)
        print(msg)
        pass


def fill_case_summary(txt: str, data_dict: dict):
    try:
        case_summary_str = re.search(r"CASE SUMMARY(.*)RELIEF REQUESTED", txt).group(1)
        data_dict['Case Summary'] = case_summary_str
        is_settled = [key_word in case_summary_str for key_word in is_settled_key_words]
        data_dict['is Settled'] = any(is_settled)
    except AttributeError:
        msg = f"{data_dict['Doc Num']}: Could not extract the field: case summary"
        logging.error(msg)
        print(msg)
        pass


def fill_relief_requested(txt: str, data_dict: dict):
    try:
        relief_requested_str = re.search(
            r"RELIEF REQUESTED(.*)In the Amended|In the Statement of Answer|At the hearing|OTHER ISSUES", txt).group(1)
        data_dict['Relief Requested'] = relief_requested_str
    except AttributeError:
        msg = f"{data_dict['Doc Num']}: Could not extract the field: relief requested"
        logging.error(msg)
        print(msg)
        pass


def fill_arbitration_panel(txt: str, data_dict: dict):
    try:
        arbitrators_str = re.search(
            r"(ARBITRATION PANEL|ARBITRATOR)(.*)I, the undersigned Arbitrator,", txt).group(2)
        pattern = re.compile(rf'(.*?){arbitrators_opt}')
        arbitrators = pattern.finditer(arbitrators_str)
        for arbitrator in arbitrators:
            name = arbitrator.group(1).strip('-')
            position = arbitrator.group(2).strip()
            post_fix = 2
            while data_dict.setdefault(position, name) != name:
                position = f'{position}-{post_fix}'
                post_fix += 1

    except AttributeError:
        msg = f"{data_dict['Doc Num']}: Could not extract the field: arbitrator"
        logging.error(msg)
        print(msg)
        pass

def fill_hearing_sessions_fields(txt: str, data_dict: dict):
    hearing_sessions_str = re.search(
        r"Hearing Session Fees and Assessments(.*)Total Hearing Session Fees", txt).group(1)
    n_pre_hearing = re.search(r'\((\d+)\) pre-hearing session[s]? with', hearing_sessions_str).group(1)
    data_dict['Pre-Hearing Num'] = n_pre_hearing

    hearing_str = re.search(
        r"Hearing[s]?:(.*)", hearing_sessions_str).group(1)
    pattern = re.compile(r'[ADFJMNOS][a-z*] [\d]{1,2}, [\d]{4}')
    hearing_dates = pattern.finditer(hearing_str)
    for date in hearing_dates:
        print(date)

############ CONFIGURATIONS #############

# Logging configurations
now = datetime.datetime.now()
strat_time_str = now.strftime('%m-%d-%Y_%H-%M-%S')
log_file = f'../logs/log_{strat_time_str}.log'
logging.basicConfig(filename=log_file, level=logging.INFO,
                    format='%(levelname)s: %(message)s')


start_date = datetime.datetime(2022, 3, 25)  # should be accepted as argument
end_date = datetime.datetime(2022, 4, 8)


ntr_dispt_opt = r'(Associated Person[s]?|Member[s]?|Customer[s]?|Non-Member[s]?)'  # nature of dispute options
arbitrators_opt = r'(Public Arbitrator, Presiding Chairperson|Public Arbitrator|Non-Public Arbitrator' \
                  r'|Sole Public Arbitrator)'
is_settled_key_words = ['settled', 'settlement', 'settle']

############## MAIN CODE ###############

start_date_str = start_date.strftime("%m-%d-%Y")
end_date_str = end_date.strftime("%m-%d-%Y")

date_range_str = f'{start_date_str}_till_{end_date_str}'

logging.info(f'LOGS FOR: {date_range_str}')
csv_path = f"../csv/{date_range_str}.csv"

start_date_str = start_date_str.replace('-', '/')
end_date_str = end_date_str.replace('-', '/')


# SCRAPE DATA
soup = get_soup_for_date_and_page(start_date_str, end_date_str, 0)
n_pages = get_n_pages(soup)

data = []
n_files = 0
n_failed_files = 0

for page in range(n_pages):

    soup = get_soup_for_date_and_page(start_date.strftime("%m/%d/%Y"), end_date.strftime("%m/%d/%Y"), page)
    documents_table = soup.find('tbody')
    docs = documents_table.find_all('tr')

    for doc in docs:
        doc_dict = {}

        # Document Number
        doc_num_link = doc.find('a')
        doc_dict['Doc Num'] = doc_num_link.text
        n_files += 1

        if True:
        # if doc_dict['Doc Num'] == '21-00833':
            print(f"{doc_dict['Doc Num']}...")

            doc_dict['Doc URL'] = 'https://www.finra.org' + doc_num_link['href']

            # Website Information
            participants_container = doc.find('div', class_="push-down-15")
            participants_info = participants_container.find_all('div')

            doc_dict['Claimants'] = get_element_text_only(participants_info[0])
            doc_dict['Claimant Represent'] = get_element_text_only(participants_info[1])
            doc_dict['Respondents'] = get_element_text_only(participants_info[2])
            doc_dict['Respondent Represent'] = get_element_text_only(participants_container)
            doc_dict['Award Date'] = doc.find('td', class_="views-field views-field-field-core-official-dt").text
            doc_dict['Hearing Site'] = get_hearing_site(doc)

            # Textual data from pdf
            try:
                pdf_text = extract_text_from_pdf(doc_dict['Doc URL'])

                fill_award(pdf_text, doc_dict)
                fill_nature_of_dispute(pdf_text, doc_dict)
                fill_statement_of_claim_date(pdf_text, doc_dict)
                fill_case_summary(pdf_text, doc_dict)
                fill_relief_requested(pdf_text, doc_dict)
                fill_arbitration_panel(pdf_text, doc_dict)
                fill_hearing_sessions_fields(pdf_text, doc_dict)

            except ExtractTextFromPDFError as e:
                err_msg = f"{doc_dict['Doc Num']}: {str(e)}"
                logging.error(err_msg)
                print(err_msg)
                n_failed_files += 1
            except PermissionError as e:
                err_msg = f"{doc_dict['Doc Num']}:" \
                          f" Permission denied: '../documents/{doc_dict['Doc Num']}.pdf'. Close file and try again"
                logging.error(err_msg)
                print(err_msg)
                n_failed_files += 1
            finally:
                data.append(doc_dict)


# SAVE DATA
data_df = pd.DataFrame(data).fillna("NO DATA")

data_df.to_csv(csv_path, index=False)

print(f'\nCSV Saved to {csv_path}')
print(f'\nCould not process {n_failed_files} files out of {n_files}')
