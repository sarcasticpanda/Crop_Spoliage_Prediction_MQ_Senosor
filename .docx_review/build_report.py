"""Rebuild the UROP report from the supplied template and embedded university logo."""
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(r"C:\Users\Lunar Panda\3-Main\urop_crop")
REFERENCE = Path(r"C:\Users\Lunar Panda\Downloads\sample_urop.docx")
OUT = ROOT / "submission"
OUT.mkdir(exist_ok=True)
DOCX = OUT / "UROP_Report_DRAFT_POLISHED.docx"
LOGO_PATH = ROOT / ".docx_review" / "srm_logo.png"

# Start from the provided sample so the document carries its styles, theme,
# section defaults, and embedded SRM mark. Replace only the sample body text.
doc = Document(REFERENCE)
logo_bytes = doc.inline_shapes[0]._inline.graphic.graphicData.pic.blipFill.blip.embed
image_part = doc.part.related_parts[logo_bytes]
LOGO_PATH.write_bytes(image_part.blob)
body = doc._element.body
for child in list(body):
    if child.tag != qn("w:sectPr"):
        body.remove(child)
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Inches(1)

# The supplied acknowledgement reference is sans-serif with a bold left
# heading, justified text, and generous line spacing. Use Arial for body and
# headings, while retaining the sample's clean serif cover-page feel.
normal = doc.styles["Normal"]
normal.font.name = "Arial"
normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
normal.font.size = Pt(11)
normal.paragraph_format.space_after = Pt(8)
normal.paragraph_format.line_spacing = 1.14
for name, size in (("Heading 1", 16), ("Heading 2", 11.5)):
    style = doc.styles[name]
    style.font.name = "Arial"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_before = Pt(9 if name == "Heading 1" else 6)
    style.paragraph_format.space_after = Pt(5)

# The sample's built-in heading styles carry legacy alignment and list-numbering
# settings. Use clean local styles so headings match the visible sample instead
# of inheriting its broken TOC numbering/indentation.
for name, size in (("Report Heading 1", 16), ("Report Heading 2", 11.5)):
    style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = normal
    style.font.name = "Arial"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    style.paragraph_format.left_indent = Inches(0)
    style.paragraph_format.first_line_indent = Inches(0)
    style.paragraph_format.space_before = Pt(10 if size > 12 else 7)
    style.paragraph_format.space_after = Pt(5)
    style.paragraph_format.keep_with_next = True

doc.settings.odd_and_even_pages_header_footer = False
sec.different_first_page_header_footer = False

# Clear old linked footer contents and use restrained centered page numbering.
footer = sec.footer.paragraphs[0]
for child in list(footer._p):
    footer._p.remove(child)
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = footer.add_run("UROP Project Report  |  Page ")
run.font.name, run.font.size = "Arial", Pt(8)
field = OxmlElement("w:fldSimple")
field.set(qn("w:instr"), "PAGE")
footer._p.append(field)

def add_para(text="", *, align=None, bold=False, italic=False, size=None,
             font="Arial", after=None, before=None, line=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    if before is not None:
        p.paragraph_format.space_before = Pt(before)
    if line is not None:
        p.paragraph_format.line_spacing = line
    r = p.add_run(text)
    r.bold, r.italic, r.font.name = bold, italic, font
    if size:
        r.font.size = Pt(size)
    return p

def add_heading(text, level=1):
    return doc.add_paragraph(text, style="Report Heading 1" if level == 1 else "Report Heading 2")

def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)

def set_cell_margins(cell, top=90, start=100, bottom=90, end=100):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")

def add_table(headers, rows, widths, fontsize=8.6):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = OxmlElement(f"w:{edge}")
        tag.set(qn("w:val"), "single")
        tag.set(qn("w:sz"), "5")
        tag.set(qn("w:space"), "0")
        tag.set(qn("w:color"), "686868")
        borders.append(tag)
    t._tbl.tblPr.append(borders)
    for j, label in enumerate(headers):
        c = t.rows[0].cells[j]
        c.text = label
        set_cell_shading(c, "E8ECEF")
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        cells = t.add_row().cells
        for j, value in enumerate(row):
            cells[j].text = str(value)
    for row_index, row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for j, c in enumerate(row.cells):
            c.width = Inches(widths[j])
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(c)
            for p in c.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                for r in p.runs:
                    r.font.name = "Arial"
                    r.font.size = Pt(fontsize)
                    if row_index == 0:
                        r.bold = True
    return t

# Page 1: sample-like centered cover, including the original SRM logo.
add_para("A Leakage-Aware Multimodal Crop-Storage Modeling Pipeline",
         align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, size=18,
         font="Book Antiqua", before=26, after=5)
