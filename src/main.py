from PyPDF2 import PdfFileReader
import re
from bs4 import BeautifulSoup, NavigableString
import requests
import datetime
import pandas as pd


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
    url_str = f'https://www.finra.org/arbitration-mediation/arbitration-awards-online?aao_radios=all&field_case_id_text=&search=&field_forum_tax=All&field_special_case_type_tax=All&field_core_official_dt%5Bmin%5D={start_date}&field_core_official_dt%5Bmax%5D={end_date}&page={page}'
    html_txt = requests.get(url_str).text
    return BeautifulSoup(html_txt, 'lxml')

def download_pdf(pdf_url):
    pdf_name = pdf_url.split('/')[-1]
    pdf_response = requests.get(pdf_url)
    with open('../reports/' + pdf_name, 'wb') as pdf:
        pdf.write(pdf_response.content)
    return pdf

def extract_textual_data_from_pdf(pdf_url):
    pdf_file_obj = download_pdf(pdf_url)
    reader = PdfFileReader(pdf_file_obj)
    # Extract clean text
    second_page = reader.getPage(1)

    txt = ""
    for page in reader.pages:
        txt += page.extractText()



start_date = datetime.datetime(2022, 3, 21)  # should be accepted as argument
end_date = datetime.datetime.now()

start_date_str = start_date.strftime("%m/%d/%Y")
end_date_str = end_date.strftime("%m/%d/%Y")

soup = get_soup_for_date_and_page(start_date_str, end_date_str, 0)
n_pages = get_n_pages(soup)

data = []

for page in range(n_pages):

    soup = get_soup_for_date_and_page(start_date_str, end_date_str, page)
    documents_table = soup.find('tbody')

    docs = documents_table.find_all('tr')

    for doc in docs:
        doc_dict = {}

        # Document Number
        doc_num_link = doc.find('a')
        doc_dict['doc_num'] = doc_num_link.text

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

        # Textual data from pdf
        # extract_textual_data_from_pdf(doc_dict['doc_url'])

        data.append(doc_dict)

data_df = pd.DataFrame(data)
start_date_str = start_date.strftime("%m-%d-%Y")
end_date_str = end_date.strftime("%m-%d-%Y")
csv_path = f"../csv/{start_date_str}_till_{end_date_str}.csv"
data_df.to_csv(csv_path, index=False)

########### PyPDF ###########

# report_path = '../reports/18-01953.pdf'
# output_path = 'out.txt'

# pdf = PdfFileReader(report_path)
# a = pdf.getPageLayout()
# page_1_obj = pdf.getPage(0)
# page_1_txt = page_1_obj.extractText()
#
# words = [sentence for sentence in re.split(' ', page_1_txt) if 'Claimants' in sentence]
# "Claimants"
# print(words)
#
# with open(output_path, 'w', encoding='utf-8') as output_file:
#     txt = ''
#     for page in pdf.pages:
#         txt += page.extractText()
#     # output_file.write(txt)
#
#     member_fees_str = re.search("Member Fees(.*)ARBITRAT", txt)
#     # print(member_fees_str.group(0))
#     output_file.write(member_fees_str.group(0))

# if __name__ == '__main__':
