from PyPDF2 import PdfFileReader
import re
from bs4 import BeautifulSoup, NavigableString
import requests
import datetime
import pandas as pd
import logging


class ExtractTextFromPDFError(Exception):
    """Raised when there are no words in pdf"""
    pass


def get_element_text_only(element):
    # returns the text of this specific element only without children text
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


def download_pdf(pdf_url):
    pdf_name = pdf_url.split('/')[-1]
    pdf_response = requests.get(pdf_url)
    path = '../documents/' + pdf_name
    with open(path, 'wb') as pdf:
        pdf.write(pdf_response.content)
    return path


def clean_page_header_from_text(txt_to_clean: str):
    txt_to_clean = txt_to_clean.replace("\n", "")
    pattern = re.compile(
        r'FINRA Dispute Resolution Services\s{0,1}Arbitration No.  \d{1,2}-\d{3,5}\s{0,1}Award Page (\d{1,2}) of (\d{1,2})')
    matches = pattern.finditer(txt_to_clean)
    matches_list = [match for match in matches]
    for match in reversed(matches_list):
        txt_to_clean = txt_to_clean[0:match.span()[0]] + txt_to_clean[match.span()[1]:]
    return txt_to_clean


def extract_text_from_pdf(pdf_url):
    pdf_path = download_pdf(pdf_url)
    pdf_name = pdf_path.split('/')[-1]
    reader = PdfFileReader(pdf_path)
    n_pages = reader.numPages
    # PDF to String
    text = ""
    for page in reader.pages:
        text += page.extractText()

    clean_text = clean_page_header_from_text(text)

    # Check PDF validity
    if re.search('\w', clean_text) is None or len(clean_text) < 200 * n_pages:
        raise ExtractTextFromPDFError('Could not extract text from file')
    return clean_text


############ CONFIGURATIONS #############

# Logging configurations
now = datetime.datetime.now()
strat_time_str = now.strftime('%m-%d-%Y_%H-%M-%S')
log_file = f'../logs/log_{strat_time_str}.log'
logging.basicConfig(filename=log_file, level=logging.INFO,
                    format='%(levelname)s: %(message)s')

start_date = datetime.datetime(2022, 3, 20)  # should be accepted as argument
end_date = datetime.datetime(2022, 4, 1)

start_date_str = start_date.strftime("%m-%d-%Y")
end_date_str = end_date.strftime("%m-%d-%Y")

date_range_str = f'{start_date_str}_till_{end_date_str}'

logging.info(f'LOGS FOR: {date_range_str}')
csv_path = f"../csv/{date_range_str}.csv"

############## MAIN CODE ###############
start_date_str = start_date_str.replace('-', '/')
end_date_str = end_date_str.replace('-', '/')

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
        try:
            doc_dict = {}

            # Document Number
            doc_num_link = doc.find('a')
            doc_dict['doc_num'] = doc_num_link.text
            n_files += 1
            if True:
            # if doc_dict['doc_num'] == '18-01349':
                print(f"{doc_dict['doc_num']}...")
                # Document URL
                doc_dict['doc_url'] = 'https://www.finra.org' + doc_num_link['href']

                # Participants Information
                participants_container = doc.find('div', class_="push-down-15")
                participants_info = participants_container.find_all('div')
                doc_dict['claimants'] = get_element_text_only(participants_info[0])
                doc_dict['claimant_represent'] = get_element_text_only(participants_info[1])
                doc_dict['respondents'] = get_element_text_only(participants_info[2])
                doc_dict['respondent_represent'] = get_element_text_only(participants_container)

                # Date
                doc_dict['date'] = doc.find('td', class_="views-field views-field-field-core-official-dt").text

                # Hearing Site
                doc_dict['Hearing_site'] = doc.find_all('div')[6].text.split(':')[1]

                # Textual data from pdf
                text = extract_text_from_pdf(doc_dict['doc_url'])

                doc_dict['award_str'] = re.search(r"AWARD(.*)FEES|ARBITRATOR", text).group(0)[5:-4]

                data.append(doc_dict)

        except ExtractTextFromPDFError as e:
            err_msg = f"{doc_dict['doc_num']}: {str(e)}"
            logging.error(err_msg)
            print(err_msg)
            n_failed_files += 1
        except PermissionError as e:
            err_msg = f"{doc_dict['doc_num']}: Permission denied: '../documents/21-02138.pdf'. Close file and try again"
            logging.error(err_msg)
            print(err_msg)
            n_failed_files += 1

data_df = pd.DataFrame(data)

data_df.to_csv(csv_path, index=False)

print(f'\nCSV Saved to {csv_path}')
print(f'\nCould not process {n_failed_files} files out of {n_files}')