add_para("Simulation Audit and Public Tomato Scenario Study",
         align=WD_ALIGN_PARAGRAPH.CENTER, italic=True, size=12,
         font="Book Antiqua", after=16)
for text, bold in [
    ("UROP Project Report", True),
    ("Submitted to SRM University–AP, Andhra Pradesh", False),
    ("for the partial fulfilment of the requirements for the degree of", False),
    ("Bachelor of Technology in Computer Science and Engineering", True),
    ("School of Engineering and Sciences", True),
    ("Submitted by", False),
    ("Savari Kashyap  |  AP23110010439  |  [UROP ID]", True),
]:
    add_para(text, align=WD_ALIGN_PARAGRAPH.CENTER, bold=bold, size=10.5,
             font="Book Antiqua", after=5)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(2)
p.paragraph_format.space_after = Pt(5)
p.add_run().add_picture(str(LOGO_PATH), width=Inches(1.25))
for text, bold in [
    ("Under the Guidance of", False),
    ("[Current UROP Mentor Name]", True),
    ("SRM University–AP", True),
    ("Neerukonda, Mangalagiri, Andhra Pradesh – 522 240", True),
    ("November 2026", True),
]:
    add_para(text, align=WD_ALIGN_PARAGRAPH.CENTER, bold=bold, size=10.5,
             font="Book Antiqua", after=5)

# Page 2: acknowledgement typography follows the user's screenshot.
doc.add_page_break()
add_heading("Acknowledgements:")
p = add_para("I would like to express my sincere gratitude to [Current UROP Mentor Name] for their guidance and supervision during this UROP project. The opportunity to explore crop-storage monitoring through environmental readings and MQ sensor responses has helped me connect machine-learning methods with a practical postharvest question. I am grateful for the direction and feedback that helped me define a manageable scope, review the evidence carefully, and present the limitations of the work clearly.", after=9, line=1.22)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p = add_para("I am also thankful to my two project teammates for their collaboration, discussions, and shared effort throughout the project. I extend my thanks to the UROP coordinators and the School of Engineering and Sciences for organizing this research opportunity and providing an academic setting in which to carry it out. Finally, I acknowledge the researchers and institutions whose public datasets, technical documentation, and postharvest guidance informed the literature review and data-source audit. Their work helped us distinguish what has been measured from what remains simulated in this study.", after=14, line=1.22)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_heading("1. Introduction")
p = add_para("Storage conditions can influence crop quality over time. This project builds a research workflow that combines environmental readings with responses from nine metal-oxide MQ channels: MQ2, MQ3, MQ4, MQ5, MQ6, MQ7, MQ8, MQ9, and MQ135. The intended tasks are to estimate current quality state and, when repeated independent inspections are available, risk by the next inspection interval.", line=1.12)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p = add_para("The five-crop dataset covers wheat, maize, table potato, cured dry onion, and spinach. It contains 120,000 simulated rows: 500 starting lots, six storage paths per lot, and 40 readings per path. The readings, dates, labels, paths, and sensor values are generated. The rows are repeated simulator observations, not 120,000 real samples.", line=1.12)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p = add_para("The goal of the current work is to verify the pipeline and evaluation design, not to claim validated crop accuracy. Simulator scores cannot establish how well the model will perform on real produce.", line=1.12)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

# Page 3: literature survey in a readable, bordered table.
doc.add_page_break()
add_heading("2. Literature Survey")
p = add_para("The sources below support separate experiments and help define the future measurement plan. None provides a verified paired dataset containing the same crop lot, all requested sensors, and independent spoilage inspections.", line=1.1)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_table(
    ["Study / dataset", "What it contains", "Use and limitation in this project"],
    [
        ["Tomato e-nose, Zenodo 15469472 [1]", "12 Rs/R0 gas-response channels, weight, colour, storage day and scenario.", "Separate tomato storage-scenario experiment; no inspected spoilage target or matching AeroSense temperature/RH."],
        ["Nine-MQ recordings, Zenodo 17285312 [2]", "Short recordings for the nine MQ channels; day-coded tomato and banana sessions.", "Response-scale exploration only; no verified lot key, matched environment history, or independent inspection label."],
        ["Potato storage archive, Mendeley [3]", "Temperature, RH, tuber-core temperature and CO2 histories across nodes and modes.", "Useful environmental history; MQ and quality summaries lack a verified row-level lot/time join."],
        ["UC Davis postharvest guidance [4–6]", "Crop-stage and intended-use storage guidance for tomato, potato and banana.", "Informs simulated scenario centers, not spoilage labels or universal class thresholds."],
    ], widths=[1.55, 2.35, 3.15], fontsize=8.4)
