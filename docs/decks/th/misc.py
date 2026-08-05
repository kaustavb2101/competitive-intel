# -*- coding: utf-8 -*-
"""Thai catalogue, part 4 — pass-throughs, crop-mix rows and the price-panel captions.

Three kinds of string live here.

PASS-THROUGH. Province and amphoe names arrive from the pipeline already in Thai, and so do the
punctuation-only strings the layout emits. They still need a catalogue entry: a string with no entry
is reported as untranslated, and "0 untranslated" is the only signal that nothing was missed. Value
== key is the honest way to say "this is already Thai".

CROP MIX. Slide 07 prints each province's full published crop mix as one sentence, so the sentence
is a distinct string per province. Six variants, one entry each — mechanical, but the alternative is
translating crop names in the builder, which would put Thai in a script that also builds the
English deck.

PRICE PANELS. Slide 08's captions carry a unit and the belts a crop is grown in. Belt codes are
abbreviated hard (ตอ. / ตต.) because the panel is 2.36in wide and the caption cannot wrap.
"""

_PROVINCES = [
    # already Thai on arrival — province, amphoe and the province-with-a-number variants
    "กำแพงเพชร", "ขอนแก่น {}", "คอนสวรรค์", "ชัยภูมิ", "ชุมพร", "ตาพระยา", "นครนายก {}",
    "นครพนม", "นครราชสีมา", "นครสวรรค์", "นราธิวาส", "นราธิวาส {}", "บึงกาฬ", "บุรีรัมย์",
    "ปราจีนบุรี {}", "มุกดาหาร", "ยโสธร", "ระยอง", "สมุทรสงคราม", "สระแก้ว", "สิงห์บุรี",
    "สุราษฎร์ธานี", "สุรินทร์", "สุโขทัย", "หนองบัวลำภู", "หนองบุญมาก", "อรัญประเทศ",
    "อำนาจเจริญ", "อุดรธานี", "อุบลราชธานี", "เสิงสาง", "แกลง", "แม่ฮ่องสอน {}",
    # punctuation and bare-number layout strings
    "{}", "{}/{}", "{}{}", "฿{}", "—", "•",
]

STRINGS = {s: s for s in _PROVINCES}

STRINGS.update({
    # ------------------------------------------------ 02 the four questions
    "Is the economy\nthe problem?": "เศรษฐกิจ\nคือปัญหาหรือไม่",
    "Are crop prices\nthe problem?": "ราคาพืชผล\nคือปัญหาหรือไม่",
    "What is\ndeteriorating?": "อะไรที่กำลัง\nแย่ลง",
    "And the\nborrower?": "แล้วตัวผู้กู้\nล่ะ",

    # ------------------------------------------------ 07 crop mix, one sentence per province
    "Rice {}, Cassava {}, Sugarcane {}, Maize {}, Rubber {}, Oil palm <{}, Coconut <{}, "
    "Pineapple <{}":
        "ข้าว {}, มันสำปะหลัง {}, อ้อย {}, ข้าวโพด {}, ยางพารา {}, ปาล์มน้ำมัน <{}, มะพร้าว <{}, "
        "สับปะรด <{}",
    "Rice {}, Rubber {}, Cassava {}, Maize {}, Oil palm <{}, Sugarcane <{}, Coconut <{}, "
    "Pineapple <{}":
        "ข้าว {}, ยางพารา {}, มันสำปะหลัง {}, ข้าวโพด {}, ปาล์มน้ำมัน <{}, อ้อย <{}, มะพร้าว <{}, "
        "สับปะรด <{}",
    "Rice {}, Rubber {}, Sugarcane {}, Cassava {}, Oil palm <{}, Coconut <{}, Maize <{}, "
    "Pineapple <{}":
        "ข้าว {}, ยางพารา {}, อ้อย {}, มันสำปะหลัง {}, ปาล์มน้ำมัน <{}, มะพร้าว <{}, ข้าวโพด <{}, "
        "สับปะรด <{}",
    "Rice {}, Rubber {}, Sugarcane {}, Cassava {}, Oil palm <{}, Maize <{}, Coconut <{}":
        "ข้าว {}, ยางพารา {}, อ้อย {}, มันสำปะหลัง {}, ปาล์มน้ำมัน <{}, ข้าวโพด <{}, มะพร้าว <{}",
    "Rice {}, Sugarcane {}, Maize {}, Cassava {}, Rubber <{}, Oil palm <{}, Coconut <{}, "
    "Pineapple <{}":
        "ข้าว {}, อ้อย {}, ข้าวโพด {}, มันสำปะหลัง {}, ยางพารา <{}, ปาล์มน้ำมัน <{}, มะพร้าว <{}, "
        "สับปะรด <{}",
    "Rubber {}, Oil palm {}, Coconut {}, Rice <{}, Maize <{}, Pineapple <{}":
        "ยางพารา {}, ปาล์มน้ำมัน {}, มะพร้าว {}, ข้าว <{}, ข้าวโพด <{}, สับปะรด <{}",

    # ------------------------------------------------ 08 price-panel captions
    # C กลาง · E ตะวันออก · W ตะวันตก · N เหนือ · S ใต้ · Isan อีสาน — abbreviated to fit 2.36in
    "฿{} /กก. · C·E": "฿{} /กก. · กลาง·ตอ.",
    "฿{} /กก. · C·W·E": "฿{} /กก. · กลาง·ตต.·ตอ.",
    "฿{} /กก. · E·W·N": "฿{} /กก. · ตอ.·ตต.·เหนือ",
    "฿{} /กก. · Isan·N·E": "฿{} /กก. · อีสาน·เหนือ·ตอ.",
    "฿{} /กก. · North": "฿{} /กก. · เหนือ",
    "฿{} /กก. · South": "฿{} /กก. · ใต้",
    "฿{} /กก. · S·E": "฿{} /กก. · ใต้·ตอ.",
    "฿{} /กก. · S·E coast": "฿{} /กก. · ชายฝั่งใต้·ตอ.",
    "฿{} /ตัน · Isan·N·C": "฿{} /ตัน · อีสาน·เหนือ·กลาง",
    "฿{} /ร้อยผล · C·W": "฿{} /ร้อยผล · กลาง·ตต.",
    "฿{} /ร้อยผล · S·E": "฿{} /ร้อยผล · ใต้·ตอ.",
    "฿{} /ร้อยฟอง · C·E": "฿{} /ร้อยฟอง · กลาง·ตอ.",
})
