# -*- coding: utf-8 -*-
"""Thai catalogue, part 3 of 3 — callouts, source rows, Q&A answers and speaker notes.

These are the longest strings in the deck and the ones carrying the most placeholders. A template
consumes `{}` in the same order as its English key, so the number sequence must be mirrored exactly:
a template with one placeholder too many raises at format time and Deck._t() logs a finding and
falls back to English rather than shipping a half-substituted sentence. That is the safety net, not
the plan — the plan is to mirror the sequence.

Provenance vocabulary is fixed on purpose: MEASURED = วัดจริง, ESTIMATED = ประมาณการ. The whole
point of the chip is that a reader can tell the two apart at a glance, in either language.
"""

STRINGS = {
    # ---------------------------------------------------------------- 02 the answer
    "No — stable, not strong.\n• GDP {}, CPI {} — both above the IMF's {} forecast. Policy rate "
    "{}.\n• Slowest growth in ASEAN{}: Thailand {} vs Vietnam {}.\n• Government debt {} of GDP vs "
    "Vietnam's {} — thinnest cushion in the group.":
        "ไม่ใช่ — นิ่ง แต่ไม่แข็งแรง\n• GDP {} เงินเฟ้อ {} — สูงกว่าประมาณการ IMF ปี {} ทั้งคู่ "
        "ดอกเบี้ยนโยบาย {}\n• โตช้าที่สุดใน ASEAN{}: ไทย {} เทียบเวียดนาม {}\n"
        "• หนี้ภาครัฐ {} ของ GDP เทียบเวียดนาม {} — กันชนบางที่สุดในกลุ่ม",
    "Not on the world index — the farm gate (ราคาที่เกษตรกรขายได้) says otherwise.\n• Eight of "
    "seventeen Thai farm-gate prices are falling year on year.\n• Beef: farm gate {} vs world index "
    "{}.\n• Margin over price: a {} price move becomes an {} swing in crop income.":
        "ไม่ใช่ถ้าดูดัชนีโลก — แต่ราคาหน้าฟาร์ม (ราคาที่เกษตรกรขายได้) บอกคนละเรื่อง\n"
        "• ราคาหน้าฟาร์มไทยแปดจากสิบเจ็ดรายการลดลงเมื่อเทียบกับปีก่อน\n"
        "• เนื้อวัว: หน้าฟาร์ม {} เทียบดัชนีโลก {}\n"
        "• ส่วนต่างสำคัญกว่าราคา: ราคาขยับ {} กลายเป็นรายได้เกษตรเหวี่ยง {}",
    "The collateral — the used-pickup (รถกระบะ) market.\n• Resale value {} off peak, {} pts below "
    "its {} base.\n• New pickup registrations {} year on year.\n• Hilux Revo {}, worst nameplate "
    "Ranger {}.":
        # manual numbering: Thai puts the base YEAR before the point gap, English the other way
        "หลักประกัน — ตลาดรถกระบะมือสอง\n"
        "• มูลค่าขายต่อ {0} จากจุดสูงสุด และต่ำกว่าฐานปี {2} อยู่ {1} จุด\n"
        "• ยอดจดทะเบียนกระบะใหม่ {3} เทียบปีก่อน\n• Hilux Revo {4} รุ่นที่แย่ที่สุดคือ Ranger {5}",
    "Thin before any of this.\n• Farming pays ฿{}–{}/month vs an employee wage of ฿{}–{}.\n• Three "
    "of five full-cost crops pay below cost of production.\n• {} of households have no {}-month "
    "cushion; arrears rose in three of the last four quarters.":
        "บางอยู่ก่อนแล้ว ก่อนที่ทั้งหมดนี้จะเกิด\n• อาชีพเกษตรได้ ฿{}–{}/เดือน เทียบค่าจ้างลูกจ้าง ฿{}–{}\n"
        "• พืชสามจากห้าชนิดที่มีข้อมูลต้นทุนครบ ขายได้ต่ำกว่าต้นทุนการผลิต\n"
        "• ครัวเรือน {} ไม่มีกันชนเงินออม {} เดือน และหนี้ค้างชำระเพิ่มขึ้นในสามจากสี่ไตรมาสล่าสุด",
    "NESDC · TPSO · Bank of Thailand · BIS · ECB · IMF · World Bank · NABC · OAE · DLT · MOT · NSO "
    "· ThaiWater. Each page carries its own chip and vintage; where a figure is modelled rather than "
    "published it is labelled ESTIMATED.":
        "สศช. · TPSO · ธนาคารแห่งประเทศไทย · BIS · ECB · IMF · ธนาคารโลก · NABC · สศก. · ขบ. · คค. · "
        "สสช. · ThaiWater ทุกหน้ามีป้ายกำกับแหล่งที่มาและรุ่นข้อมูลของตัวเอง "
        "ตัวเลขใดที่มาจากแบบจำลองไม่ใช่การเผยแพร่จริง จะกำกับว่า ประมาณการ",
    "If they take one thing: the macro is stable, the crops are mixed, the collateral is "
    "deteriorating — and the borrower was already thin before any of it. Scope is external "
    "conditions; the book readouts live on Exposure and Risk, not here.":
        "ถ้าจะจำได้เรื่องเดียว: เศรษฐกิจนิ่ง พืชผลผสม หลักประกันแย่ลง — และผู้กู้บางอยู่ก่อนแล้วก่อนทั้งหมดนี้ "
        "ขอบเขตคือปัจจัยภายนอก ส่วนตัวเลขพอร์ตอยู่ในแท็บ Exposure และ Risk ไม่ใช่ที่นี่",

    # ---------------------------------------------------------------- 03 macro overlay
    "Growth beat the IMF's own {} forecast": "การเติบโตสูงกว่าประมาณการของ IMF เองปี {}",
    "• Growth: IMF forecast {}, actual {}.\n• Inflation: IMF forecast {}, actual {}.\n• We use the "
    "Thai number over the projection, wherever one exists.\n• Exception: tourism, {} YoY (trailing "
    "{} months) — feeds informal income in the South and East, missing from crop and fleet data.":
        "• การเติบโต: IMF ประมาณการ {} ตัวเลขจริง {}\n• เงินเฟ้อ: IMF ประมาณการ {} ตัวเลขจริง {}\n"
        "• เราใช้ตัวเลขไทยแทนประมาณการทุกครั้งที่มีตัวเลขจริง\n"
        "• ข้อยกเว้น: ท่องเที่ยว {} เทียบปีก่อน (ย้อนหลัง {} เดือน) — "
        "หนุนรายได้นอกระบบในภาคใต้และภาคตะวันออก ซึ่งข้อมูลพืชและรถมองไม่เห็น",
    "Slowest growth in the region, least room to cushion it":
        "โตช้าที่สุดในภูมิภาค และมีพื้นที่รองรับน้อยที่สุด",
    "• Thailand grows {}. The rest of the region runs {}–{}.\n• Govt debt {} of GDP vs Vietnam's "
    "{}.\n• Less fiscal room for relief than in {}–{}.\n• System arrears rose in three of the last "
    "four quarters — bank loans, a direction not a benchmark.":
        "• ไทยโต {} ส่วนที่เหลือในภูมิภาคโต {}–{}\n• หนี้ภาครัฐ {} ของ GDP เทียบเวียดนาม {}\n"
        "• พื้นที่การคลังสำหรับมาตรการช่วยเหลือน้อยกว่าช่วงปี {}–{}\n"
        "• หนี้ค้างชำระทั้งระบบเพิ่มขึ้นในสามจากสี่ไตรมาสล่าสุด — เป็นสินเชื่อธนาคาร ดูเป็นทิศทาง ไม่ใช่เกณฑ์เทียบ",
    "NESDC {}-Q{} · TPSO {}{} · Bank of Thailand {}{} · BIS {}-Q{} · ECB {}{}{} each pulled from "
    "the publishing agency. IMF World Economic Outlook {} (pulled {}{}{}) for the peer table. BoT "
    "published NPL ratio — {} at {}-Q{} {} the quarter before, {}pp on the year, {} low in {}-Q{}.":
        "สศช. {} ไตรมาส {} · TPSO {}{} · ธนาคารแห่งประเทศไทย {}{} · BIS {} ไตรมาส {} · ECB {}{}{} "
        "ทั้งหมดดึงจากหน่วยงานผู้เผยแพร่โดยตรง ตารางเทียบประเทศใช้ IMF World Economic Outlook {} "
        "(ดึงข้อมูล {}{}{}) อัตรา NPL ที่ ธปท. เผยแพร่ — {} ณ {} ไตรมาส {} จาก {} ไตรมาสก่อน "
        "เปลี่ยน {} จุดใน 1 ปี และต่ำสุด {} ณ {} ไตรมาส {}",
    "Economy is fine — the region and the arrears line are the story. Slow growth, thin fiscal "
    "cushion, arrears up in most of the last year. Less relief room than {}–{}.":
        "เศรษฐกิจไม่มีปัญหา — ประเด็นอยู่ที่การเทียบภูมิภาคและเส้นหนี้ค้างชำระ โตช้า กันชนการคลังบาง "
        "หนี้ค้างชำระเพิ่มขึ้นเกือบทั้งปีที่ผ่านมา และมีพื้นที่ช่วยเหลือน้อยกว่าช่วงปี {}–{}",

    # ---------------------------------------------------------------- 04 conditions
    "{} unemployment hides informal work": "อัตราว่างงาน {} ซ่อนการทำงานนอกระบบไว้",
    "A lost formal job reappears as informal work, not as unemployment — on lower, less predictable "
    "pay. Read informality, seasonal idle and the cushion instead. Isan's seasonal idle is {}× the "
    "North's.":
        # kept to two lines on purpose — the Thai wrapped to three and spilled past the footer
        "งานในระบบที่หายไปกลับมาเป็นงานนอกระบบ ไม่ใช่การว่างงาน — ค่าจ้างต่ำกว่าและไม่แน่นอนกว่า "
        "ให้ดูสัดส่วนนอกระบบ การว่างงานตามฤดูกาล และกันชนเงินออมแทน "
        "อีสานว่างงานตามฤดูกาลสูงเป็น {} เท่าของภาคเหนือ",
    "NSO LFS · ILOSTAT · DLT · MOT · DBD · ThaiWater · BoT/NSO household debt. Labour, fleet and "
    "water roll province → region → national on their own weight, never a plain average. The debt "
    "card is BoT/NSO {} ({}), ALL households — not only the {} carrying debt. The table's region "
    "column is a newer cut, {} ({}), in baht: income is not published at region grain for enough "
    "regions to convert it. East shares Central's figure.":
        "สสช. (สำรวจแรงงาน) · ILOSTAT · ขบ. · คค. · กรมพัฒนาธุรกิจการค้า · ThaiWater · "
        "หนี้ครัวเรือน ธปท./สสช. ตัวเลขแรงงาน รถ และน้ำ รวมจากจังหวัด → ภาค → ประเทศ ตามน้ำหนักจริงของแต่ละพื้นที่ "
        "ไม่ใช่ค่าเฉลี่ยธรรมดา การ์ดหนี้เป็นข้อมูล ธปท./สสช. {} ({}) นับ ทุกครัวเรือน — "
        "ไม่ใช่เฉพาะ {} ที่มีหนี้ ส่วนคอลัมน์รายภาคในตารางเป็นชุดข้อมูลใหม่กว่า {} ({}) หน่วยเป็นบาท "
        "เพราะรายได้ไม่ได้เผยแพร่ในระดับภาคครบพอที่จะแปลงเป็นเดือนได้ ภาคตะวันออกใช้ตัวเลขร่วมกับภาคกลาง",
    "This drill goes from a national number to a district without changing instrument. Household "
    "debt is now months of income, not baht — that's the underwriting frame. If someone reaches for "
    "near-zero unemployment as evidence the borrower is fine, this is the slide.":
        "หน้านี้ไล่จากตัวเลขระดับประเทศลงถึงระดับอำเภอโดยไม่เปลี่ยนเครื่องมือวัด "
        "หนี้ครัวเรือนแสดงเป็นจำนวนเดือนของรายได้ ไม่ใช่บาท — นั่นคือกรอบที่เราใช้พิจารณาสินเชื่อ "
        "ถ้ามีใครหยิบอัตราว่างงานที่ใกล้ศูนย์มาอ้างว่าผู้กู้ไม่มีปัญหา ให้เปิดหน้านี้",

    # ---------------------------------------------------------------- 05 commodity board
    "Beef: the world index is the wrong instrument": "เนื้อวัว: ดัชนีโลกเป็นเครื่องมือที่ผิด",
    "World beef {}, Thai farm gate {} — a {}-point gap, opposite directions. {} of our farming "
    "customers live in the beef belt, Isan.":
        "เนื้อวัวตลาดโลก {} ราคาหน้าฟาร์มไทย {} — ต่างกัน {} จุด และไปคนละทาง "
        "ลูกค้าอาชีพเกษตรของเรา {} รายอาศัยอยู่ในแหล่งเลี้ยงวัวคืออีสาน",
    "Prices MEASURED — NABC daily quotes for the Thai farm gate, OCSB announced cane price; newest "
    "quote {}{}{}. The six-month move is computed from NABC's own monthly series "
    "(thai_price_history, vintage {}{}{}); a crop with no monthly series is marked, never estimated. "
    "Belt is an ESTIMATED read of where each commodity is produced, and belts overlap. Farming "
    "accounts are OURS and MEASURED — accounts whose recorded occupation is เกษตร in the belt "
    "provinces, from the {}-account tape at {}{}; no cell below {} accounts is published. They live "
    "where the crop grows; they are not confirmed to grow it.":
        "ราคา วัดจริง — ราคาหน้าฟาร์มไทยจากราคารายวันของ NABC และราคาอ้อยประกาศของ สอน. "
        "ราคาล่าสุด {}{}{} การเปลี่ยนแปลงหกเดือนคำนวณจากข้อมูลรายเดือนของ NABC เอง "
        "(thai_price_history รุ่นข้อมูล {}{}{}) พืชที่ไม่มีข้อมูลรายเดือนจะกำกับไว้ ไม่ประมาณการขึ้นมา "
        "แหล่งผลิตเป็นการอ่านแบบ ประมาณการ ว่าสินค้าแต่ละชนิดปลูกที่ไหน และแหล่งผลิตทับซ้อนกันได้ "
        "บัญชีอาชีพเกษตรเป็นข้อมูลของเราเองและ วัดจริง — บัญชีที่บันทึกอาชีพว่า เกษตร ในจังหวัดแหล่งผลิต "
        "จากฐานข้อมูล {} บัญชี ณ {}{} ไม่เผยแพร่ช่องที่มีน้อยกว่า {} บัญชี "
        "คนกลุ่มนี้อาศัยอยู่ในพื้นที่ที่ปลูกพืชนั้น แต่ไม่ได้ยืนยันว่าปลูกพืชนั้นเอง",
    "Two points. First, the world index and the Thai farm gate can face opposite ways, and only one "
    "of them is what a Thai grower is paid — beef is the clean example. Second, the last column is "
    "farmers, not all accounts: the app's 'book exposed' number counts every borrower in the belt "
    "and about four in five of them are not farming.":
        "สองประเด็น หนึ่ง ดัชนีโลกกับราคาหน้าฟาร์มไทยหันไปคนละทางได้ และมีเพียงตัวเดียวที่เป็นเงินที่เกษตรกรไทยได้รับ "
        "— เนื้อวัวเป็นตัวอย่างที่ชัดที่สุด สอง คอลัมน์สุดท้ายคือเกษตรกร ไม่ใช่บัญชีทั้งหมด: "
        "ตัวเลข book exposed ในแอปนับผู้กู้ทุกคนในแหล่งผลิต และประมาณสี่ในห้าไม่ได้ทำเกษตร",

    # ---------------------------------------------------------------- 06 five years of price
    "A year-on-year number hides the shape": "ตัวเลขเทียบปีก่อนซ่อนรูปทรงไว้",
    "• Sugar (น้ำตาล): world price {} against its {}{} peak — down in {} of the last {} months, not "
    "a one-year dip.\n• Rubber (ยางพารา): spent {} of the last {} months below its own {} level — "
    "only just cleared it, after {} months running above.":
        # all-manual numbering: the Thai puts rubber's own base year ({7}) before its counts, and
        # .format() forbids mixing {} with {7} in one template
        "• น้ำตาล: ราคาโลก {0} เทียบจุดสูงสุด {1}{2} — ลดลงใน {3} จาก {4} เดือนล่าสุด "
        "ไม่ใช่การย่อตัวปีเดียว\n"
        "• ยางพารา: อยู่ต่ำกว่าระดับปี {7} ของตัวเองถึง {5} จาก {6} เดือนล่าสุด "
        "และเพิ่งกลับขึ้นมาได้ หลังยืนเหนือระดับนั้นมา {8} เดือน",
    "World Bank Pink Sheet nominal-USD monthly prices, vintage {}M{} ({} observations per series, "
    "rebased to {} at {}{} for the chart — units differ, so raw levels can’t share an axis). Baht "
    "conversion at the ECB reference rate USD/THB {}, {}{}{}. Planted-area share MEASURED, OAE/DOAE "
    "crop mix (crop_mix.json). Nominal, not deflated: five years of Thai CPI sit under every ‘vs {} "
    "yrs ago’ figure.":
        "ราคารายเดือนสกุลดอลลาร์ราคาปัจจุบันจาก World Bank Pink Sheet รุ่นข้อมูล {}M{} "
        "(ข้อมูล {} จุดต่อรายการ ปรับฐานเป็น {} ณ {}{} เพื่อวาดกราฟ — หน่วยต่างกัน "
        "จึงใช้แกนเดียวกับระดับราคาดิบไม่ได้) แปลงเป็นบาทด้วยอัตราอ้างอิง ECB USD/THB {} ณ {}{}{} "
        "สัดส่วนพื้นที่ปลูก วัดจริง จากสัดส่วนพืชของ สศก./กรมส่งเสริมการเกษตร (crop_mix.json) "
        "เป็นราคาปัจจุบัน ไม่ได้ปรับเงินเฟ้อ: ทุกตัวเลข ‘เทียบ {} ปีก่อน’ มีเงินเฟ้อไทยห้าปีซ่อนอยู่ข้างใต้",
    "YoY hides a slow move: sugar is down most months since its {} peak, not a one-off dip; rubber "
    "only just cleared its own {} level. We convert only the latest price to baht — the five-year "
    "peak stays in US$ so we don’t mix an old price with today’s FX.":
        "ตัวเลขเทียบปีก่อนซ่อนการเคลื่อนไหวช้า ๆ ไว้: น้ำตาลลดลงเกือบทุกเดือนตั้งแต่จุดสูงสุดปี {} "
        "ไม่ใช่การย่อตัวครั้งเดียว ส่วนยางพาราเพิ่งกลับขึ้นเหนือระดับปี {} ของตัวเองได้ "
        "เราแปลงเป็นบาทเฉพาะราคาล่าสุด — จุดสูงสุดห้าปีคงเป็นดอลลาร์ "
        "เพื่อไม่ให้เอาราคาเก่ามาผสมกับอัตราแลกเปลี่ยนวันนี้",

    # ---------------------------------------------------------------- 07 crop belts
    "Good for farming, almost everywhere": "ดีต่อภาคเกษตร แทบทุกพื้นที่",
    "•  {} rubber, {} cassava, {} palm, {} rice at the farm gate. Crop income rose in every "
    "region.\n•  Four provinces fell — all coconut, all on the western gulf. Coconut price is down "
    "{}.\n•  A gain on paper is not cash yet — the next table nets prices against cost.":
        "•  ราคาหน้าฟาร์ม: ยางพารา {} มันสำปะหลัง {} ปาล์ม {} ข้าว {} รายได้จากพืชเพิ่มขึ้นทุกภาค\n"
        "•  มีสี่จังหวัดที่ลดลง — ทั้งหมดเป็นมะพร้าว และอยู่ฝั่งอ่าวไทยตะวันตก ราคามะพร้าวลดลง {}\n"
        "•  กำไรบนกระดาษยังไม่ใช่เงินสด — ตารางถัดไปหักราคาด้วยต้นทุน",
    "Planted area MEASURED (OAE, by province). Crop mix MEASURED — every crop OAE tracks for that "
    "province, share of planted area, rounded to the nearest point and shown for all of them, not "
    "just the lead crop; a share that rounds to zero reads “<{}”, and any rounding gap is shown "
    "honestly as “other”. Farm-gate price moves MEASURED (NABC/OCSB); farm income level MEASURED "
    "(NSO/OAE, baht per month). The income shock is ESTIMATED — each province's crop mix weighted by "
    "the measured price move, as a percentage of its measured farm income. Six of {} provinces "
    "shown, ordered by planted area.":
        "พื้นที่ปลูก วัดจริง (สศก. รายจังหวัด) สัดส่วนพืช วัดจริง — ทุกพืชที่ สศก. เก็บข้อมูลของจังหวัดนั้น "
        "เป็นสัดส่วนของพื้นที่ปลูก ปัดเป็นจำนวนเต็ม และแสดงทุกพืช ไม่ใช่เฉพาะพืชหลัก "
        "สัดส่วนที่ปัดแล้วเป็นศูนย์แสดงเป็น “<{}” และส่วนต่างจากการปัดแสดงตรงไปตรงมาว่า “อื่น ๆ” "
        "การเปลี่ยนแปลงราคาหน้าฟาร์ม วัดจริง (NABC/สอน.) ระดับรายได้เกษตร วัดจริง (สสช./สศก. บาทต่อเดือน) "
        "ผลกระทบต่อรายได้เป็น ประมาณการ — ถ่วงน้ำหนักสัดส่วนพืชของแต่ละจังหวัดด้วยการเปลี่ยนแปลงราคาที่วัดได้ "
        "คิดเป็นร้อยละของรายได้เกษตรที่วัดได้ แสดง 6 จาก {} จังหวัด เรียงตามพื้นที่ปลูก",
    "What earns agriculture a section is that its hazards are external and forecastable — price, "
    "cost, rainfall — which is rare. The crop-mix column is now the full published mix for each "
    "province, every crop, summing to {} — not just the lead crop.":
        "เหตุที่ภาคเกษตรได้มีหมวดของตัวเอง คือความเสี่ยงของมันมาจากภายนอกและพอคาดการณ์ได้ — ราคา ต้นทุน ปริมาณฝน "
        "— ซึ่งหาได้ยาก คอลัมน์สัดส่วนพืชตอนนี้เป็นสัดส่วนที่เผยแพร่ครบของแต่ละจังหวัด ทุกพืช รวมได้ {} "
        "— ไม่ใช่เฉพาะพืชหลัก",

    # ---------------------------------------------------------------- 08 every crop
    "Farm-gate prices MEASURED — NABC daily quotes, monthly means, in baht as published (no currency "
    "conversion); newest quote {}{}{} history vintage {}{}{}. Farm gate (ราคาที่เกษตรกรขายได้) is "
    "what the grower is paid at first sale, before trading, milling or transport take a cut — not "
    "the world index and not a supermarket price. Belts are an ESTIMATED read of where each "
    "commodity is produced, and they overlap. Sugar is OCSB's announced season price, one point a "
    "year, so it has no six-month move to show.":
        "ราคาหน้าฟาร์ม วัดจริง — ราคารายวันของ NABC เฉลี่ยเป็นรายเดือน หน่วยเป็นบาทตามที่เผยแพร่ "
        "(ไม่มีการแปลงสกุลเงิน) ราคาล่าสุด {}{}{} รุ่นข้อมูลย้อนหลัง {}{}{} "
        "ราคาหน้าฟาร์ม (ราคาที่เกษตรกรขายได้) คือเงินที่เกษตรกรได้รับเมื่อขายครั้งแรก "
        "ก่อนพ่อค้าคนกลาง โรงสี หรือค่าขนส่งจะหักส่วนแบ่ง — ไม่ใช่ดัชนีโลก และไม่ใช่ราคาในซูเปอร์มาร์เก็ต "
        "แหล่งผลิตเป็นการอ่านแบบ ประมาณการ ว่าสินค้าแต่ละชนิดผลิตที่ไหน และทับซ้อนกันได้ "
        "น้ำตาลเป็นราคาอ้อยประกาศของ สอน. ปีละหนึ่งจุด จึงไม่มีการเปลี่ยนแปลงหกเดือนให้แสดง",
    "The profitability argument is gone on purpose — it covered five crops and invited a fight about "
    "which published price is right. This shows the price the grower is actually paid, for every "
    "commodity we can measure, with its own six-month line. The point to land: year-on-year and "
    "six-month disagree on direction for several of them, so a single annual number is not enough to "
    "act on.":
        "เราตัดข้อถกเถียงเรื่องกำไรออกโดยเจตนา — มันครอบคลุมแค่ห้าพืช และเปิดทางให้เถียงกันว่าราคาที่เผยแพร่ตัวไหนถูก "
        "หน้านี้แสดงราคาที่เกษตรกรได้รับจริง ครบทุกสินค้าที่เราวัดได้ พร้อมเส้นหกเดือนของตัวเอง "
        "ประเด็นที่ต้องให้ติด: หลายรายการมีทิศทางไม่ตรงกันระหว่างเทียบปีก่อนกับหกเดือน "
        "ตัวเลขรายปีตัวเดียวจึงไม่พอที่จะใช้ตัดสินใจ",

    # ---------------------------------------------------------------- 09 income by region
    "Farming (เกษตรกร) — up everywhere, still the floor":
        "เกษตรกร — เพิ่มขึ้นทุกภาค แต่ยังเป็นพื้นล่างสุด",
    "• Best-moving job in every region — and still the lowest-paid.\n• North ฿{} against a ฿{} wage "
    "({}); Isan ฿{} against ฿{} ({}).\n• Floor: นราธิวาส farms on ฿{}/mo — size a programme against "
    "this, not the mean.":
        "• เป็นอาชีพที่รายได้ขยับดีที่สุดในทุกภาค — และยังได้ค่าตอบแทนต่ำที่สุด\n"
        "• ภาคเหนือ ฿{} เทียบค่าจ้าง ฿{} ({}) อีสาน ฿{} เทียบ ฿{} ({})\n"
        "• พื้นล่างสุด: นราธิวาส ฿{}/เดือน — ออกแบบมาตรการตามตัวเลขนี้ ไม่ใช่ค่าเฉลี่ย",
    "Transport (ขนส่ง) — one number, not five": "ขนส่ง — ตัวเลขเดียว ไม่ใช่ห้าตัว",
    "• Down {} in every region. Factory moves the same way; office is flat — no channel modelled "
    "for it, which is not the same as no change.\n• One measured crude-oil move through one chosen "
    "coefficient. No Thai diesel or freight series behind it.\n• Still matters: here the vehicle IS "
    "the income. An early call beats a late one.":
        "• ลดลง {} ทุกภาค โรงงานเคลื่อนไปทางเดียวกัน ส่วนออฟฟิศนิ่ง — เพราะไม่มีช่องทางส่งผ่านในแบบจำลอง "
        "ซึ่งไม่เหมือนกับการไม่เปลี่ยนแปลง\n"
        "• มาจากการเคลื่อนไหวของราคาน้ำมันดิบที่วัดได้หนึ่งค่า ผ่านค่าสัมประสิทธิ์ที่เลือกไว้หนึ่งค่า "
        "ไม่มีข้อมูลดีเซลหรือค่าขนส่งของไทยรองรับ\n"
        "• ยังสำคัญ: อาชีพนี้ตัวรถคือรายได้ โทรไปก่อนดีกว่าโทรไปสาย",
    "Income MEASURED — NSO SES province income (NSO SES {}), NSO LFS regional wages ({} "
    "({}-quarter average)), ฿/month; region = unweighted mean of its provinces. Move is ESTIMATED — "
    "one first-order model of the price and fuel round (fuel driver {}M{}), at documented "
    "coefficients, not fitted. No monthly SES/LFS series exists, so no {}-month figure sits beside "
    "it.":
        "รายได้ วัดจริง — รายได้รายจังหวัดจากการสำรวจภาวะเศรษฐกิจและสังคมของครัวเรือน สสช. (สสช. SES {}) "
        "ค่าจ้างรายภาคจากการสำรวจแรงงาน สสช. ({} (เฉลี่ย {} ไตรมาส)) หน่วยบาท/เดือน "
        "ค่าของภาค = ค่าเฉลี่ยไม่ถ่วงน้ำหนักของจังหวัดในภาคนั้น การเปลี่ยนแปลงเป็น ประมาณการ — "
        "แบบจำลองลำดับที่หนึ่งของรอบราคาและน้ำมัน (ตัวขับเคลื่อนราคาน้ำมัน {}M{}) "
        "ใช้ค่าสัมประสิทธิ์ที่มีเอกสารอ้างอิง ไม่ได้ประมาณค่าทางสถิติ "
        "ไม่มีข้อมูล SES/LFS รายเดือน จึงไม่มีตัวเลข {} เดือนวางเทียบไว้",
    "Two things: farming is up everywhere and still under half the local wage — size the programme "
    "off the floor province, not the mean. Be upfront that the transport number is one national "
    "assumption, not five measurements.":
        "สองเรื่อง: รายได้เกษตรเพิ่มขึ้นทุกภาคแต่ยังไม่ถึงครึ่งของค่าจ้างในพื้นที่ — "
        "ออกแบบมาตรการจากจังหวัดที่ต่ำสุด ไม่ใช่ค่าเฉลี่ย และพูดตรง ๆ ว่าตัวเลขขนส่งเป็นสมมติฐานระดับประเทศหนึ่งค่า "
        "ไม่ใช่การวัดห้าครั้ง",

    # ---------------------------------------------------------------- 10 water
    "Planted area MEASURED (OAE — {} amphoe crop rows). Drought is a MODELLED SPEI index from "
    "rainfall and evapotranspiration, refreshed monthly, retrieved {}{}{} — the best "
    "national-coverage signal available, but nobody has walked those districts. Rain and river "
    "telemetry MEASURED (ThaiWater, live, pulled daily and accumulated — a missed pull leaves a gap "
    "rather than an invented point) · rain to {}{}{} river to {}{}{}. Structural flood exposure "
    "MEASURED (GISTDA {}:{} repeated-flooding census, {}{} — a {}-year ground record, not a "
    "forecast).":
        "พื้นที่ปลูก วัดจริง (สศก. — ข้อมูลอำเภอ×พืช {} แถว) ภัยแล้งเป็นดัชนี SPEI จาก แบบจำลอง "
        "คำนวณจากปริมาณฝนและการคายระเหย ปรับเดือนละครั้ง ดึงข้อมูล {}{}{} — "
        "เป็นสัญญาณที่ครอบคลุมทั้งประเทศดีที่สุดที่มี แต่ไม่มีใครลงพื้นที่ไปเดินดูอำเภอเหล่านั้น "
        "ข้อมูลฝนและระดับน้ำ วัดจริง (ThaiWater เรียลไทม์ ดึงทุกวันและสะสมไว้ — "
        "วันที่ดึงไม่สำเร็จจะเว้นเป็นช่องว่าง ไม่ใส่ค่าสมมติ) · ฝนถึง {}{}{} ระดับน้ำถึง {}{}{} "
        "ความเสี่ยงน้ำท่วมเชิงโครงสร้าง วัดจริง (สำมะโนพื้นที่ท่วมซ้ำซาก GISTDA มาตราส่วน {}:{} ปี {}{} "
        "— เป็นบันทึกภาคพื้นดิน {} ปี ไม่ใช่การพยากรณ์)",
    "Two clocks, kept apart: SPEI is the season (modelled, monthly), ThaiWater is today (measured, "
    "live). GISTDA is a third, separate thing — which ground floods anyway — its own card, never "
    "blended into either table.":
        "นาฬิกาสองเรือน แยกกันชัดเจน: SPEI คือฤดูกาล (แบบจำลอง รายเดือน) ThaiWater คือวันนี้ (วัดจริง เรียลไทม์) "
        "GISTDA เป็นเรื่องที่สาม แยกออกไป — ว่าพื้นที่ไหนท่วมอยู่ดี — มีการ์ดของตัวเอง "
        "ไม่เคยผสมเข้ากับตารางใดทั้งสองตาราง",

    # ---------------------------------------------------------------- 11 where to reach out
    "Crop is a poor discriminator": "พืชแยกแยะได้ไม่ดี",
    "It trips {} of {} provinces — national exposure, not who to call. Debt, jobs and rain are what "
    "separate this list.":
        "สัญญาณนี้เข้าเงื่อนไข {} จาก {} จังหวัด — เป็นความเสี่ยงระดับประเทศ ไม่ได้บอกว่าควรโทรหาใคร "
        "ตัวที่แยกรายการนี้ออกจากกันคือหนี้ การว่างงาน และฝน",
    "Household debt-to-income MEASURED (NSO SES {} — debt as a share of ANNUAL income, so above {} "
    "is more debt than a year of earnings). Unemployment MEASURED (NSO LFS, by province). Lead crop "
    "MEASURED (OAE planted area, all eight crops); its economics ESTIMATED from OAE cost of "
    "production ({} (crop year {}/{} OAE forecast Mar {})). Rainfall MEASURED as precipitation "
    "against the long-run normal, a different instrument from the SPEI index two slides back; two "
    "provinces carry no gauge and cannot trip this signal.":
        "หนี้ครัวเรือนต่อรายได้ วัดจริง (สสช. SES {} — หนี้เป็นสัดส่วนของรายได้ ทั้งปี "
        "ดังนั้นเกิน {} หมายถึงหนี้มากกว่ารายได้หนึ่งปี) การว่างงาน วัดจริง (สำรวจแรงงาน สสช. รายจังหวัด) "
        "พืชหลัก วัดจริง (พื้นที่ปลูก สศก. ครบทั้งแปดพืช) เศรษฐกิจของพืชเป็น ประมาณการ "
        "จากต้นทุนการผลิตของ สศก. ({} (ปีเพาะปลูก {}/{} ประมาณการ สศก. มี.ค. {})) "
        "ปริมาณฝน วัดจริง เทียบค่าปกติระยะยาว ซึ่งเป็นเครื่องมือคนละตัวกับดัชนี SPEI สองหน้าก่อน "
        "มีสองจังหวัดที่ไม่มีสถานีวัดและไม่สามารถเข้าเงื่อนไขสัญญาณนี้ได้",
    "Ranked on how many of four signals tripped, not on two of them — that is why สิงห์บุรี appears "
    "despite low debt. The crop test trips almost everywhere and does not discriminate; debt, jobs "
    "and rain do. Geographies, not people.":
        "เรียงตามจำนวนสัญญาณที่เข้าเงื่อนไขจากทั้งสี่ตัว ไม่ใช่แค่สองตัว — "
        "นั่นคือเหตุที่สิงห์บุรีปรากฏขึ้นมาแม้หนี้จะต่ำ เกณฑ์พืชเข้าเงื่อนไขแทบทุกที่และแยกแยะไม่ได้ "
        "ตัวที่แยกได้คือหนี้ การว่างงาน และฝน หน้านี้ชี้ไปที่พื้นที่ ไม่ใช่ตัวบุคคล",
    "อำนาจเจริญ trips all four warning flags. Three more trip three — สุโขทัย, สิงห์บุรี, "
    "อุบลราชธานี.":
        "อำนาจเจริญเข้าเงื่อนไขทั้งสี่สัญญาณ อีกสามจังหวัดเข้าสามสัญญาณ — สุโขทัย สิงห์บุรี อุบลราชธานี",

    # ---------------------------------------------------------------- 10 collateral
    "Slow down here. Everything before was conditions on the borrower; this is conditions on the "
    "security, which is the part with an underwriting consequence.":
        "ช้าลงตรงนี้ ทุกอย่างก่อนหน้านี้คือสภาพของผู้กู้ ส่วนนี้คือสภาพของหลักประกัน "
        "ซึ่งเป็นส่วนที่มีผลต่อการพิจารณาสินเชื่อโดยตรง",
    "We lend against titles, so the used-vehicle market is an external condition that prices our "
    "security directly. Five things are moving at once: what a used vehicle is worth, how many are "
    "entering the pool, which brands they are, which nameplates underneath those brands, and how "
    "easily any of them can be sold on. A model with no Thai residual history is a recovery "
    "assumption nobody can make yet.":
        "เราปล่อยกู้โดยใช้เล่มทะเบียนเป็นหลักประกัน ตลาดรถมือสองจึงเป็นปัจจัยภายนอกที่กำหนดราคาหลักประกันของเราโดยตรง "
        "มีห้าเรื่องเคลื่อนไหวพร้อมกัน: รถมือสองมีมูลค่าเท่าไร มีรถเข้ามาในกองมากน้อยแค่ไหน เป็นแบรนด์อะไร "
        "อยู่รุ่นไหนภายใต้แบรนด์นั้น และขายต่อได้ง่ายแค่ไหน "
        "รุ่นที่ไม่มีสถิติราคามือสองในไทยคือสมมติฐานการเรียกคืนที่ยังไม่มีใครตั้งได้",
    "Two windows, one message": "สองหน้าต่าง ข้อความเดียว",
    "• Pickup {} in {} months, {} in {} — the fall has stopped.\n• Car {} in {} months, {} in {} — "
    "same shape, weaker level.\n• Pickup is {} pts below its {} base, car {} pts.\n• Advance rates "
    "set before {} price a market that no longer exists.":
        # manual numbering, same reason as the collateral card on slide 02
        "• กระบะ {0} ใน {1} เดือน และ {2} ใน {3} เดือน — ราคาหยุดตกแล้ว\n"
        "• รถยนต์ {4} ใน {5} เดือน และ {6} ใน {7} เดือน — รูปทรงเดียวกัน แต่ระดับอ่อนกว่า\n"
        "• กระบะต่ำกว่าฐานปี {9} อยู่ {8} จุด รถยนต์ {10} จุด\n"
        "• อัตราปล่อยกู้ที่ตั้งไว้ก่อนปี {11} ตีราคาตลาดที่ไม่มีอยู่แล้ว",
    "Bank of Thailand used-vehicle price index (EC_EI_{}), {} monthly points; {}- and {}-month "
    "moves computed from the published series, rebased to {} = {}. Pickup = confirmed pickup trucks "
    "(รถกระบะ), not heavy commercial (BoT Stat-Horizon methodology, {}). Latest month preliminary.":
        "ดัชนีราคารถมือสองของธนาคารแห่งประเทศไทย (EC_EI_{}) ข้อมูลรายเดือน {} จุด "
        "การเปลี่ยนแปลง {} และ {} เดือนคำนวณจากชุดข้อมูลที่เผยแพร่ ปรับฐานเป็น {} = {} "
        "กระบะ = รถกระบะที่ยืนยันแล้ว ไม่ใช่รถบรรทุกหนัก (ตามวิธีวัด Stat-Horizon ของ ธปท. ปี {}) "
        "เดือนล่าสุดเป็นข้อมูลเบื้องต้น",
    "Two windows: pickup {} over six months but {} over twelve — the fall has stopped, not reversed. "
    "Level still well below {}.":
        "สองหน้าต่าง: กระบะ {} ในหกเดือน แต่ {} ในสิบสองเดือน — ราคาหยุดตก ไม่ใช่กลับทิศ "
        "ระดับยังต่ำกว่าปี {} อยู่มาก",

    # ---------------------------------------------------------------- 10b registration windows
    "The pickup “trend” is one flagged month": "“แนวโน้ม” ของกระบะคือเดือนผิดปกติเดือนเดียว",
    "• Five months fall in a row, then one month jumps — a bar, not a turn.\n• Slope with that month "
    "in: {}/mo. Without it: {}/mo.\n• Even that month was {} YoY for pickups — still falling.":
        "• ลดลงห้าเดือนติด แล้วมีหนึ่งเดือนกระโดด — เป็นแท่งเดียว ไม่ใช่การกลับทิศ\n"
        "• ความชันเมื่อรวมเดือนนั้น: {}/เดือน หากตัดออก: {}/เดือน\n"
        "• แม้แต่เดือนนั้นเองกระบะก็ยัง {} เทียบปีก่อน — ยังลดลงอยู่",
    "Most of the car “boom” is one month": "“การเติบโต” ของรถยนต์ส่วนใหญ่มาจากเดือนเดียว",
    "• {}-month car growth: {}. Ex-flag: {}.\n• That month alone ran {} YoY — pulled forward, not "
    "demand.\n• The {}-month figure, {}, is the safer read.":
        "• การเติบโตรถยนต์ {} เดือน: {} หากตัดเดือนผิดปกติ: {}\n"
        "• เดือนนั้นเดือนเดียว {} เทียบปีก่อน — เป็นการเร่งยอดมาก่อน ไม่ใช่ความต้องการจริง\n"
        "• ตัวเลข {} เดือนที่ {} เป็นค่าที่อ่านได้ปลอดภัยกว่า",
    "Registrations MEASURED — DLT gdcatalog first registrations, {} months from {}{}. Ex-flag "
    "figures are our arithmetic on that series — ESTIMATED, a judgement call on which month to "
    "trust.":
        "ยอดจดทะเบียน วัดจริง — ยอดจดทะเบียนครั้งแรกจาก gdcatalog ของกรมการขนส่งทางบก {} เดือน ตั้งแต่ {}{} "
        "ตัวเลขที่ตัดเดือนผิดปกติออกเป็นการคำนวณของเราเองบนชุดข้อมูลนั้น — ประมาณการ "
        "และเป็นการใช้วิจารณญาณว่าจะเชื่อเดือนไหน",
    "Pickup's six-month slope is not a recovery — ex-flag it is {}/mo. The same month inflates car "
    "growth from {} to {}. Quote the {}-month windows.":
        "ความชันหกเดือนของกระบะไม่ใช่การฟื้นตัว — หากตัดเดือนผิดปกติออกจะเป็น {}/เดือน "
        "เดือนเดียวกันนี้ทำให้การเติบโตรถยนต์พุ่งจาก {} เป็น {} ให้อ้างหน้าต่าง {} เดือนแทน",

    # ---------------------------------------------------------------- 10c brand concentration
    "Two markets, opposite directions": "สองตลาด คนละทิศทาง",
    "• Pickup: Toyota + Isuzu hold {}, down only {} points in a year. The pool shrinks; its shape "
    "barely changes.\n• Car: {} points surrendered in a year. {} of new cars now carry no Thai "
    "residual record.\n• We know what a five-year-old Hilux is worth. We do not yet know what a "
    "five-year-old BYD is worth.":
        "• กระบะ: Toyota + Isuzu ครอง {} ลดลงเพียง {} จุดในหนึ่งปี กองรถเล็กลง แต่รูปทรงแทบไม่เปลี่ยน\n"
        "• รถยนต์: เสียส่วนแบ่งไป {} จุดในหนึ่งปี รถยนต์ใหม่ {} ไม่มีสถิติราคามือสองในไทย\n"
        "• เรารู้ว่า Hilux อายุห้าปีมีมูลค่าเท่าไร แต่เรายังไม่รู้ว่า BYD อายุห้าปีมีมูลค่าเท่าไร",
    "DLT first registrations at nameplate grain, trailing {} months, NATIONAL only — no province "
    "column exists. First registrations are the FUTURE collateral pool, not a stock of what is on "
    "the road, and not used-vehicle sales.":
        "ยอดจดทะเบียนครั้งแรกของกรมการขนส่งทางบก ระดับรายรุ่น ย้อนหลัง {} เดือน ระดับประเทศเท่านั้น — "
        "ไม่มีคอลัมน์รายจังหวัด ยอดจดทะเบียนครั้งแรกคือกองหลักประกัน ในอนาคต "
        "ไม่ใช่จำนวนรถที่วิ่งอยู่บนถนน และไม่ใช่ยอดขายรถมือสอง",
    "Pickup pool shrinks without changing shape — residual values stay predictable. Cars are the "
    "opposite: a growing share carries no Thai residual record to price against.":
        "กองกระบะเล็กลงแต่รูปทรงไม่เปลี่ยน — มูลค่าคงเหลือยังคาดการณ์ได้ ฝั่งรถยนต์ตรงกันข้าม: "
        "สัดส่วนที่โตขึ้นเรื่อย ๆ ไม่มีสถิติราคามือสองในไทยให้ใช้ตีราคา",

    # ---------------------------------------------------------------- 10d nameplates
    "DLT first registrations at the registrar's own ยี่ห้อ + รุ่น grain, trailing {} months to "
    "{}{} NATIONAL only. PU shares are over pickup + PPV combined, PA shares over cars, so each is "
    "a share of its own market. One caveat that only bites the right-hand table: DLT files many car "
    "models per TRIM — {} distinct car nameplate strings against {} cars, Toyota alone filing {} — "
    "so each PA share is a floor. Merging every trim would not close the gap: BYD's entire car "
    "volume is {}, still under the single biggest PU nameplate.":
        "ยอดจดทะเบียนครั้งแรกของกรมการขนส่งทางบก ตามระดับ ยี่ห้อ + รุ่น ของนายทะเบียนเอง ย้อนหลัง {} เดือน "
        "ถึง {}{} ระดับประเทศเท่านั้น สัดส่วนกระบะคิดจากกระบะ + PPV รวมกัน สัดส่วนรถยนต์คิดจากรถยนต์ "
        "แต่ละฝั่งจึงเป็นสัดส่วนของตลาดตัวเอง มีข้อควรระวังหนึ่งข้อที่กระทบเฉพาะตารางขวา: "
        "ขบ. แจ้งรุ่นรถยนต์แยกตามรุ่นย่อย — มีชื่อรุ่นรถยนต์ต่างกัน {} ชื่อ จากรถ {} คัน "
        "เฉพาะ Toyota แจ้งถึง {} ชื่อ ดังนั้นสัดส่วนรถยนต์แต่ละรุ่นเป็นค่าต่ำสุด "
        "การรวมรุ่นย่อยทั้งหมดก็ยังไม่ปิดช่องว่างนี้: ยอดรถยนต์ทั้งหมดของ BYD อยู่ที่ {} "
        "ซึ่งยังต่ำกว่ารุ่นกระบะรุ่นเดียวที่ใหญ่ที่สุด",
    "Advance rates are set per model, not brand. PU is five rows we can price from history. PA is a "
    "long tail of models registered for the first time this year — the trim-split caveat makes PA "
    "shares a floor, but it does not change the conclusion.":
        "อัตราปล่อยกู้กำหนดเป็นรายรุ่น ไม่ใช่รายแบรนด์ ฝั่งกระบะมีห้าแถวที่เราตีราคาได้จากสถิติ "
        "ฝั่งรถยนต์เป็นหางยาวของรุ่นที่เพิ่งจดทะเบียนปีนี้เป็นปีแรก — "
        "ข้อควรระวังเรื่องรุ่นย่อยทำให้สัดส่วนฝั่งรถยนต์เป็นค่าต่ำสุด แต่ไม่เปลี่ยนข้อสรุป",

    # ---------------------------------------------------------------- 10f four years of nameplates
    "The collateral pool is shrinking faster than it is changing shape":
        "กองหลักประกันหดตัวเร็วกว่าที่รูปทรงจะเปลี่ยน",
    "Four years took {} pickups a year out of the flow — {} — while cars held roughly flat. Fewer "
    "new pickups now means a thinner supply of five-year-old pickups to lend against later, and the "
    "nameplates are the same ones: this is a volume problem, not a mix problem.":
        "สี่ปีที่ผ่านมาดึงกระบะออกจากยอดจดทะเบียนไป {} คันต่อปี — คิดเป็น {} — ขณะที่รถยนต์แทบไม่เปลี่ยน "
        "กระบะใหม่ที่น้อยลงวันนี้หมายถึงกระบะอายุห้าปีที่จะให้กู้ได้ในอนาคตจะน้อยลงตามไปด้วย "
        "และรุ่นรถก็ยังเป็นรุ่นเดิม: นี่คือปัญหาปริมาณ ไม่ใช่ปัญหาส่วนผสม",
    "DLT first registrations at the registrar's own ยี่ห้อ + รุ่น grain, from the yearly roll-up "
    "files so the mirror's missing {}{} month cannot distort a year. {}–{} are the only complete "
    "years published. These are vehicles entering the fleet, NOT the stock on the road — no DLT "
    "dataset carries brand or model against registered stock, so a total parc by nameplate does not "
    "exist and is not shown here. An em-dash means the nameplate was outside that year's top {} not "
    "that none were registered.":
        "ยอดจดทะเบียนครั้งแรกของกรมการขนส่งทางบก ตามระดับ ยี่ห้อ + รุ่น ของนายทะเบียนเอง "
        "อ่านจากไฟล์สรุปรายปี เพื่อไม่ให้เดือน {}{} ที่ขาดไปในชุดข้อมูลบิดเบือนตัวเลขทั้งปี "
        "ปี {}–{} เป็นปีที่เผยแพร่ครบเพียงเท่านี้ ตัวเลขเหล่านี้คือรถที่ เข้าสู่ กองรถ "
        "ไม่ใช่จำนวนรถที่วิ่งอยู่บนถนน — ไม่มีชุดข้อมูลของ ขบ. ใดที่มีคอลัมน์ยี่ห้อหรือรุ่นควบคู่กับรถจดทะเบียนสะสม "
        "ดังนั้นจำนวนรถทั้งหมดแยกตามรุ่นจึงไม่มีอยู่ และไม่ได้แสดงไว้ที่นี่ "
        "เครื่องหมายขีดหมายถึงรุ่นนั้นอยู่นอก {} อันดับแรกของปีนั้น ไม่ได้หมายความว่าไม่มีการจดทะเบียนเลย",
    "Say the caveat first: this is what ENTERED the road each year, not what is on it — DLT "
    "publishes no stock by model, so the parc by nameplate cannot be built. What it shows is a "
    "four-year collapse in pickup supply with the same nameplates on top throughout, which is a "
    "volume problem rather than a mix problem.":
        "พูดข้อจำกัดก่อน: นี่คือรถที่ เข้าสู่ ท้องถนนในแต่ละปี ไม่ใช่รถที่อยู่บนถนน — "
        "ขบ. ไม่ได้เผยแพร่จำนวนรถจดทะเบียนสะสมแยกตามรุ่น จึงสร้างจำนวนรถทั้งหมดแยกตามรุ่นไม่ได้ "
        "สิ่งที่หน้านี้แสดงคืออุปทานกระบะที่ทรุดลงต่อเนื่องสี่ปี โดยรุ่นที่อยู่อันดับบนยังเป็นรุ่นเดิมตลอด "
        "ซึ่งเป็นปัญหาปริมาณมากกว่าปัญหาส่วนผสม",

    # ---------------------------------------------------------------- 10e second-hand market
    "Small and slow, at the same time": "เล็กและช้า ในเวลาเดียวกัน",
    "Pickups are only {} of the vehicle parc — cars {}, motorcycles {} — and still turn over "
    "slowest: {}–{} of pickups change hands a year against {}–{} for cars, worst in East.\n\nA "
    "smaller, slower market means a longer disposal and a wider discount on a repossessed title.":
        "กระบะคิดเป็นเพียง {} ของรถทั้งหมด — รถยนต์ {} จักรยานยนต์ {} — และยังเปลี่ยนมือช้าที่สุด: "
        "กระบะเปลี่ยนมือ {}–{} ต่อปี เทียบกับรถยนต์ {}–{} โดยช้าที่สุดที่ภาคตะวันออก\n\n"
        "ตลาดที่เล็กและช้ากว่าหมายถึงระยะเวลาขายทอดตลาดที่นานขึ้น และส่วนลดที่กว้างขึ้นเมื่อยึดเล่มทะเบียนมา",
    "Electrification is a clock, not a problem": "รถไฟฟ้าเป็นนาฬิกา ไม่ใช่ปัญหา",
    "BEVs are {} of the fleet, electrified {} — not a factor today.\n\nBut titles resell over five "
    "to ten years, and {} of new cars already carry no Thai resale history. That fleet ages into the "
    "used market before {}.":
        "รถ BEV คิดเป็น {} ของรถทั้งหมด ไฟฟ้ารวม {} — ยังไม่ใช่ปัจจัยในวันนี้\n\n"
        "แต่เล่มทะเบียนขายต่อกันในช่วงห้าถึงสิบปี และรถยนต์ใหม่ {} ไม่มีสถิติราคามือสองในไทยอยู่แล้ว "
        "กองรถนั้นจะแก่ตัวเข้าสู่ตลาดมือสองก่อนปี {}",
    "DLT registered stock and ownership transfers by region and class (PU รถกระบะ · car รถยนต์นั่ง "
    "· moto รถจักรยานยนต์), plus MOT fleet totals. Share = class stock ÷ all registered vehicles in "
    "the region. Turnover = transfers ÷ registered stock — how much of the parc changes hands a "
    "year, the depth a repossessed title sells into.":
        "รถจดทะเบียนสะสมและการโอนกรรมสิทธิ์ของกรมการขนส่งทางบก แยกตามภาคและประเภท "
        "(กระบะ · รถยนต์นั่ง · จักรยานยนต์) รวมกับยอดรถทั้งหมดของกระทรวงคมนาคม "
        "สัดส่วน = รถจดทะเบียนของประเภทนั้น ÷ รถจดทะเบียนทั้งหมดในภาค "
        "อัตราเปลี่ยนมือ = จำนวนการโอน ÷ รถจดทะเบียนสะสม — "
        "บอกว่ารถในกองเปลี่ยนมือกันปีละเท่าไร ซึ่งคือความลึกของตลาดที่เล่มทะเบียนที่ยึดมาต้องไปขาย",
    "The point of the table: pickup is both the smallest class of the three and the slowest to turn "
    "over. Turnover is the depth a repossession actually sells into.":
        "ประเด็นของตารางนี้: กระบะเป็นทั้งประเภทที่เล็กที่สุดในสามประเภท และเปลี่ยนมือช้าที่สุด "
        "อัตราเปลี่ยนมือคือความลึกของตลาดที่รถยึดต้องไปขายจริง",

    # ---------------------------------------------------------------- 11 so what
    "Call the four-signal provinces first": "ติดต่อจังหวัดที่ครบสี่สัญญาณก่อน",
    "Watch the provinces left behind": "เฝ้าดูจังหวัดที่ตกขบวน",
    "Median crop income rose {}, but four provinces fell — all on the coconut (มะพร้าว) belt, worst "
    "สมุทรสงคราม at {}.":
        "รายได้จากพืชค่ากลางเพิ่มขึ้น {} แต่มีสี่จังหวัดที่ลดลง — ทั้งหมดอยู่ในแหล่งปลูกมะพร้าว "
        "โดยหนักที่สุดคือสมุทรสงครามที่ {}",
    "Track the three crops still falling": "ติดตามสามพืชที่ยังลดลง",
    "Coconut (มะพร้าว), Pineapple (สับปะรด), Sugarcane (อ้อย) keep falling at the farm gate "
    "(ราคาที่เกษตรกรขายได้) — {} of the country’s planted land.":
        "มะพร้าว สับปะรด และอ้อย ราคาหน้าฟาร์ม (ราคาที่เกษตรกรขายได้) ยังลดลงต่อเนื่อง — "
        "คิดเป็น {} ของพื้นที่เพาะปลูกทั้งประเทศ",
    "Reprice the vehicle we lend against": "ตีราคารถที่เราใช้เป็นหลักประกันใหม่",
    "Pickup resale is still {} points below its {} level, the slowest-selling class on the road. "
    "Five nameplates cover {} of that market; new car brands do not.":
        "ราคาขายต่อของกระบะยังต่ำกว่าระดับปี {1} อยู่ {0} จุด และเป็นประเภทที่ขายช้าที่สุดบนถนน "
        "กระบะห้ารุ่นครอง {2} ของตลาดนั้น ส่วนแบรนด์รถยนต์ใหม่ไม่มีสถิติแบบนั้น",
    "Read two signals as models, not facts": "อ่านสองสัญญาณนี้เป็นแบบจำลอง ไม่ใช่ข้อเท็จจริง",
    "Transport income moves {} on one national fuel number, no Thai freight data behind it. Drought "
    "(ภัยแล้ง) is a rainfall model — nobody has walked those districts.":
        "รายได้ขนส่งขยับ {} จากตัวเลขราคาน้ำมันระดับประเทศตัวเดียว โดยไม่มีข้อมูลค่าขนส่งของไทยรองรับ "
        "ส่วนภัยแล้งเป็นแบบจำลองปริมาณฝน — ไม่มีใครลงพื้นที่ไปเดินดูอำเภอเหล่านั้น",
    "External data only — the economy, crops, water, vehicles. It points at places, never at people; "
    "turning a place into a call list is the Assistance tab’s job. Nothing here argues to open, "
    "close or expand anything.":
        "ข้อมูลภายนอกเท่านั้น — เศรษฐกิจ พืชผล น้ำ รถ หน้านี้ชี้ไปที่พื้นที่ ไม่ใช่ตัวบุคคล "
        "การแปลงพื้นที่ให้เป็นรายชื่อสำหรับติดต่อเป็นหน้าที่ของแท็บ Assistance "
        "และไม่มีอะไรในนี้ที่เสนอให้เปิด ปิด หรือขยายสิ่งใด",
    "Five short asks, easiest slide in the deck to read. The farm-income ask now stands on the price "
    "shock, not the OAE cost table — that argument left with {}. Close on scope: external "
    "conditions only, no book, no open/close/expand call.":
        "ห้าข้อเสนอสั้น ๆ เป็นหน้าที่อ่านง่ายที่สุดในชุดนี้ ข้อเสนอเรื่องรายได้เกษตรตอนนี้ยืนอยู่บนผลกระทบด้านราคา "
        "ไม่ใช่ตารางต้นทุนของ สศก. — ข้อถกเถียงนั้นออกไปพร้อมกับหน้า {} "
        "ปิดท้ายด้วยขอบเขต: ปัจจัยภายนอกเท่านั้น ไม่มีตัวเลขพอร์ต และไม่มีข้อเสนอเปิด ปิด หรือขยาย",
    "Vintages — world prices {}M{} · Thai farm gate {}{}{} · Thai price history {}{}{} · crop cost "
    "of production OAE Cai-up {} (crop year {}/{} OAE forecast Mar {}) · drought {}{}{} · CPI {}{} "
    "· GDP {}-Q{} · IMF WEO {} · resale index {}{} · registrations to {}{} · household debt NSO SES "
    "{} · wages NSO LFS {} · telemetry {}{}{}.":
        "รุ่นข้อมูล — ราคาโลก {}M{} · ราคาหน้าฟาร์มไทย {}{}{} · ประวัติราคาไทย {}{}{} · "
        "ต้นทุนการผลิตพืช สศก. ไจอัป {} (ปีเพาะปลูก {}/{} ประมาณการ สศก. มี.ค. {}) · ภัยแล้ง {}{}{} · "
        "เงินเฟ้อ {}{} · GDP {} ไตรมาส {} · IMF WEO {} · ดัชนีราคาขายต่อ {}{} · ยอดจดทะเบียนถึง {}{} · "
        "หนี้ครัวเรือน สสช. SES {} · ค่าจ้าง สสช. LFS {} · ข้อมูลตรวจวัด {}{}{}",
}