add_heading("Research gap", 2)
p = add_para("MQ sensors give cross-sensitive response patterns; raw readings are not exact gas concentrations without a defined measurement scale and calibration. The public records remain separate. Joining unrelated files would invent same-lot matches, so that was not done.", line=1.1)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

# Page 4: system model, audited data dimensions, and validation design.
doc.add_page_break()
add_heading("3. System Model")
add_heading("3.1 Five-crop dataset", 2)
p = add_para("The original CSV has 24,000 rows for each of five crops, for 120,000 rows total. This is 500 simulated starting lots × 6 storage paths per lot × 40 observations per path. Each crop contributes 100 starting lots, 600 paths, and 24,000 rows. All six paths from a starting lot remain together during splitting.", line=1.05)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_table(["Crop", "Rows", "Starting lots", "Paths"],
          [["Wheat", "24,000", "100", "600"], ["Maize", "24,000", "100", "600"],
           ["Table potato", "24,000", "100", "600"], ["Cured dry onion", "24,000", "100", "600"],
           ["Spinach", "24,000", "100", "600"], ["TOTAL", "120,000", "500", "3,000"]],
          widths=[2.1, 1.45, 1.6, 1.5], fontsize=8.8)
add_heading("3.2 Inputs and validation", 2)
p = add_para("Models compare environment-only, nine-MQ-only, and combined inputs. Predictors use information available by the current time. Status, inspection defects, failure targets, IDs, scenarios, fictional absolute dates, and future readings are excluded. A fixed split holds out 100 starting lots; five-fold grouped validation on 400 training lots tunes combined Random Forest and XGBoost. The starting-inspection field is evaluated separately because it must also be measured in a real deployment.", line=1.05)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_table(["Feature set", "Inputs used at prediction time"],
          [["Environment-only", "Storage age, temperature, and relative humidity"],
           ["MQ-only", "MQ2, MQ3, MQ4, MQ5, MQ6, MQ7, MQ8, MQ9, and MQ135 response indices"],
           ["Combined", "The environment fields and all nine MQ response indices"]],
          widths=[1.65, 4.85], fontsize=8.7)
add_heading("3.3 Survival and interface", 2)
p = add_para("The discrete-time hazard model uses readings at the start of each inspection interval and excludes post-failure readings. A lot still acceptable at monitoring end is censored, not assigned a made-up failure day. The output is risk by the next inspection, not an exact day-left estimate. The local browser app loads saved five-crop models; it is not connected to live hardware. V3 tomato/potato/banana models run separately through a command-line example.", line=1.05)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_heading("3.4 Additional three-crop simulation", 2)
p = add_para("Edition 2 V3 contains 100 generated trajectories and eight readings per trajectory for tomato, table potato, and banana. Tomato and banana session medians anchor response scale only; potato MQ values use a generic synthetic scale. All environmental paths and three-state labels are simulated. This separate V3 experiment does not add measured lots to the five-crop dataset.", line=1.05)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

# Page 5: actual model and per-crop results, with clear tables.
doc.add_page_break()
add_heading("4. Results and Discussion")
p = add_para("All model scores in the following tables are simulator results, not validated crop accuracy. The five-crop test set contains repeated rows from 100 held-out starting lots.", italic=True, line=1.0)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_heading("4.1 Five-crop status comparison", 2)
add_table(
    ["Inputs / model", "Macro F1", "Spoiled recall", "Log loss", "Brier"],
    [["Majority baseline", "0.1794", "0.0000", "1.0962", "0.6650"],
     ["Environment / XGBoost", "0.8360", "0.8445", "0.3921", "0.2382"],
     ["Nine MQ / XGBoost", "0.9251", "0.9526", "0.1738", "0.1084"],
     ["Combined / Random Forest", "0.9309", "0.9587", "0.1783", "0.1055"],
     ["Combined / XGBoost", "0.9300", "0.9562", "0.1622", "0.1004"]],
    widths=[2.1, .95, 1.15, .95, .85], fontsize=8.1)
p = add_para("XGBoost has better log loss and Brier probability scores; Random Forest has slightly higher macro F1 and spoiled recall. Paired whole-lot intervals for F1 and spoiled recall include zero, so neither model clearly wins those measures. XGBoost is a reasonable probability-focused simulator model, while Random Forest remains a close benchmark.", line=1.02)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_heading("4.2 Per-crop XGBoost results", 2)
add_table(["Crop", "Macro F1", "Spoiled recall"],
          [["Wheat", "0.9185", "0.9536"], ["Maize", "0.9232", "0.9394"],
           ["Table potato", "0.9400", "0.9621"], ["Cured dry onion", "0.9165", "0.9391"],
           ["Spinach", "0.9506", "0.9718"]],
          widths=[2.4, 1.8, 1.8], fontsize=8.6)
