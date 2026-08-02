REGION={'กรุงเทพมหานคร':'Central&BKK','นนทบุรี':'Central&BKK','ปทุมธานี':'Central&BKK','สมุทรปราการ':'Central&BKK','สมุทรสาคร':'Central&BKK','นครปฐม':'Central&BKK','สมุทรสงคราม':'Central&BKK','พระนครศรีอยุธยา':'Central&BKK','อ่างทอง':'Central&BKK','ลพบุรี':'Central&BKK','สิงห์บุรี':'Central&BKK','ชัยนาท':'Central&BKK','สระบุรี':'Central&BKK','นครนายก':'Central&BKK','สุพรรณบุรี':'Central&BKK','กาญจนบุรี':'Central&BKK','ราชบุรี':'Central&BKK','เพชรบุรี':'Central&BKK','ประจวบคีรีขันธ์':'Central&BKK',
'ชลบุรี':'East','ระยอง':'East','จันทบุรี':'East','ตราด':'East','ฉะเชิงเทรา':'East','ปราจีนบุรี':'East','สระแก้ว':'East',
'นครราชสีมา':'Isan','บุรีรัมย์':'Isan','สุรินทร์':'Isan','ศรีสะเกษ':'Isan','อุบลราชธานี':'Isan','ยโสธร':'Isan','ชัยภูมิ':'Isan','อำนาจเจริญ':'Isan','หนองบัวลำภู':'Isan','ขอนแก่น':'Isan','อุดรธานี':'Isan','เลย':'Isan','หนองคาย':'Isan','มหาสารคาม':'Isan','ร้อยเอ็ด':'Isan','กาฬสินธุ์':'Isan','สกลนคร':'Isan','นครพนม':'Isan','มุกดาหาร':'Isan','บึงกาฬ':'Isan',
'เชียงใหม่':'North','ลำพูน':'North','ลำปาง':'North','อุตรดิตถ์':'North','แพร่':'North','น่าน':'North','พะเยา':'North','เชียงราย':'North','แม่ฮ่องสอน':'North','นครสวรรค์':'North','อุทัยธานี':'North','กำแพงเพชร':'North','ตาก':'North','สุโขทัย':'North','พิษณุโลก':'North','พิจิตร':'North','เพชรบูรณ์':'North',
'สุราษฎร์ธานี':'South','นครศรีธรรมราช':'South','กระบี่':'South','พังงา':'South','ภูเก็ต':'South','ระนอง':'South','ชุมพร':'South','สงขลา':'South','สตูล':'South','ตรัง':'South','พัทลุง':'South','ปัตตานี':'South','ยะลา':'South','นราธิวาส':'South'}
TIER={'Isan':4,'North':3,'South':3,'East':2,'Central&BKK':2}
# modeled competitor-intensity multiplier (indicative; pending locator census). Isan small-towns saturated; rural low.
CINT={'Isan':1.15,'North':0.8,'South':0.9,'East':1.0,'Central&BKK':1.0}

# ── province-string normalization ──────────────────────────────────────────────
# The master arrived with 116 distinct province strings (should be 77): some records
# carry ISO 3166-2:TH codes, English names, a "จังหวัด " prefix, or a blank. These
# maps fold every variant back to the canonical Thai name in REGION, so by-province /
# by-region rollups are complete. See canonical().
ISO={ 'TH-10':'กรุงเทพมหานคร','TH-11':'สมุทรปราการ','TH-12':'นนทบุรี','TH-13':'ปทุมธานี',
 'TH-14':'พระนครศรีอยุธยา','TH-15':'อ่างทอง','TH-16':'ลพบุรี','TH-17':'สิงห์บุรี','TH-18':'ชัยนาท',
 'TH-19':'สระบุรี','TH-20':'ชลบุรี','TH-21':'ระยอง','TH-22':'จันทบุรี','TH-23':'ตราด','TH-24':'ฉะเชิงเทรา',
 'TH-25':'ปราจีนบุรี','TH-26':'นครนายก','TH-27':'สระแก้ว','TH-30':'นครราชสีมา','TH-31':'บุรีรัมย์',
 'TH-32':'สุรินทร์','TH-33':'ศรีสะเกษ','TH-34':'อุบลราชธานี','TH-35':'ยโสธร','TH-36':'ชัยภูมิ',
 'TH-37':'อำนาจเจริญ','TH-38':'บึงกาฬ','TH-39':'หนองบัวลำภู','TH-40':'ขอนแก่น','TH-41':'อุดรธานี',
 'TH-42':'เลย','TH-43':'หนองคาย','TH-44':'มหาสารคาม','TH-45':'ร้อยเอ็ด','TH-46':'กาฬสินธุ์',
 'TH-47':'สกลนคร','TH-48':'นครพนม','TH-49':'มุกดาหาร','TH-50':'เชียงใหม่','TH-51':'ลำพูน','TH-52':'ลำปาง',
 'TH-53':'อุตรดิตถ์','TH-54':'แพร่','TH-55':'น่าน','TH-56':'พะเยา','TH-57':'เชียงราย','TH-58':'แม่ฮ่องสอน',
 'TH-60':'นครสวรรค์','TH-61':'อุทัยธานี','TH-62':'กำแพงเพชร','TH-63':'ตาก','TH-64':'สุโขทัย',
 'TH-65':'พิษณุโลก','TH-66':'พิจิตร','TH-67':'เพชรบูรณ์','TH-70':'ราชบุรี','TH-71':'กาญจนบุรี',
 'TH-72':'สุพรรณบุรี','TH-73':'นครปฐม','TH-74':'สมุทรสาคร','TH-75':'สมุทรสงคราม','TH-76':'เพชรบุรี',
 'TH-77':'ประจวบคีรีขันธ์','TH-80':'นครศรีธรรมราช','TH-81':'กระบี่','TH-82':'พังงา','TH-83':'ภูเก็ต',
 'TH-84':'สุราษฎร์ธานี','TH-85':'ระนอง','TH-86':'ชุมพร','TH-90':'สงขลา','TH-91':'สตูล','TH-92':'ตรัง',
 'TH-93':'พัทลุง','TH-94':'ปัตตานี','TH-95':'ยะลา','TH-96':'นราธิวาส'}
