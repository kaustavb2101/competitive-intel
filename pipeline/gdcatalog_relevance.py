# -*- coding: utf-8 -*-
"""gdcatalog_relevance.py — shared KEEP/DROP rule for the gdcatalog harvest.

One place decides whether a catalog dataset is relevant to AutoX (a Thai title-loan lender).
Both the harvester (skip irrelevant at download, --relevant-only) and the prune script (delete
already-downloaded irrelevant files) import is_relevant() so the rule is identical everywhere.

Design goal: GENEROUS keep. Everything is re-downloadable from the retained _catalog.jsonl index,
but we still err toward keeping anything plausibly useful. A dataset is KEPT if EITHER:
  (a) its publishing agency is on HIGH_VALUE_ORGS (national statistics, finance, vehicles, land,
      agri, labour, industry, cooperatives, foreclosure, business registry, fiscal/monetary), OR
  (b) its title/notes contain any AutoX KEYWORD (debt/income/household/vehicle/land/crop/price/
      labour/factory/cooperative/foreclosure/tax/...).
This keeps provincial-portal datasets that ARE useful (e.g. a province's vehicle-registration or
crop table) while dropping provincial admin noise (mask counts, radio schedules, meeting logs) and
clearly-irrelevant national agencies (zoo, nuclear, airports, PR/radio, heritage, forensics).
"""

# --- agency allowlist (substring match on the Thai org title) ---------------------------------
HIGH_VALUE_ORGS = [
    "สำนักงานสถิติแห่งชาติ",              # NSO — household income/debt/poverty/labour (crown jewel)
    "กรมการขนส่งทางบก",                  # DLT — vehicle registration (collateral)
    "กรมโรงงานอุตสาหกรรม",               # DIW — factories
    "กรมสรรพสามิต",                      # Excise — vehicle/goods tax
    "กรมส่งเสริมสหกรณ์",                 # Cooperative Promotion
    "กรมตรวจบัญชีสหกรณ์",                # Cooperative Auditing
    "กรมบังคับคดี",                      # Legal Execution — foreclosures / asset seizure
    "กรมพัฒนาธุรกิจการค้า",              # Business Development — company registry
    "สำนักงานคณะกรรมการกำกับหลักทรัพย์",  # SEC
    "ธนาคารแห่งประเทศไทย",               # BoT
    "สำนักงานเศรษฐกิจการคลัง",           # Fiscal Policy Office
    "สำนักงานปลัดกระทรวงการคลัง",        # MoF
    "สำนักงานเศรษฐกิจการเกษตร",          # OAE — agri economics
    "กรมส่งเสริมการเกษตร",               # Agri Extension
    "กรมการข้าว",                        # Rice Dept
    "กรมประมง",                          # Fisheries
    "กรมปศุสัตว์",                       # Livestock
    "กรมพัฒนาที่ดิน",                    # Land Development
    "กรมที่ดิน",                         # Land Dept (land collateral / title)
    "กรมการปกครอง",                      # Provincial Admin — population registry
    "กรมการจัดหางาน",                   # Employment Dept
    "สำนักงานประกันสังคม",               # Social Security — formal employment
    "กระทรวงแรงงาน",                     # Ministry of Labour
    "สำนักงานสภาพัฒนาการเศรษฐกิจ",       # NESDC — GPP / macro
    "สำนักงานกองทุนน้ำมันเชื้อเพลิง",     # Oil Fund — fuel prices
    "กรมพัฒนาพลังงานทดแทน",              # Energy — GPP-linked
    "กรมการค้าภายใน",                   # Internal Trade — retail prices
    "กรมพัฒนาชุมชน",                     # Community Development — household economy
    "สำนักงานเศรษฐกิจอุตสาหกรรม",        # Industrial Economics
    "กรมส่งเสริมอุตสาหกรรม",             # Industrial Promotion
]

# --- title/notes keyword allowlist (Thai) -----------------------------------------------------
KEYWORDS = [
    # debt / credit / finance
    "หนี้", "สินเชื่อ", "เงินกู้", "กู้ยืม", "จำนำ", "จำนอง", "บังคับคดี", "ล้มละลาย",
    "สหกรณ์", "สถาบันการเงิน", "เงินฝาก", "หลักทรัพย์", "งบการเงิน", "นิติบุคคล", "ทุนจดทะเบียน",
    # income / household / poverty
    "รายได้", "รายจ่าย", "ค่าใช้จ่าย", "ครัวเรือน", "ยากจน", "ฐานราก", "หัวหน้าครัวเรือน", "สวัสดิการ",
    # collateral: vehicles / land
    "รถ", "ยานพาหนะ", "รถยนต์", "รถจักรยานยนต์", "ทะเบียนรถ", "จดทะเบียนรถ",
    "ที่ดิน", "โฉนด", "อสังหาริมทรัพย์",
    # agri (borrower PD)
    "เกษตร", "ข้าว", "ยางพารา", "มันสำปะหลัง", "อ้อย", "ปาล์ม", "พืช", "ปศุสัตว์", "ประมง",
    "ผลผลิต", "เพาะปลูก", "ชลประทาน", "ภัยแล้ง",
    # prices / macro
    "ราคา", "ดัชนีราคา", "เงินเฟ้อ", "ผลิตภัณฑ์มวลรวม", "gpp", "gdp", "อัตราดอกเบี้ย",
    # labour / employment
    "แรงงาน", "จ้างงาน", "ว่างงาน", "ค่าจ้าง", "ค่าตอบแทน", "อาชีพ", "ลูกจ้าง", "การมีงานทำ",
    # population / business / industry
    "ประชากร", "โรงงาน", "อุตสาหกรรม", "สถานประกอบการ", "วิสาหกิจ", "ผู้ประกอบการ", "ธุรกิจ", "ภาษี",
]

# agencies we treat as noise even if a stray keyword matches the ORG name
HARD_DROP_ORGS = [
    "องค์การสวนสัตว์", "สถาบันเทคโนโลยีนิวเคลียร์", "กรมท่าอากาศยาน", "กรมประชาสัมพันธ์",
    "สถาบันนิติวิทยาศาสตร์", "องค์การสวนพฤกษศาสตร์", "กรมอุทยานแห่งชาติ",
]
# ...but keep even a hard-drop agency's dataset if the TITLE is squarely on-topic
_ONTOPIC = ("รถ", "ที่ดิน", "หนี้", "สินเชื่อ", "ครัวเรือน", "ราคา")


def _txt(*parts):
    return " ".join(str(p or "") for p in parts)


def is_relevant(org, title, notes=""):
    """True if this dataset is worth keeping for AutoX. Generous by design."""
    o = str(org or "")
    for bad in HARD_DROP_ORGS:
        if bad in o:
            return any(k in _txt(title) for k in _ONTOPIC)
    if any(a in o for a in HIGH_VALUE_ORGS):
        return True
    blob = _txt(title, notes).lower()
    return any(k.lower() in blob for k in KEYWORDS)
