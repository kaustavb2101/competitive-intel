/**
 * PROVINCIAL HOUSEHOLD DEBT & FINANCIAL RESILIENCE
 * Sources:
 *   - debtToIncome, stressIndex: BOT Household Debt Regional Data Q4/2024
 *   - debtPerHousehold (THB): NSO SES 2566 (catalog.nso.go.th/dataset/0705_08_0009)
 *     parsed via scripts/parse-nso-debt.cjs → data/nso-ses-debt-2566.json
 */

// NSO SES 2566 debt-per-household values (THB), all 77 provinces
const _NSO_DEBT = {
  "Amnat Charoen": 369739, "Ang Thong": 128630, "Bangkok": 88856,
  "Bueng Kan": 189021, "Buri Ram": 216500, "Chachoengsao": 73913,
  "Chai Nat": 246575, "Chaiyaphum": 234837, "Chanthaburi": 191578,
  "Chiang Mai": 215821, "Chiang Rai": 193540, "Chon Buri": 282402,
  "Chumphon": 242083, "Kalasin": 276654, "Kamphaeng Phet": 247710,
  "Kanchanaburi": 166875, "Khon Kaen": 280791, "Krabi": 226547,
  "Lampang": 238044, "Lamphun": 217019, "Loei": 281620,
  "Lop Buri": 187476, "Mae Hong Son": 131705, "Maha Sarakham": 285706,
  "Mukdahan": 207694, "Nakhon Nayok": 176869, "Nakhon Pathom": 185534,
  "Nakhon Phanom": 247476, "Nakhon Ratchasima": 322819, "Nakhon Sawan": 198261,
  "Nakhon Si Thammarat": 197765, "Nan": 181434, "Narathiwat": 161015,
  "Nong Bua Lam Phu": 310867, "Nong Khai": 233625, "Nonthaburi": 113566,
  "Pathum Thani": 193100, "Pattani": 167014, "Phang Nga": 156498,
  "Phatthalung": 195011, "Phayao": 184252, "Phetchabun": 218063,
  "Phetchaburi": 138782, "Phichit": 201817, "Phitsanulok": 199561,
  "Phra Nakhon Si Ayutthaya": 199073, "Phrae": 188038, "Phuket": 199498,
  "Prachin Buri": 161050, "Prachuap Khiri Khan": 188786, "Ranong": 155028,
  "Ratchaburi": 217625, "Rayong": 269028, "Roi Et": 293244,
  "Sa Kaeo": 169673, "Sakon Nakhon": 246684, "Samut Prakan": 137015,
  "Samut Sakhon": 118060, "Samut Songkhram": 115680, "Saraburi": 203462,
  "Satun": 207773, "Si Sa Ket": 281430, "Sing Buri": 170810,
  "Songkhla": 253523, "Sukhothai": 248399, "Suphan Buri": 191020,
  "Surat Thani": 210855, "Surin": 248843, "Tak": 162027,
  "Trang": 188551, "Trat": 248163, "Ubon Ratchathani": 268498,
  "Udon Thani": 289031, "Uthai Thani": 226261, "Uttaradit": 268683,
  "Yala": 175213, "Yasothon": 314516
};