ALIAS={'Lamphun':'ลำพูน','Samut Prakan':'สมุทรปราการ','Chaiyaphum':'ชัยภูมิ',
 'Prachuap Khiri Khan':'ประจวบคีรีขันธ์',
 'สุราษฏร์ธานี':'สุราษฎร์ธานี',   # ฏ→ฎ spelling variant seen in NSO data
 'อยุธยา':'พระนครศรีอยุธยา'}      # everyday short form; OAE files the napprang crop under it
# fallback for blank province strings: resolve by the (canonical) amphoe in the record
DISTRICT_PROV={'ไชโย':'อ่างทอง','ลำปลายมาศ':'บุรีรัมย์','ลำลูกกา':'ปทุมธานี',
 'ลานสัก':'อุทัยธานี','เมืองร้อยเอ็ด':'ร้อยเอ็ด'}

# Explicit English-name / slug overrides for provinces whose name cannot be derived
# from a "Mueang <prov>" amphoe (build_province.py's default heuristic). Without these
# the province inherits an arbitrary district name: กรุงเทพมหานคร has no "Mueang" amphoe
# so it fell back to "Bang Kapi", and พระนครศรีอยุธยา's capital amphoe is
# "Phra Nakhon Si Ayutthaya" (not "Mueang ...") so it fell back to "Bang Sai".
PROVINCE_EN={'กรุงเทพมหานคร':'Bangkok','พระนครศรีอยุธยา':'Ayutthaya'}

def canonical(prov, district=None):
    """Fold a raw province string to its canonical Thai name (or '' if unresolved)."""
    p=(prov or '').strip()
    if p.startswith('จังหวัด'): p=p.replace('จังหวัด','',1).strip()
    if p in REGION: return p
    if p in ISO: return ISO[p]
    if p in ALIAS: return ALIAS[p]
    if not p and district and district.strip() in DISTRICT_PROV: return DISTRICT_PROV[district.strip()]
    return p

def region_of(prov, district=None):
    """Canonical region for a raw province string, or 'Other' if still unresolved."""
    return REGION.get(canonical(prov, district), 'Other')

def norm_district(d, prov=None):
    """Normalize an amphoe (district) name so branch records and the DIW
    factory layer join. Folds the DECOMPOSED SARA-AM (U+0E4D U+0E32 -> U+0E33,
    which NFC does not compose), drops อำเภอ/เขต/Amphoe/อ. prefixes, fixes the
    'อำเมือง' typo, and expands a bare 'เมือง' to the capital amphoe 'เมือง<prov>'."""
    s = (d or '').replace('ํา', 'ำ').strip()   # decomposed SARA-AM -> composed
    s = s.replace('อำเมือง', 'เมือง')                          # typo: missing เภอ
    for pre in ('อำเภอ', 'เขต', 'Amphoe ', 'อ.', 'อ '):
        if s.startswith(pre):
            s = s[len(pre):].strip(); break
    if s == 'เมือง' and prov:
        s = 'เมือง' + prov
    return s
