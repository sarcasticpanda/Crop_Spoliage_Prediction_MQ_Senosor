from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

source = Path(r'C:\Users\Lunar Panda\Downloads\UROP_Report_DRAFT_POLISHED.docx')
output = Path(r'C:\Users\Lunar Panda\Downloads\AP23110010439_UROP_CLA.docx')
doc = Document(source)

def set_cell_margins(cell, top=120, start=120, bottom=120, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in('w:tcMar')
    if margins is None:
        margins = OxmlElement('w:tcMar')
        tc_pr.append(margins)
    for edge, value in (('top',top),('start',start),('bottom',bottom),('end',end)):
        node = margins.find(qn(f'w:{edge}'))
        if node is None:
            node = OxmlElement(f'w:{edge}')
            margins.append(node)
        node.set(qn('w:w'), str(value))
        node.set(qn('w:type'), 'dxa')

def set_table_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn('w:tblBorders'))
    if borders is None:
        borders = OxmlElement('w:tblBorders')
        tbl_pr.append(borders)
    for edge in ('top','left','bottom','right','insideH','insideV'):
        tag = borders.find(qn(f'w:{edge}'))
        if tag is None:
            tag = OxmlElement(f'w:{edge}')
            borders.append(tag)
        tag.set(qn('w:val'),'single')
        tag.set(qn('w:sz'),'6')
        tag.set(qn('w:space'),'0')
        tag.set(qn('w:color'),'686868')

def set_cell_fill(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn('w:shd'))
    if shading is None:
        shading = OxmlElement('w:shd')
        tc_pr.append(shading)
    shading.set(qn('w:fill'), fill)

# Replace the single-author placeholder with a compact, readable team table.
paras = doc.paragraphs
submitted = next(p for p in paras if p.text.strip() == 'Submitted by')
old_author = next(p for p in paras if p.text.strip().startswith('Savari Kashyap'))
old_author._element.getparent().remove(old_author._element)
team = doc.add_table(rows=1, cols=2)
team.alignment = WD_TABLE_ALIGNMENT.CENTER
team.autofit = False
team.columns[0].width = Inches(2.65)
team.columns[1].width = Inches(2.25)
team.rows[0].cells[0].text = 'Student Name'
team.rows[0].cells[1].text = 'Registration Number'
for name, regno in [
    ('Saubhagya Kashyap','AP23110010439'),
    ('Nishkam Makadiya','AP23110010126'),
    ('Aditya Tripathi','AP23110010109'),
]:
    cells = team.add_row().cells
    cells[0].text = name
    cells[1].text = regno
for ri,row in enumerate(team.rows):
    row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    for ci,cell in enumerate(row.cells):
        cell.width = Inches(2.65 if ci == 0 else 2.25)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_margins(cell, top=90, bottom=90, start=120, end=120)
        if ri == 0:
            set_cell_fill(cell,'E8ECEF')
        for p in cell.paragraphs:
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            for run in p.runs:
                run.font.name = 'Book Antiqua'
                run.font.size = Pt(9.5)
                run.bold = (ri == 0)
set_table_borders(team)
submitted._p.addnext(team._tbl)

# Set both faculty mentors on the cover; remove the unprovided UROP ID slot.
for p in doc.paragraphs:
    if p.text.strip() == 'Under the Guidance of':
        p.clear()
        p.add_run('Faculty Mentors')
    elif p.text.strip() == '[Current UROP Mentor Name]':
        p.clear()
        p.add_run('Ravikant Kumar  |  Dr. Raushan Singh')

# Replace acknowledgements with wording for the three-author team and both mentors.
for p in doc.paragraphs:
    if p.text.startswith('I would like to express my sincere gratitude'):
        p.clear()
        p.add_run('We are sincerely grateful to our faculty mentors, Ravikant Kumar and Dr. Raushan Singh, for their mentorship and academic support throughout this UROP project. Their guidance gave us the opportunity to study crop-storage monitoring through environmental readings and MQ sensor responses, and to present the scope and limitations of this work with care.')
        p.paragraph_format.line_spacing = 1.22
    elif p.text.startswith('I am also thankful to my two project teammates'):
        p.clear()
        p.add_run('We also thank the UROP coordinators and the School of Engineering and Sciences, SRM University-AP, for organizing and supporting this research experience. We acknowledge the researchers and institutions that made public datasets, sensor documentation, and postharvest guidance available. These resources helped us distinguish measured evidence from generated simulation data and shape a responsible plan for future real-crop validation.')
        p.paragraph_format.line_spacing = 1.22

# Make the literature table more legible and add the relevant Bath banana benchmark.
lit = doc.tables[1]
new_row = lit.add_row().cells
for cell, value in zip(new_row, [
    'Banana ripeness dataset, University of Bath [7]',
    'Five ripeness stages; VOC, environmental, and spectral sensor subsets.',
    'Useful measured ripeness benchmark; its VOC devices are not the nine MQ channels, and ripeness is not inspected spoilage.'
]):
    cell.text = value
for ri,row in enumerate(lit.rows):
    row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    for cell in row.cells:
        set_cell_margins(cell, top=130, bottom=130, start=120, end=120)
        for p in cell.paragraphs:
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.04
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(9.2)
                if ri == 0:
                    run.bold = True

# Add the cited dataset and renumber the existing final reference.
for p in doc.paragraphs:
    if p.text.startswith('[7] XGBoost Developers.'):
        p.text = '[8] XGBoost Developers. AFT Survival Analysis. https://xgboost.readthedocs.io/en/stable/tutorials/aft_survival_analysis.html'
        p.paragraph_format.left_indent = Inches(0.22)
        p.paragraph_format.first_line_indent = Inches(-0.22)
        p.paragraph_format.space_after = Pt(4)
        bath = p.insert_paragraph_before('[7] Callaghan, K., and U. Martinez Hernandez. Dataset for "Low-Cost, Multi-Sensor Non-Destructive Banana Ripeness Estimation Using Machine Learning." University of Bath Research Data Archive, 2025. https://doi.org/10.15125/BATH-01459')
        bath.paragraph_format.left_indent = Inches(0.22)
        bath.paragraph_format.first_line_indent = Inches(-0.22)
        bath.paragraph_format.space_after = Pt(4)
        for run in bath.runs:
            run.font.name = 'Arial'
            run.font.size = Pt(8.5)

doc.core_properties.title = 'A Leakage-Aware Multimodal Crop-Storage Modeling Pipeline'
doc.core_properties.subject = 'UROP Project Report'
doc.core_properties.author = 'Saubhagya Kashyap; Nishkam Makadiya; Aditya Tripathi'
doc.save(output)
print(output)