export const HOUSEHOLD_DEBT_RECORDS = {
  // --- CENTRAL (High leverage) ---
  "Bangkok":                   { debtToIncome: 14.2, stressIndex: 0.65, mobility: 0.80, debtPerHousehold: _NSO_DEBT["Bangkok"] || 88856 },
  "Samut Prakan":              { debtToIncome: 12.8, stressIndex: 0.58, mobility: 0.70, debtPerHousehold: _NSO_DEBT["Samut Prakan"] || 137015 },
  "Nonthaburi":                { debtToIncome: 13.5, stressIndex: 0.62, mobility: 0.75, debtPerHousehold: _NSO_DEBT["Nonthaburi"] || 113566 },
  "Pathum Thani":              { debtToIncome: 12.1, stressIndex: 0.55, mobility: 0.70, debtPerHousehold: _NSO_DEBT["Pathum Thani"] || 193100 },
  "Phra Nakhon Si Ayutthaya":  { debtToIncome: 11.8, stressIndex: 0.52, mobility: 0.65, debtPerHousehold: _NSO_DEBT["Phra Nakhon Si Ayutthaya"] || 199073 },
  "Saraburi":                  { debtToIncome: 10.5, stressIndex: 0.48, mobility: 0.60, debtPerHousehold: _NSO_DEBT["Saraburi"] || 203462 },
  "Nakhon Pathom":             { debtToIncome: 10.2, stressIndex: 0.46, mobility: 0.65, debtPerHousehold: _NSO_DEBT["Nakhon Pathom"] || 185534 },
  "Suphan Buri":               { debtToIncome: 11.0, stressIndex: 0.50, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Suphan Buri"] || 191020 },

  // --- EASTERN (Industrial Corridor) ---
  "Chon Buri":                 { debtToIncome: 11.2, stressIndex: 0.50, mobility: 0.85, debtPerHousehold: _NSO_DEBT["Chon Buri"] || 282402 },
  "Rayong":                    { debtToIncome: 9.8,  stressIndex: 0.42, mobility: 0.90, debtPerHousehold: _NSO_DEBT["Rayong"] || 269028 },
  "Chachoengsao":              { debtToIncome: 10.2, stressIndex: 0.45, mobility: 0.70, debtPerHousehold: _NSO_DEBT["Chachoengsao"] || 73913 },
  "Prachin Buri":              { debtToIncome: 9.5,  stressIndex: 0.43, mobility: 0.65, debtPerHousehold: _NSO_DEBT["Prachin Buri"] || 161050 },
  "Sa Kaeo":                   { debtToIncome: 10.8, stressIndex: 0.49, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Sa Kaeo"] || 169673 },

  // --- NORTHEASTERN (Agri-Stress Hubs) ---
  "Nakhon Ratchasima":         { debtToIncome: 15.4, stressIndex: 0.72, mobility: 0.40, debtPerHousehold: _NSO_DEBT["Nakhon Ratchasima"] || 322819 },
  "Khon Kaen":                 { debtToIncome: 14.8, stressIndex: 0.68, mobility: 0.45, debtPerHousehold: _NSO_DEBT["Khon Kaen"] || 280791 },
  "Si Sa Ket":                 { debtToIncome: 18.2, stressIndex: 0.85, mobility: 0.30, debtPerHousehold: _NSO_DEBT["Si Sa Ket"] || 281430 },
  "Surin":                     { debtToIncome: 17.5, stressIndex: 0.82, mobility: 0.35, debtPerHousehold: _NSO_DEBT["Surin"] || 248843 },
  "Buri Ram":                  { debtToIncome: 16.9, stressIndex: 0.78, mobility: 0.35, debtPerHousehold: _NSO_DEBT["Buri Ram"] || 216500 },
  "Udon Thani":                { debtToIncome: 15.1, stressIndex: 0.70, mobility: 0.40, debtPerHousehold: _NSO_DEBT["Udon Thani"] || 289031 },
  "Ubon Ratchathani":          { debtToIncome: 14.5, stressIndex: 0.66, mobility: 0.38, debtPerHousehold: _NSO_DEBT["Ubon Ratchathani"] || 268498 },
  "Roi Et":                    { debtToIncome: 15.8, stressIndex: 0.74, mobility: 0.35, debtPerHousehold: _NSO_DEBT["Roi Et"] || 293244 },
  "Maha Sarakham":             { debtToIncome: 15.2, stressIndex: 0.71, mobility: 0.38, debtPerHousehold: _NSO_DEBT["Maha Sarakham"] || 285706 },
  "Kalasin":                   { debtToIncome: 14.9, stressIndex: 0.69, mobility: 0.38, debtPerHousehold: _NSO_DEBT["Kalasin"] || 276654 },
  "Loei":                      { debtToIncome: 14.2, stressIndex: 0.65, mobility: 0.40, debtPerHousehold: _NSO_DEBT["Loei"] || 281620 },
  "Nakhon Phanom":             { debtToIncome: 13.8, stressIndex: 0.63, mobility: 0.38, debtPerHousehold: _NSO_DEBT["Nakhon Phanom"] || 247476 },
  "Sakon Nakhon":              { debtToIncome: 14.1, stressIndex: 0.64, mobility: 0.38, debtPerHousehold: _NSO_DEBT["Sakon Nakhon"] || 246684 },
  "Nong Khai":                 { debtToIncome: 13.5, stressIndex: 0.61, mobility: 0.40, debtPerHousehold: _NSO_DEBT["Nong Khai"] || 233625 },
  "Nong Bua Lam Phu":          { debtToIncome: 15.9, stressIndex: 0.75, mobility: 0.35, debtPerHousehold: _NSO_DEBT["Nong Bua Lam Phu"] || 310867 },
  "Yasothon":                  { debtToIncome: 16.2, stressIndex: 0.76, mobility: 0.33, debtPerHousehold: _NSO_DEBT["Yasothon"] || 314516 },
  "Amnat Charoen":             { debtToIncome: 17.1, stressIndex: 0.80, mobility: 0.32, debtPerHousehold: _NSO_DEBT["Amnat Charoen"] || 369739 },
  "Bueng Kan":                 { debtToIncome: 13.2, stressIndex: 0.60, mobility: 0.40, debtPerHousehold: _NSO_DEBT["Bueng Kan"] || 189021 },
  "Mukdahan":                  { debtToIncome: 13.5, stressIndex: 0.61, mobility: 0.40, debtPerHousehold: _NSO_DEBT["Mukdahan"] || 207694 },
  "Chaiyaphum":                { debtToIncome: 14.3, stressIndex: 0.65, mobility: 0.38, debtPerHousehold: _NSO_DEBT["Chaiyaphum"] || 234837 },

  // --- NORTHERN ---
  "Chiang Mai":                { debtToIncome: 12.5, stressIndex: 0.55, mobility: 0.60, debtPerHousehold: _NSO_DEBT["Chiang Mai"] || 215821 },
  "Chiang Rai":                { debtToIncome: 13.2, stressIndex: 0.58, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Chiang Rai"] || 193540 },
  "Lampang":                   { debtToIncome: 11.9, stressIndex: 0.52, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Lampang"] || 238044 },
  "Lamphun":                   { debtToIncome: 11.5, stressIndex: 0.50, mobility: 0.52, debtPerHousehold: _NSO_DEBT["Lamphun"] || 217019 },
  "Nan":                       { debtToIncome: 12.8, stressIndex: 0.57, mobility: 0.45, debtPerHousehold: _NSO_DEBT["Nan"] || 181434 },
  "Phayao":                    { debtToIncome: 12.1, stressIndex: 0.54, mobility: 0.48, debtPerHousehold: _NSO_DEBT["Phayao"] || 184252 },
  "Phrae":                     { debtToIncome: 11.8, stressIndex: 0.52, mobility: 0.48, debtPerHousehold: _NSO_DEBT["Phrae"] || 188038 },
  "Uttaradit":                 { debtToIncome: 12.3, stressIndex: 0.55, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Uttaradit"] || 268683 },
  "Mae Hong Son":              { debtToIncome: 10.2, stressIndex: 0.46, mobility: 0.42, debtPerHousehold: _NSO_DEBT["Mae Hong Son"] || 131705 },
  "Phitsanulok":               { debtToIncome: 11.2, stressIndex: 0.50, mobility: 0.52, debtPerHousehold: _NSO_DEBT["Phitsanulok"] || 199561 },
  "Sukhothai":                 { debtToIncome: 11.5, stressIndex: 0.51, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Sukhothai"] || 248399 },
  "Phetchabun":                { debtToIncome: 11.8, stressIndex: 0.52, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Phetchabun"] || 218063 },
  "Kamphaeng Phet":            { debtToIncome: 11.0, stressIndex: 0.49, mobility: 0.52, debtPerHousehold: _NSO_DEBT["Kamphaeng Phet"] || 247710 },
  "Phichit":                   { debtToIncome: 11.3, stressIndex: 0.50, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Phichit"] || 201817 },

  // --- WESTERN ---
  "Ratchaburi":                { debtToIncome: 10.8, stressIndex: 0.47, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Ratchaburi"] || 217625 },
  "Kanchanaburi":              { debtToIncome: 10.5, stressIndex: 0.46, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Kanchanaburi"] || 166875 },
  "Prachuap Khiri Khan":       { debtToIncome: 10.2, stressIndex: 0.45, mobility: 0.58, debtPerHousehold: _NSO_DEBT["Prachuap Khiri Khan"] || 188786 },
  "Phetchaburi":               { debtToIncome: 10.0, stressIndex: 0.44, mobility: 0.58, debtPerHousehold: _NSO_DEBT["Phetchaburi"] || 138782 },
  "Tak":                       { debtToIncome: 9.5,  stressIndex: 0.42, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Tak"] || 162027 },
  "Nakhon Sawan":              { debtToIncome: 11.0, stressIndex: 0.49, mobility: 0.52, debtPerHousehold: _NSO_DEBT["Nakhon Sawan"] || 198261 },
  "Uthai Thani":               { debtToIncome: 10.8, stressIndex: 0.48, mobility: 0.50, debtPerHousehold: _NSO_DEBT["Uthai Thani"] || 226261 },

  // --- SOUTHERN ---
  "Phuket":                    { debtToIncome: 10.8, stressIndex: 0.45, mobility: 0.75, debtPerHousehold: _NSO_DEBT["Phuket"] || 199498 },
  "Surat Thani":               { debtToIncome: 11.5, stressIndex: 0.48, mobility: 0.65, debtPerHousehold: _NSO_DEBT["Surat Thani"] || 210855 },
  "Songkhla":                  { debtToIncome: 12.2, stressIndex: 0.52, mobility: 0.60, debtPerHousehold: _NSO_DEBT["Songkhla"] || 253523 },
  "Nakhon Si Thammarat":       { debtToIncome: 11.8, stressIndex: 0.50, mobility: 0.58, debtPerHousehold: _NSO_DEBT["Nakhon Si Thammarat"] || 197765 },
  "Krabi":                     { debtToIncome: 10.5, stressIndex: 0.46, mobility: 0.62, debtPerHousehold: _NSO_DEBT["Krabi"] || 226547 },
  "Phang Nga":                 { debtToIncome: 10.2, stressIndex: 0.45, mobility: 0.60, debtPerHousehold: _NSO_DEBT["Phang Nga"] || 156498 },
  "Ranong":                    { debtToIncome: 9.8,  stressIndex: 0.43, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Ranong"] || 155028 },
  "Chumphon":                  { debtToIncome: 10.5, stressIndex: 0.46, mobility: 0.58, debtPerHousehold: _NSO_DEBT["Chumphon"] || 242083 },
  "Trang":                     { debtToIncome: 10.8, stressIndex: 0.47, mobility: 0.58, debtPerHousehold: _NSO_DEBT["Trang"] || 188551 },
  "Phatthalung":               { debtToIncome: 11.0, stressIndex: 0.48, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Phatthalung"] || 195011 },
  "Satun":                     { debtToIncome: 10.2, stressIndex: 0.45, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Satun"] || 207773 },
  "Pattani":                   { debtToIncome: 11.5, stressIndex: 0.52, mobility: 0.45, debtPerHousehold: _NSO_DEBT["Pattani"] || 167014 },
  "Yala":                      { debtToIncome: 11.2, stressIndex: 0.50, mobility: 0.45, debtPerHousehold: _NSO_DEBT["Yala"] || 175213 },
  "Narathiwat":                { debtToIncome: 11.0, stressIndex: 0.49, mobility: 0.42, debtPerHousehold: _NSO_DEBT["Narathiwat"] || 161015 },

  // --- OTHER CENTRAL ---
  "Ang Thong":                 { debtToIncome: 10.8, stressIndex: 0.48, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Ang Thong"] || 128630 },
  "Sing Buri":                 { debtToIncome: 10.5, stressIndex: 0.47, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Sing Buri"] || 170810 },
  "Chai Nat":                  { debtToIncome: 10.2, stressIndex: 0.46, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Chai Nat"] || 246575 },
  "Lop Buri":                  { debtToIncome: 10.5, stressIndex: 0.47, mobility: 0.55, debtPerHousehold: _NSO_DEBT["Lop Buri"] || 187476 },
  "Nakhon Nayok":              { debtToIncome: 9.8,  stressIndex: 0.44, mobility: 0.60, debtPerHousehold: _NSO_DEBT["Nakhon Nayok"] || 176869 },
  "Chanthaburi":               { debtToIncome: 10.5, stressIndex: 0.46, mobility: 0.60, debtPerHousehold: _NSO_DEBT["Chanthaburi"] || 191578 },
  "Trat":                      { debtToIncome: 10.2, stressIndex: 0.45, mobility: 0.58, debtPerHousehold: _NSO_DEBT["Trat"] || 248163 },
  "Samut Sakhon":              { debtToIncome: 11.5, stressIndex: 0.51, mobility: 0.68, debtPerHousehold: _NSO_DEBT["Samut Sakhon"] || 118060 },
  "Samut Songkhram":           { debtToIncome: 10.8, stressIndex: 0.48, mobility: 0.60, debtPerHousehold: _NSO_DEBT["Samut Songkhram"] || 115680 },
};

export const DEBT_META = {
  "source": "BOT Q4/2024 (debtToIncome, stressIndex) + NSO SES 2566 (debtPerHousehold)",
  "metric": "Debt-to-Annual-Income Multiplier + NSO SES Household Debt (THB)",
  "provinces": 77,
  "updated_at": "2026-04-05"
};