add_heading("4.3 Three-crop V3 and time-risk results", 2)
add_table(["V3 crop", "RF F1 / high-risk recall", "XGBoost F1 / high-risk recall"],
          [["Tomato", "0.787 / 0.630", "0.746 / 0.667"],
           ["Potato", "0.614 / 0.400", "0.580 / 0.320"],
           ["Banana", "0.687 / 0.633", "0.745 / 0.733"]],
          widths=[1.5, 2.4, 2.4], fontsize=8.2)
p = add_para("In the five-crop simulation, next-interval XGBoost hazard Brier was 0.01545 (AUC 0.98036); logistic Brier was 0.05504 (AUC 0.98297). AUC is not days-left accuracy. Separately, real tomato data labels storage scenario, not spoilage: XGBoost macro F1 was 0.498 under leave-one-day-out validation and 0.278 on nine tracked tomatoes. This small transfer check is weak.", line=1.0)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

# Page 6: conclusion, future work, and references.
doc.add_page_break()
add_heading("5. Concluding Remarks")
p = add_para("A runnable workflow now covers data review, grouped model comparison, saved-model predictions, and interval-based risk. Thirty focused checks pass for grouped splitting, leakage exclusions, censoring, prediction inputs, and V3 sample-time keys. High simulator scores show that the code can learn generated patterns; they do not show that its labels or sensor patterns match real crop quality.", line=1.1)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_heading("6. Future Work")
p = add_para("For real validation, record temperature/RH and all nine MQ responses for the same identified lot at matched times, with sensor calibration and warm-up details. Independent assessors should apply a written crop-specific rubric: acceptable means sound and marketable; warning means early deterioration or limited defects needing recheck; high risk means severe decay or nonmarketable condition. Record inspection evidence and time. Store the last acceptable and first unacceptable inspection as an interval; record monitoring end as censoring if no failure occurs. Hold out complete lots and preferably a later harvest or device. Compare real-only training with real-plus-simulation on untouched real lots.", line=1.1)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p = add_para("Future temperature/RH what-if results require explicit future MQ values and are conditional projections; they do not prove cooling causes longer shelf life.", line=1.05)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
add_heading("Minimum paired-data record", 2)
add_table(["Record", "Fields to capture"],
          [["Sensor observation", "Study and lot IDs; crop and stage; UTC timestamp and storage age; temperature and RH with units; all nine MQ responses; device, calibration, and warm-up details."],
           ["Independent inspection", "Same lot/sample ID; inspection time; assessor and method; acceptable/warning/high-risk state; crop-specific defect evidence."],
           ["Follow-up", "Last acceptable and first unacceptable inspection times, or monitoring end if no failure; keep all readings from one lot in one split."]],
          widths=[1.55, 4.95], fontsize=8.4)
add_heading("References", 2)
for ref in [
    "[1] Zenodo. Tomato e-nose and laboratory data, record 15469472. https://zenodo.org/records/15469472",
    "[2] Zenodo. Nine-MQ food freshness recordings, record 17285312. https://zenodo.org/records/17285312",
    "[3] Mendeley Data. Potato storage-condition histories, sbwxmtpj47, version 1. https://data.mendeley.com/datasets/sbwxmtpj47/1",
    "[4] UC Davis Postharvest Center. Tomato Produce Facts. https://postharvest.ucdavis.edu/produce-facts-sheets/tomato",
    "[5] UC Davis Postharvest Center. Potato Produce Facts. https://postharvest.ucdavis.edu/produce-facts-sheets/potato",
    "[6] UC Davis Postharvest Center. Banana Produce Facts. https://postharvest.ucdavis.edu/produce-facts-sheets/banana",
    "[7] XGBoost Developers. AFT Survival Analysis. https://xgboost.readthedocs.io/en/stable/tutorials/aft_survival_analysis.html",
]:
    p = add_para(ref, size=8.3, after=3, line=1.0)
    p.paragraph_format.left_indent = Inches(.18)
    p.paragraph_format.first_line_indent = Inches(-.18)

doc.core_properties.title = "A Leakage-Aware Multimodal Crop-Storage Modeling Pipeline"
doc.core_properties.subject = "UROP project report"
doc.core_properties.author = "Savari Kashyap"
doc.save(DOCX)
print(DOCX)
