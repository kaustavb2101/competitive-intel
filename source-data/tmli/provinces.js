/**
 * WATCHER UNIVERSAL PROVINCE MAPPING (Knowledge Base Core)
 * This file serves as the single source of truth for Thai-to-English province names,
 * population data (NSO 2023), and AutoX branch distribution.
 */

export const THAI_PROVINCE_MAP = {
  'กรุงเทพมหานคร': 'Bangkok', 'สมุทรปราการ': 'Samut Prakan', 'นนทบุรี': 'Nonthaburi', 'ปทุมธานี': 'Pathum Thani',
  'นครปฐม': 'Nakhon Pathom', 'สมุทรสาคร': 'Samut Sakhon', 'ชลบุรี': 'Chon Buri', 'ระยอง': 'Rayong',
  'ฉะเชิงเทรา': 'Chachoengsao', 'ปราจีนบุรี': 'Prachin Buri', 'สระแก้ว': 'Sa Kaeo', 'จันทบุรี': 'Chanthaburi',
  'ตราด': 'Trat', 'นครราชสีมา': 'Nakhon Ratchasima', 'บุรีรัมย์': 'Buri Ram', 'สุรินทร์': 'Surin',
  'ศรีสะเกษ': 'Si Sa Ket', 'อุบลราชธานี': 'Ubon Ratchathani', 'ยโสธร': 'Yasothon', 'ชัยภูมิ': 'Chaiyaphum',
  'อำนาจเจริญ': 'Amnat Charoen', 'บึงกาฬ': 'Bueng Kan', 'หนองบัวลำภู': 'Nong Bua Lam Phu', 'ขอนแก่น': 'Khon Kaen',
  'อุดรธานี': 'Udon Thani', 'เลย': 'Loei', 'หนองคาย': 'Nong Khai', 'มหาสารคาม': 'Maha Sarakham',
  'ร้อยเอ็ด': 'Roi Et', 'กาฬสินธุ์': 'Kalasin', 'สกลนคร': 'Sakon Nakhon', 'นครพนม': 'Nakhon Phanom',
  'มุกดาหาร': 'Mukdahan', 'เชียงใหม่': 'Chiang Mai', 'ลำพูน': 'Lamphun', 'ลำปาง': 'Lampang',
  'อุตรดิตถ์': 'Uttaradit', 'แพร่': 'Phrae', 'น่าน': 'Nan', 'พะเยา': 'Phayao', 'เชียงราย': 'Chiang Rai',
  'แม่ฮ่องสอน': 'Mae Hong Son', 'นครสวรรค์': 'Nakhon Sawan', 'อุทัยธานี': 'Uthai Thani', 'กำแพงเพชร': 'Kamphaeng Phet',
  'ตาก': 'Tak', 'สุโขทัย': 'Sukhothai', 'พิษณุโลก': 'Phitsanulok', 'พิจิตร': 'Phichit', 'เพชรบูรณ์': 'Phetchabun',
  'ราชบุรี': 'Ratchaburi', 'กาญจนบุรี': 'Kanchanaburi', 'สุพรรณบุรี': 'Suphan Buri', 'สระบุรี': 'Saraburi',
  'นครนายก': 'Nakhon Nayok', 'พระนครศรีอยุธยา': 'Phra Nakhon Si Ayutthaya', 'อ่างทอง': 'Ang Thong',
  'ลพบุรี': 'Lop Buri', 'สิงห์บุรี': 'Sing Buri', 'ชัยนาท': 'Chai Nat', 'นครศรีธรรมราช': 'Nakhon Si Thammarat',
  'กระบี่': 'Krabi', 'พังงา': 'Phang Nga', 'ภูเก็ต': 'Phuket', 'สุราษฎร์ธานี': 'Surat Thani',
  'ระนอง': 'Ranong', 'ชุมพร': 'Chumphon', 'สงขลา': 'Songkhla', 'สตูล': 'Satun', 'ตรัง': 'Trang',
  'พัทลุง': 'Phatthalung', 'ปัตตานี': 'Pattani', 'ยะลา': 'Yala', 'นราธิวาส': 'Narathiwat',
  'ประจวบคีรีขันธ์': 'Prachuap Khiri Khan', 'เพชรบุรี': 'Phetchaburi', 'สมุทรสงคราม': 'Samut Songkhram'
};

// Fuzzy match aliases (common variations found in data.go.th and other datasets)
export const PROVINCE_ALIASES = {
  'Buriram': 'Buri Ram',
  'Ayutthaya': 'Phra Nakhon Si Ayutthaya',
  'Chonburi': 'Chon Buri',
  'Prachuap Khiri Khan': 'Prachuap Khiri Khan',
  'Prachuap Khirikhan': 'Prachuap Khiri Khan',
  'Si Sa Ket': 'Si Sa Ket',
  'Sisaket': 'Si Sa Ket'
};

