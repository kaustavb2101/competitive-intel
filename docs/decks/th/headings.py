# -*- coding: utf-8 -*-
"""Thai catalogue, part 2 of 3 — slide eyebrows, titles, bullets and callouts.

The eyebrows are the numbered rails down the left of each slide ("03 · COMMODITY BOARD"). They keep
their number and separator so the Thai and English decks can be read side by side page for page.
"""

STRINGS = {
    # ---- eyebrows
    "THE ANSWER FIRST": "คำตอบก่อน",
    "{} · MACRO OVERLAY": "{} · ภาพรวมเศรษฐกิจ",
    "{} · CONDITIONS ON THE GROUND": "{} · สภาพจริงในพื้นที่",
    "{} · COMMODITY BOARD": "{} · กระดานราคาสินค้าเกษตร",
    "{} · FIVE YEARS OF PRICE": "{} · ราคาห้าปี",
    "{} · THE CROP BELTS": "{} · แหล่งเพาะปลูก",
    "{} · EVERY CROP AT THE FARM GATE": "{} · ทุกสินค้าเกษตร ณ ราคาหน้าฟาร์ม",
    "{} · INCOME RIGHT NOW, BY REGION": "{} · รายได้ ณ ปัจจุบัน รายภาค",
    "{} · WATER": "{} · น้ำ",
    "{} · WHERE TO REACH OUT FIRST": "{} · ควรติดต่อที่ไหนก่อน",
    "{} · Collateral": "{} · หลักประกัน",
    "{}A · RESALE VALUE": "{}A · มูลค่าขายต่อ",
    "{}B · COLLATERAL SUPPLY": "{}B · อุปทานหลักประกัน",
    "{}C · BRAND CONCENTRATION": "{}C · การกระจุกตัวของแบรนด์",
    "{}D · THE NAMEPLATES": "{}D · รุ่นรถ",
    "{}F · FOUR YEARS OF NAMEPLATES": "{}F · รุ่นรถ ย้อนหลังสี่ปี",
    "{}E · THE SECOND-HAND MARKET": "{}E · ตลาดรถมือสอง",
    "{} · SO WHAT": "{} · แล้วอย่างไรต่อ",

    # ---- cover + titles
    "Macro: the conditions\nwe are lending into.":
        "เศรษฐกิจมหภาค: สภาพแวดล้อม\nที่เราปล่อยสินเชื่ออยู่",
    "MCOM · Wednesday {} August {} · AutoX / บริษัท ออโต้ เอกซ์ จำกัด (เงินไชโย)":
        "MCOM · วันพุธที่ {} สิงหาคม {} · AutoX / บริษัท ออโต้ เอกซ์ จำกัด (เงินไชโย)",
    "Four questions about the world outside the company.":
        "สี่คำถามเกี่ยวกับโลกภายนอกบริษัท",
    "Benign at home, slowest in the region, and system arrears are turning.":
        "ในประเทศยังนิ่ง แต่โตช้าที่สุดในภูมิภาค และหนี้เสียทั้งระบบเริ่มกลับทิศ",
    "Five lenses, from the country down to a district.":
        "ห้ามุมมอง ตั้งแต่ระดับประเทศลงถึงระดับอำเภอ",
    "The world index says tailwind. The Thai farm gate does not.":
        "ดัชนีโลกบอกว่าลมส่ง แต่ราคาหน้าฟาร์มไทยไม่ได้บอกอย่างนั้น",
    "Sugar has not fallen for a year. It has fallen for four.":
        "น้ำตาลไม่ได้ลดลงแค่หนึ่งปี แต่ลดลงมาสี่ปีแล้ว",
    "Which crop each region grows, and what the price round did to its income.":
        "แต่ละภาคปลูกอะไร และราคารอบนี้ทำอะไรกับรายได้ของเขา",
    "What the grower is paid, and which way it has moved.":
        "เกษตรกรได้รับเงินเท่าไร และราคาเคลื่อนไปทางไหน",
    "What each occupation earns, where the floor is, and which way it moved.":
        "แต่ละอาชีพมีรายได้เท่าไร จุดต่ำสุดอยู่ตรงไหน และเคลื่อนไปทางใด",
    "Where it is driest, and where it is wettest — right now.":
        "ที่ไหนแล้งที่สุด และที่ไหนน้ำมากที่สุด — ณ ตอนนี้",
    "Provinces ranked by how many stress signals tripped.":
        "จังหวัดเรียงตามจำนวนสัญญาณความเครียดที่เข้าเงื่อนไข",
    "This is the half with a decision attached.":
        "ครึ่งหลังนี้คือส่วนที่มีการตัดสินใจผูกอยู่",
    "The fall has stopped. The level has not recovered.":
        "ราคาหยุดตกแล้ว แต่ระดับยังไม่ฟื้น",
    "Two vehicle markets, moving opposite ways.":
        "ตลาดรถสองตลาด เคลื่อนไปคนละทาง",
    "Two vehicle markets, and only one is holding its shape.":
        "ตลาดรถสองตลาด และมีเพียงตลาดเดียวที่ยังรักษารูปทรงไว้ได้",
    "Top {} pickups are {} of the market. The top car is {}.":
        "กระบะ {} รุ่นแรกคิดเป็น {} ของตลาด ส่วนรถยนต์รุ่นที่ใหญ่ที่สุดมีเพียง {}",
    "Pickups entering the road are down {} since {}. Cars are up {}.":
        "กระบะที่เข้าสู่ท้องถนนลดลง {} ตั้งแต่ปี {} ขณะที่รถยนต์เพิ่มขึ้น {}",
    "Pickups are {} of the parc — cars {}, motorcycles {}.":
        "กระบะคิดเป็น {} ของรถทั้งหมด — รถยนต์ {} จักรยานยนต์ {}",
    "Five things the macro picture asks of us.":
        "ห้าสิ่งที่ภาพเศรษฐกิจเรียกร้องจากเรา",

    # ---- section-lead sentences and bullets
    "Scope: the Macro tab — external conditions only. The economy, crop prices and the used-vehicle "
    "market, all published by someone else. What any of it costs us is the Exposure and Risk "
    "conversation; competition and the branch views are separate again.":
        "ขอบเขต: แท็บ Macro — เฉพาะปัจจัยภายนอกเท่านั้น เศรษฐกิจ ราคาสินค้าเกษตร และตลาดรถมือสอง "
        "ทั้งหมดเผยแพร่โดยหน่วยงานอื่น ส่วนผลกระทบต่อพอร์ตของเราเป็นเรื่องของแท็บ Exposure และ Risk "
        "ขณะที่การแข่งขันและมุมมองรายสาขาแยกออกไปอีกส่วนหนึ่ง",
    "{}–{}  macro backdrop        {}–{}  agriculture: prices, belts, cost, income, water        "
    "{}  where to reach out first        {}  collateral        {}  what it asks of us":
        "{}–{}  ภาพเศรษฐกิจ        {}–{}  เกษตร: ราคา แหล่งผลิต ต้นทุน รายได้ น้ำ        "
        "{}  ควรติดต่อที่ไหนก่อน        {}  หลักประกัน        {}  แล้วอย่างไรต่อ",
    "Monthly income now, by region and job — each region set against its own wage.":
        "รายได้ต่อเดือน ณ ปัจจุบัน แยกตามภาคและอาชีพ — เทียบกับค่าจ้างของภาคนั้นเอง",
    "Ordered by signals tripped; ties broken on debt + unemployment.":
        "เรียงตามจำนวนสัญญาณที่เข้าเงื่อนไข หากเท่ากันตัดสินด้วยหนี้ + การว่างงาน",
    "Farm gate (ราคาที่เกษตรกรขายได้) = what the farmer is paid at first sale — before trading, "
    "milling or transport take a cut.":
        "ราคาหน้าฟาร์ม (ราคาที่เกษตรกรขายได้) = เงินที่เกษตรกรได้รับเมื่อขายครั้งแรก — "
        "ก่อนที่พ่อค้าคนกลาง โรงสี หรือค่าขนส่งจะหักส่วนแบ่งไป",
    "Seventeen of the {} commodities we track have a measured Thai farm-gate price "
    "(ราคาที่เกษตรกรขายได้). Eight are falling year on year.":
        "สินค้าเกษตร 17 จากทั้งหมด {} รายการที่เราติดตาม มีราคาหน้าฟาร์มไทยที่วัดได้จริง "
        "(ราคาที่เกษตรกรขายได้) และแปดรายการกำลังลดลงเมื่อเทียบกับปีก่อน",
    "Six months beside the year: they disagree on direction more often than they agree on size.":
        "ดูหกเดือนคู่กับหนึ่งปี: ทั้งสองชี้คนละทิศบ่อยกว่าที่จะเห็นตรงกันเรื่องขนาด",
    "The last column is OUR farming customers living in that belt — the only loan-book number in "
    "this deck.":
        "คอลัมน์สุดท้ายคือลูกค้าอาชีพเกษตรของเราที่อาศัยอยู่ในแหล่งผลิตนั้น — "
        "เป็นตัวเลขเดียวจากพอร์ตสินเชื่อในเอกสารชุดนี้",
    "Seventeen commodities have a measured Thai farm-gate price (ราคาที่เกษตรกรขายได้). Twelve "
    "also have a real monthly price series — those are the lines below.":
        "สินค้าเกษตร 17 รายการมีราคาหน้าฟาร์มไทยที่วัดได้จริง (ราคาที่เกษตรกรขายได้) "
        "และ 12 รายการมีข้อมูลราคารายเดือนจริง — คือเส้นกราฟด้านล่างนี้",
    "Year on year and six months disagree on direction for three of them. A single annual number "
    "can point the wrong way.":
        "สามรายการมีทิศทางไม่ตรงกันระหว่างเทียบปีก่อนกับหกเดือน "
        "ตัวเลขรายปีเพียงตัวเดียวจึงอาจชี้ผิดทางได้",
    "Every line is scaled to its own range: read the shape, not the height.":
        "เส้นกราฟแต่ละเส้นปรับสเกลตามช่วงของตัวเอง: ให้ดูรูปทรง ไม่ใช่ความสูง",
    "Priced but not plotted — no monthly series: Sugar {} (annual, administered) · Rambutan {} · "
    "Beef {} · Durian {} · Longan {}":
        "มีราคาแต่ไม่ได้พล็อตกราฟ — ไม่มีข้อมูลรายเดือน: น้ำตาล {} (รายปี ราคาประกาศ) · เงาะ {} · "
        "เนื้อวัว {} · ทุเรียน {} · ลำไย {}",
    "SPEI (ภัยแล้ง, drought) is modelled once a month — how the season has gone, not today’s "
    "weather.":
        "SPEI (ภัยแล้ง) เป็นแบบจำลองที่ปรับเดือนละครั้ง — บอกว่าฤดูกาลเป็นอย่างไร ไม่ใช่อากาศวันนี้",
    "ThaiWater is measured every day — rain gauges and river levels (น้ำท่วม, flood), live.":
        "ThaiWater วัดจริงทุกวัน — สถานีวัดฝนและระดับน้ำในแม่น้ำ (น้ำท่วม) แบบเรียลไทม์",
    "GISTDA is a separate {}-year census — ground that has flooded before, not what is happening "
    "now.":
        "GISTDA เป็นสำมะโนแยกต่างหากย้อนหลัง {} ปี — พื้นที่ที่เคยท่วมมาก่อน ไม่ใช่สิ่งที่เกิดขึ้นตอนนี้",
    "Drought (ภัยแล้ง) — worst planted-area cells": "ภัยแล้ง — พื้นที่เพาะปลูกที่หนักที่สุด",
    "Rain & rivers (น้ำท่วม) — worst today, live": "ฝนและแม่น้ำ (น้ำท่วม) — หนักที่สุดวันนี้ เรียลไทม์",
    "Severe drought at planting means a lighter harvest and less cash this season.":
        "ภัยแล้งรุนแรงช่วงเพาะปลูกหมายถึงผลผลิตน้อยลงและเงินสดน้อยลงในฤดูกาลนี้",
    "High rivers and heavy rain threaten roads, fields and branches right now — today’s reading, "
    "not a forecast.":
        "ระดับน้ำสูงและฝนหนักกำลังคุกคามถนน ไร่นา และสาขาในตอนนี้ — เป็นค่าที่อ่านได้วันนี้ ไม่ใช่พยากรณ์",
    "DLT first registrations, AutoX’s own pickup definition — any pickup or PPV, any class. Six- "
    "and {}-month windows, side by side.":
        "ยอดจดทะเบียนครั้งแรกของกรมการขนส่งทางบก ตามนิยามกระบะของ AutoX เอง — กระบะหรือ PPV ทุกประเภท "
        "เทียบหน้าต่างหกเดือนกับ {} เดือนคู่กัน",
    "† flagged months in this window: {}{} {}{} — registrations pulled forward before an incentive "
    "deadline. Only the last is stripped from the trend column; both YoY columns keep it.":
        "† เดือนที่ถูกตั้งข้อสังเกตในช่วงนี้: {}{} {}{} — ยอดจดทะเบียนถูกเร่งมาก่อนหมดเขตมาตรการส่งเสริม "
        "ตัดออกเฉพาะเดือนสุดท้ายจากคอลัมน์แนวโน้ม ส่วนคอลัมน์เทียบปีก่อนทั้งสองยังคงนับรวมไว้",
    "Top {} pickup nameplates cover {} of the market — priced off years of Thai resale history.":
        "รุ่นกระบะ {} อันดับแรกครอง {} ของตลาด — ตีราคาได้จากสถิติราคามือสองในไทยหลายปี",
    "Top {} car nameplates cover only {}, and the single biggest is just {}.":
        "รุ่นรถยนต์ {} อันดับแรกครองเพียง {} และรุ่นที่ใหญ่ที่สุดมีแค่ {}",
    "New brands — BYD, MG, Jaecoo, AION, Deepal — carry no Thai resale record; some registered for "
    "the first time this year.":
        "แบรนด์ใหม่ — BYD, MG, Jaecoo, AION, Deepal — ไม่มีสถิติราคามือสองในไทย บางรุ่นเพิ่งจดทะเบียนปีนี้เป็นปีแรก",
    "An advance rate is set per model. PU is five rows we can price. PA is a long tail we cannot, "
    "yet.":
        "อัตราปล่อยกู้กำหนดเป็นรายรุ่น ฝั่งกระบะมีห้าแถวที่เราตีราคาได้ ส่วนรถยนต์เป็นหางยาวที่เรายังตีราคาไม่ได้",
    "Only ‘latest’ is converted to baht — today’s FX is right for today’s price, not a {}–{} one, "
    "so ‘{}-yr peak’ stays in US$.":
        "แปลงเป็นบาทเฉพาะช่อง ‘ล่าสุด’ — อัตราแลกเปลี่ยนวันนี้ใช้กับราคาวันนี้ ไม่ใช่ราคาปี {}–{} "
        "ช่อง ‘จุดสูงสุด {} ปี’ จึงคงเป็นดอลลาร์",
}
