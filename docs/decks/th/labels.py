# -*- coding: utf-8 -*-
"""Thai catalogue, part 1 of 3 — labels, headings, table headers, card captions.

Keys are the English string with every number punched out to `{}` (see Deck.tkey), so one entry
covers every data vintage. A template must not ask for more placeholders than its key carries, and
it may reorder them as {0}/{1} where Thai word order differs.

Names that stay Latin on purpose: vehicle brands and nameplates (the registrar files them that way
and a Thai transliteration would not match a DLT lookup), statistical agencies, and the currency
pair. Province names arrive from the data already in Thai and never reach this file.
"""

STRINGS = {
    # ---- pass through unchanged: brands, nameplates, symbols, belt shorthand
    "MG": "MG", "BYD": "BYD", "GWM": "GWM", "AION": "AION", "FORD": "FORD",
    "HONDA": "HONDA", "ISUZU": "ISUZU", "MAZDA": "MAZDA", "TOYOTA": "TOYOTA",
    "NISSAN": "NISSAN", "DEEPAL": "DEEPAL", "JAECOO": "JAECOO", "MITSUBISHI": "MITSUBISHI",
    "D-MAX": "D-MAX", "D-Max": "D-Max", "MU-X": "MU-X", "Mu-X": "Mu-X",
    "RANGER": "RANGER", "Ranger": "Ranger", "TRITON": "TRITON", "Triton": "Triton",
    "FORTUNER": "FORTUNER", "Fortuner": "Fortuner", "EVEREST": "EVEREST",
    "HILUX REVO": "HILUX REVO", "Hilux Revo": "Hilux Revo",
    "HILUX CHAMP": "HILUX CHAMP", "Hilux Champ": "Hilux Champ",
    "HONDA CITY": "HONDA CITY", "Honda City": "Honda City",
    "HONDA HR-V": "HONDA HR-V", "Honda Hr-V": "Honda Hr-V", "Honda Civic": "Honda Civic",
    "TOYOTA YARIS ATIV": "TOYOTA YARIS ATIV", "Toyota Yaris Ativ": "Toyota Yaris Ativ",
    "TOYOTA YARIS CROSS": "TOYOTA YARIS CROSS", "Toyota Yaris Cross": "Toyota Yaris Cross",
    "TOYOTA COROLLA CROSS": "TOYOTA COROLLA CROSS", "Toyota Corolla Cross": "Toyota Corolla Cross",
    "HONDA CITY HATCHBACK": "HONDA CITY HATCHBACK", "Honda City Hatchback": "Honda City Hatchback",
    "BYD DOLPHIN ({}KM-STD)": "BYD DOLPHIN ({}KM-STD)",
    "JAECOO {} EV LONG RANGE MAX": "JAECOO {} EV LONG RANGE MAX",
    "SPEI": "SPEI", "USD / THB": "USD / THB", "PPV": "PPV",
    "C · E": "กลาง · ตอ.", "S · E": "ใต้ · ตอ.", "C · W · E": "กลาง · ตต. · ตอ.",
    "E · W · N": "ตอ. · ตต. · เหนือ", "Isan · C": "อีสาน · กลาง", "S · E coast": "ชายฝั่งใต้ · ตอ.",
    "Central&BKK": "กลาง & กทม.",

    # ---- regions, one-word column heads, chips
    "Isan": "อีสาน", "North": "เหนือ", "South": "ใต้", "East": "ตะวันออก",
    "Car": "รถยนต์นั่ง", "Rai": "ไร่", "SME": "ธุรกิจส่วนตัว", "YoY": "เทียบปีก่อน",
    "new": "รุ่นใหม่", "Band": "ระดับ", "Beef": "เนื้อวัว", "Belt": "แหล่งผลิต",
    "Crop": "พืช", "Pork": "สุกร", "move": "เปลี่ยนแปลง", "rain": "ฝน",
    "Crops": "พืชผล", "Level": "ระดับน้ำ", "MIXED": "ผสม", "MEASURED": "วัดจริง",
    "Sugar": "น้ำตาล", "provs": "จังหวัด", "share": "สัดส่วน", "shock": "ผลกระทบ",
    "Office": "ออฟฟิศ", "Pickup": "รถกระบะ", "Region": "ภาค", "diesel": "ดีเซล",
    "region": "ภาค", "severe": "รุนแรง", "Chicken": "ไก่เนื้อ", "Coconut": "มะพร้าว",
    "Factory": "โรงงาน", "Segment": "หมวด", "Vietnam": "เวียดนาม", "tripped": "สัญญาณ",
    "weakest": "อ่อนสุด", "District": "อำเภอ", "Malaysia": "มาเลเซีย", "Province": "จังหวัด",
    "Rambutan": "เงาะ", "Thailand": "ไทย", "off peak": "จากจุดสูงสุด", "Fisheries": "ประมง",
    "Indonesia": "อินโดนีเซีย", "Inflation": "เงินเฟ้อ", "Livestock": "ปศุสัตว์",
    "Nameplate": "รุ่นรถ", "Pineapple": "สับปะรด", "Transport": "ขนส่ง",
    "backwards": "ถอยหลัง", "incumbent": "เจ้าตลาดเดิม", "lead crop": "พืชหลัก",
    "new firms": "ธุรกิจใหม่", "no series": "ไม่มีข้อมูลรายเดือน", "White shrimp": "กุ้งขาว",
    "Unemployment": "การว่างงาน", "unemployment": "การว่างงาน", "labour force": "กำลังแรงงาน",
    "Passenger car": "รถยนต์นั่ง", "below cost": "ต่ำกว่าต้นทุน",
    "Philippines": "ฟิลิปปินส์", "Policy rate": "ดอกเบี้ยนโยบาย",
    "Rain gauges": "สถานีวัดฝน", "River ≥high": "แม่น้ำเกินระดับ",
    "planted rai": "พื้นที่ (ไร่)", "rivers high": "แม่น้ำเกินระดับ",
    "Driest cells": "พื้นที่แล้งสุด", "Extreme band": "ระดับรุนแรงมาก",
    "Diesel share": "สัดส่วนดีเซล", "GDP growth": "การเติบโต GDP",
    "System NPL": "NPL ทั้งระบบ", "Registered": "จดทะเบียนสะสม",
    "Wettest today": "ฝนมากสุดวันนี้", "Scope, stated": "ขอบเขต ระบุชัด",
    "employee wage": "ค่าจ้างลูกจ้าง", "seasonal idle": "ว่างงานตามฤดูกาล",
    "vehicle fleet": "รถจดทะเบียน", "districts dry": "อำเภอแล้ง",
    "household debt": "หนี้ครัวเรือน", "crop economics": "เศรษฐกิจของพืช",
    "rain vs normal": "ฝนเทียบค่าปกติ", "income shock": "กระทบรายได้",
    "farm vs wage": "เกษตร/ค่าจ้าง", "of planted area": "ของพื้นที่ปลูก",
    "What follows": "ลำดับเรื่อง", "Govt debt/GDP": "หนี้รัฐ/GDP",
    "New car brands": "แบรนด์รถยนต์ใหม่", "Third PU brand": "แบรนด์กระบะอันดับ 3",
    "Car nameplates": "รุ่นรถยนต์นั่ง", "PU + PPV brand": "แบรนด์กระบะ + PPV",
    "Car brand": "แบรนด์รถยนต์", "PA nameplate": "รุ่นรถยนต์นั่ง", "PU nameplate": "รุ่นกระบะ",
    "Car share": "สัดส่วนรถยนต์", "PU share": "สัดส่วนกระบะ", "Moto share": "สัดส่วนจักรยานยนต์",
    "PU turnover": "อัตราเปลี่ยนมือ กระบะ", "Car turnover": "อัตราเปลี่ยนมือ รถยนต์",
    "Moto turnover": "อัตราเปลี่ยนมือ จยย.", "BEV share": "สัดส่วน BEV",
    "% heavy+": "% ฝนหนัก", "farm ฿/mo": "เกษตร ฿/ด.",
    "Farming ฿/mo": "เกษตร ฿/ด.", "latest, ฿": "ล่าสุด ฿",
    "Farm-gate YoY": "หน้าฟาร์ม ปีก่อน", "Farm-gate {}m": "ราคาหน้าฟาร์ม {} เดือน",
    "share of PA": "สัดส่วนรถยนต์", "share of PU": "สัดส่วนกระบะ",
    "share of our accounts": "สัดส่วนบัญชีทั้งหมดของเรา",
    "Farming accounts in belt": "บัญชีอาชีพเกษตรในแหล่งผลิต",
    "Falling at the farm gate": "ราคาหน้าฟาร์มที่ลดลง",
    "weakest farming province": "จังหวัดเกษตรที่อ่อนสุด",
    "crop mix, % of planted area": "สัดส่วนพืช % ของพื้นที่ปลูก",
    "Largest planted areas": "พื้นที่ปลูกมากสุด",
    "District-crop cells": "อำเภอ × พืช",
    "Districts in drought": "อำเภอที่แล้ง",
    "Provinces with heavy rain": "จังหวัดที่ฝนหนัก",
    "Stations above high mark": "สถานีน้ำเกินระดับเฝ้าระวัง",
    "Ground that floods anyway": "พื้นที่ที่ท่วมซ้ำซาก",
    "Crops with a Thai farm-gate price": "พืชที่มีราคาหน้าฟาร์มไทย",
    "Median province crop-income shock": "ผลกระทบรายได้พืช ค่ากลางรายจังหวัด",
    "Provinces where it went backwards": "จังหวัดที่รายได้ลดลง",
    "Pickup + PPV nameplates": "รุ่นกระบะ + PPV",
    "World price, five years": "ราคาโลก ห้าปี",
    "All used vehicles": "รถมือสองทุกประเภท",
    "BoT used-vehicle price index": "ดัชนีราคารถมือสอง ธปท.",
    "first registrations that year": "จดทะเบียนครั้งแรกในปีนั้น",
    "off all-time peak": "จากจุดสูงสุดตลอดกาล",
    "Biggest PA nameplate": "รุ่นรถยนต์ที่ใหญ่สุด",
    "Biggest PU nameplate": "รุ่นกระบะที่ใหญ่สุด",
    "registered pickups nationally · {} YoY": "กระบะจดทะเบียนทั้งประเทศ · {} เทียบปีก่อน",
    "districts at the extreme drought band": "อำเภอที่อยู่ในระดับแล้งรุนแรงมาก",
    "electrified {} — not a factor this quarter": "ไฟฟ้ารวม {} — ยังไม่ใช่ปัจจัยในไตรมาสนี้",

    # ---- bilingual card labels already carrying Thai in the English deck
    "Rice ข้าว": "ข้าว", "Rubber ยางพารา": "ยางพารา", "Sugar น้ำตาล": "น้ำตาล",
    "Palm oil ปาล์มน้ำมัน": "ปาล์มน้ำมัน", "Rubber (ยาง)": "ยางพารา",
    "Cassava (มัน)": "มันสำปะหลัง", "Pickup (รถกระบะ)": "รถกระบะ",
    "Rice, wet (นาปี)": "ข้าวนาปี", "Pork  สุกร": "สุกร", "Lime  มะนาว": "มะนาว",
    "Chicken  ไก่": "ไก่เนื้อ", "Eggs  ไข่ไก่": "ไข่ไก่", "Coconut  มะพร้าว": "มะพร้าว",
    "Rice  ข้าวหอมมะลิ": "ข้าวหอมมะลิ", "Rubber  ยางพารา": "ยางพารา",
    "Cassava  มันสำปะหลัง": "มันสำปะหลัง", "Palm oil  ปาล์มน้ำมัน": "ปาล์มน้ำมัน",
    "White shrimp  กุ้งขาว": "กุ้งขาว", "Pineapple  สับปะรดโรงงาน": "สับปะรดโรงงาน",
    "Maize  ข้าวโพดเลี้ยงสัตว์": "ข้าวโพดเลี้ยงสัตว์",
    "Car stock รถยนต์นั่ง": "รถยนต์นั่งจดทะเบียน", "Pickup stock รถกระบะ": "รถกระบะจดทะเบียน",
    "Pickup + PPV รถกระบะ": "รถกระบะ + PPV", "Passenger car รถยนต์นั่ง": "รถยนต์นั่ง",
    "Districts dry ภัยแล้ง": "อำเภอแล้ง", "Informal work นอกระบบ": "แรงงานนอกระบบ",
    "Labour force กำลังแรงงาน": "กำลังแรงงาน", "Vehicle fleet รถจดทะเบียน": "รถจดทะเบียน",
    "Household debt หนี้ครัวเรือน": "หนี้ครัวเรือน",
    "No cushion กันชนทางการเงิน": "ไม่มีกันชนทางการเงิน",
    "Tourist arrivals นักท่องเที่ยว": "นักท่องเที่ยวต่างชาติ",
    "Rice ข้าว ($/mt)": "ข้าว ($/ตัน)", "Sugar น้ำตาล ($/kg)": "น้ำตาล ($/กก.)",
    "Rubber ยางพารา ($/kg)": "ยางพารา ($/กก.)",
    "Palm oil ปาล์มน้ำมัน ($/mt)": "ปาล์มน้ำมัน ($/ตัน)",

    # ---- interpolated fragments
    "{}M": "{} ล้าน", "{}k": "{}k", "{}-yr": "{} ปี", "{}m {}": "{} เดือน {}",
    "YoY {}": "เทียบปีก่อน {}", "{}m YoY": "{} เดือน เทียบปีก่อน", "{}m YoY †": "{} เดือน เทียบปีก่อน †",
    "{}m low": "ต่ำสุด {} เดือน", "{}m high": "สูงสุด {} เดือน", "{} of {}": "{} จาก {}",
    "{} months": "{} เดือน", "{}-month move": "เปลี่ยนแปลง {} เดือน",
    "{}-month units": "หน่วย {} เดือน", "{}-month units †": "หน่วย {} เดือน †",
    "{}-yr peak, US$": "สูงสุด {} ปี US$", "vs {} yrs ago": "เทียบ {} ปีก่อน",
    "vs {} base": "เทียบฐานปี {}", "{}-yr": "{} ปี", "{} · WATER": "{} · น้ำ",
    "Rice {}": "ข้าว {}", "Rubber {}": "ยางพารา {}", "Aug ’{}": "ส.ค. ’{}",
    "Max mm/{}h": "มม./{} ชม.", "Cars, {}": "รถยนต์นั่ง ปี {}",
    "Pickups + PPV, {}": "กระบะ + PPV ปี {}", "{} over four years": "{} ในสี่ปี",
    "latest ({}{})": "ล่าสุด ({}{})", "diesel {} · EV {}": "ดีเซล {} · EV {}",
    "Top {} car brands": "แบรนด์รถยนต์ 5 อันดับแรก {}",
    "Top {} pickup brands": "แบรนด์กระบะ {} อันดับแรก",
    "Top {} PA nameplates": "รุ่นรถยนต์ {} อันดับแรก",
    "Top {} PU nameplates": "รุ่นกระบะ {} อันดับแรก",
    "{} YoY · {} since {}": "{} เทียบปีก่อน · {} ตั้งแต่ปี {}",
    "of GDP · BIS · {}-Q{}": "ของ GDP · BIS · {} ไตรมาส {}",
    "ECB reference · {}{}{}": "อัตราอ้างอิง ECB · {}{}{}",
    "Bank of Thailand · {}{}": "ธนาคารแห่งประเทศไทย · {}{}",
    "headline CPI YoY · TPSO · {}{}": "เงินเฟ้อทั่วไป เทียบปีก่อน · TPSO · {}{}",
    "trailing {}m · {} YoY · BoT {}{}": "ย้อนหลัง {} เดือน · {} เทียบปีก่อน · ธปท. {}{}",
    "YoY · measured quarter, not a projection · NESDC {}-Q{}":
        "เทียบปีก่อน · ไตรมาสที่วัดจริง ไม่ใช่ประมาณการ · สศช. {} ไตรมาส {}",
    "IMF {} projection": "ประมาณการ IMF ปี {}",
    "{}  Rain (ฝน)  —  rainfall < {} of normal": "{}  ฝน  —  ปริมาณฝน < {} ของค่าปกติ",
    "{}  Crop (พืชหลัก)  —  lead crop pays below cost":
        "{}  พืชหลัก  —  พืชหลักขายได้ต่ำกว่าต้นทุน",
    "{}  Unemployment (การว่างงาน)  —  unemployment ≥ {}":
        "{}  การว่างงาน  —  อัตราว่างงาน ≥ {}",
    "{}  Debt (หนี้)  —  debt-to-income ≥ {} of a year's income":
        "{}  หนี้  —  หนี้ต่อรายได้ ≥ {} ของรายได้ทั้งปี",
    "{} of {} districts · {} of {} rivers high":
        "{} จาก {} อำเภอ · แม่น้ำเกินระดับ {} จาก {} สถานี",
    "of {} ({}) · SPEI mean {}": "จาก {} ({}) · ค่าเฉลี่ย SPEI {}",
    "of {} ({}) · live · {}{}{}": "จาก {} ({}) · เรียลไทม์ · {}{}{}",
    "latest daily reading · {}{}{}": "ค่าล่าสุดรายวัน · {}{}{}",
    "{} of {} branch locations flooded in {}+ of {} years":
        "ที่ตั้งสาขา {} จาก {} แห่ง เคยท่วม {}+ ใน {} ปี",
    "of {} measured cells at severe drought or worse":
        "จาก {} อำเภอ×พืชที่วัดได้ อยู่ในระดับแล้งรุนแรงขึ้นไป",
    "unemployment {} · seasonal idle {}, {}k waiting":
        "ว่างงาน {} · ว่างตามฤดูกาล {} คิดเป็น {}k คน",
    "no payslip or social cover · core borrower base ({})":
        "ไม่มีสลิปเงินเดือนหรือประกันสังคม · ฐานลูกค้าหลักของเรา ({})",
    "debt ÷ monthly income, all households · {} carry debt":
        "หนี้ ÷ รายได้ต่อเดือน ทุกครัวเรือน · {} มีหนี้",
    "savings buffer, not debt — would last under {} months without income":
        "กันชนเงินออม ไม่ใช่หนี้ — อยู่ได้ไม่ถึง {} เดือนหากขาดรายได้",
    "of the {}M fleet — what the market runs on today":
        "จากรถ {} ล้านคัน — สิ่งที่ตลาดใช้อยู่วันนี้",
    "of the {} pickups and PPVs registered in {} months":
        "จากกระบะและ PPV {} คันที่จดทะเบียนใน {} เดือน",
    "of the {} cars — the same five-model test, less than half the answer":
        "จากรถยนต์ {} คัน — เกณฑ์ห้ารุ่นเดียวกัน ได้ไม่ถึงครึ่ง",
    "PA nameplates — share of the {}-unit car market":
        "รุ่นรถยนต์ — สัดส่วนของตลาดรถยนต์ {} คัน",
    "PU nameplates — share of the {}-unit pickup + PPV market":
        "รุ่นกระบะ — สัดส่วนของตลาดกระบะ + PPV {} คัน",
    "Pickup + PPV — {} registered in {} months": "กระบะ + PPV — จดทะเบียน {} คันใน {} เดือน",
    "Passenger car — {} registered in {} months": "รถยนต์นั่ง — จดทะเบียน {} คันใน {} เดือน",
    "Pickup + PPV — registrations by month, {}{} → {}{}":
        "กระบะ + PPV — ยอดจดทะเบียนรายเดือน {}{} → {}{}",
    "Passenger car — registrations by month, {}{} → {}{}":
        "รถยนต์นั่ง — ยอดจดทะเบียนรายเดือน {}{} → {}{}",
    "HILUX REVO · {} units · {} YoY": "HILUX REVO · {} คัน · {} เทียบปีก่อน",
    "TOYOTA YARIS ATIV · {} units · {} YoY": "TOYOTA YARIS ATIV · {} คัน · {} เทียบปีก่อน",
    "FORD · next is MITSUBISHI at {}": "FORD · ถัดไปคือ MITSUBISHI ที่ {}",
    "TOYOTA + ISUZU · was {} a year ago": "TOYOTA + ISUZU · ปีก่อนอยู่ที่ {}",
    "TOYOTA + HONDA · down {} points in a year": "TOYOTA + HONDA · ลดลง {} จุดในหนึ่งปี",
    "BYD + MG + Jaecoo + AION + Deepal · no Thai residual record":
        "BYD + MG + Jaecoo + AION + Deepal · ไม่มีสถิติราคามือสองในไทย",
    "{}m trend ex-flag, units/mo": "แนวโน้ม {} ด. ตัดเดือนผิดปกติ คัน/ด.",
    "Index, {} = {} · monthly, {}{} → {}{}": "ดัชนี {} = {} · รายเดือน {}{} → {}{}",
    "World price rebased to {} at {}{} · {} monthly observations":
        "ราคาโลก ปรับฐานเป็น {} ณ {}{} · ข้อมูลรายเดือน {} จุด",
    "Thai banking-system NPL หนี้เสีย, % of loans · {} quarters":
        "หนี้เสีย (NPL) ทั้งระบบธนาคารไทย, % ของสินเชื่อ · {} ไตรมาส",
    "rice, rubber, sugarcane, oil palm, cassava, maize, coconut, pineapple":
        "ข้าว ยางพารา อ้อย ปาล์มน้ำมัน มันสำปะหลัง ข้าวโพด มะพร้าว สับปะรด",
    "coconut {}, pineapple {}, sugarcane {} year on year":
        "มะพร้าว {} สับปะรด {} อ้อย {} เทียบปีก่อน",
    "all four are coconut belts on the western gulf":
        "ทั้งสี่จังหวัดอยู่ในแหล่งปลูกมะพร้าวฝั่งอ่าวไทยตะวันตก",
    "most of the country gained from this price round":
        "ประเทศส่วนใหญ่ได้ประโยชน์จากราคารอบนี้",
    "Restricted Data – Reproduction is prohibited": "ข้อมูลจำกัดการเข้าถึง – ห้ามทำซ้ำ",
}