export const PROVINCE_POP = {
  'Bangkok': 5494.5, 'Samut Prakan': 1290.3, 'Nonthaburi': 1155.6, 'Pathum Thani': 1147.5,
  'Nakhon Pathom': 924.8, 'Samut Sakhon': 561.0, 'Chon Buri': 1542.6, 'Rayong': 723.4,
  'Chachoengsao': 700.2, 'Prachin Buri': 462.1, 'Sa Kaeo': 548.3, 'Chanthaburi': 551.0,
  'Trat': 232.4, 'Nakhon Ratchasima': 2626.2, 'Buri Ram': 1577.6, 'Surin': 1386.0,
  'Si Sa Ket': 1462.6, 'Ubon Ratchathani': 1866.0, 'Yasothon': 534.9, 'Chaiyaphum': 1143.5,
  'Amnat Charoen': 374.8, 'Bueng Kan': 420.7, 'Nong Bua Lam Phu': 499.8,
  'Khon Kaen': 1789.6, 'Udon Thani': 1581.7, 'Loei': 636.9, 'Nong Khai': 513.5,
  'Maha Sarakham': 972.0, 'Roi Et': 1297.8, 'Kalasin': 977.5, 'Sakon Nakhon': 1142.5,
  'Nakhon Phanom': 709.3, 'Mukdahan': 342.5, 'Chiang Mai': 1765.7, 'Lamphun': 413.0,
  'Lampang': 748.4, 'Uttaradit': 462.0, 'Phrae': 461.3, 'Nan': 478.4, 'Phayao': 486.6,
  'Chiang Rai': 1289.4, 'Mae Hong Son': 282.7, 'Nakhon Sawan': 1069.6, 'Uthai Thani': 327.3,
  'Kamphaeng Phet': 717.9, 'Tak': 558.3, 'Sukhothai': 595.3, 'Phitsanulok': 862.4,
  'Phichit': 522.0, 'Phetchabun': 985.6, 'Ratchaburi': 867.8, 'Kanchanaburi': 879.7,
  'Suphan Buri': 826.0, 'Saraburi': 651.7, 'Nakhon Nayok': 268.0,
  'Phra Nakhon Si Ayutthaya': 800.0, 'Ang Thong': 284.4, 'Lop Buri': 757.8, 'Sing Buri': 210.1,
  'Chai Nat': 328.8, 'Nakhon Si Thammarat': 1542.1, 'Krabi': 461.2, 'Phang Nga': 282.0,
  'Phuket': 416.1, 'Surat Thani': 1060.7, 'Ranong': 179.5, 'Chumphon': 504.0, 'Songkhla': 1418.4,
  'Satun': 313.5, 'Trang': 628.9, 'Phatthalung': 530.4, 'Pattani': 715.4, 'Yala': 526.1, 'Narathiwat': 787.3
};

export const AUTOX_BRANCHES = {
  'Bangkok': 169, 'Samut Prakan': 102, 'Nonthaburi': 45, 'Pathum Thani': 38,
  'Nakhon Pathom': 28, 'Samut Sakhon': 22, 'Chon Buri': 102, 'Rayong': 48,
  'Chachoengsao': 31, 'Prachin Buri': 18, 'Sa Kaeo': 12, 'Chanthaburi': 15,
  'Trat': 8, 'Nakhon Ratchasima': 89, 'Buri Ram': 42, 'Surin': 38,
  'Si Sa Ket': 35, 'Ubon Ratchathani': 46, 'Yasothon': 18, 'Chaiyaphum': 24,
  'Amnat Charoen': 14, 'Bueng Kan': 9, 'Nong Bua Lam Phu': 16,
  'Khon Kaen': 67, 'Udon Thani': 58, 'Loei': 19, 'Nong Khai': 22,
  'Maha Sarakham': 28, 'Roi Et': 32, 'Kalasin': 24, 'Sakon Nakhon': 26,
  'Nakhon Phanom': 18, 'Mukdahan': 12, 'Chiang Mai': 52, 'Lamphun': 14,
  'Lampang': 22, 'Uttaradit': 12, 'Phrae': 11, 'Nan': 9, 'Phayao': 10,
  'Chiang Rai': 28, 'Mae Hong Son': 6, 'Nakhon Sawan': 32, 'Uthai Thani': 12,
  'Kamphaeng Phet': 15, 'Tak': 11, 'Sukhothai': 14, 'Phitsanulok': 24,
  'Phichit': 14, 'Phetchabun': 18, 'Ratchaburi': 22, 'Kanchanaburi': 18,
  'Suphan Buri': 20, 'Saraburi': 18, 'Nakhon Nayok': 9,
  'Phra Nakhon Si Ayutthaya': 32, 'Ang Thong': 10, 'Lop Buri': 24, 'Sing Buri': 8,
  'Chai Nat': 10, 'Nakhon Si Thammarat': 28, 'Krabi': 12, 'Phang Nga': 9,
  'Phuket': 18, 'Surat Thani': 22, 'Ranong': 6, 'Chumphon': 14, 'Songkhla': 32,
  'Satun': 8, 'Trang': 14, 'Phatthalung': 12, 'Pattani': 8, 'Yala': 7, 'Narathiwat': 6
};

/**
 * Standardizes a province name to the internal English key.
 * Handles Thai names, common aliases, and formatting variations.
 */
export function standardizeProvince(input) {
  if (!input) return null;
  const clean = String(input).trim();
  
  // 1. Direct Thai Mapping
  if (THAI_PROVINCE_MAP[clean]) return THAI_PROVINCE_MAP[clean];
  
  // 2. Exact English Key Match
  if (PROVINCE_POP[clean]) return clean;
  
  // 3. Alias Match (e.g., 'Buriram' -> 'Buri Ram')
  if (PROVINCE_ALIASES[clean]) return PROVINCE_ALIASES[clean];
  
  // 4. Fuzzy Thai Match (contains name)
  for (const [th, en] of Object.entries(THAI_PROVINCE_MAP)) {
    if (clean.includes(th) || th.includes(clean)) return en;
  }
  
  return clean; // Fallback
}
