# %%
path = 'test_data/documents/pdfs/meetings/A_78_PV.51.pdf'
import pdfplumber

with pdfplumber.open(path) as pdf:
    all_text = ""
    for page in pdf.pages:
        all_text += page.extract_text() or ""
print(all_text)
# %%
# dump to txt file
with open('A_78_PV.51.txt', 'w') as f:
    f.write(all_text)