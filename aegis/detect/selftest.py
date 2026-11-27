"""Self-test for detect on made-up text that does NOT come from the practice data.

    python -m aegis.detect.selftest

The practice score cannot show whether we generalise, because the rules were written while
looking at practice data. Add a case here whenever you find a miss or a false alarm.
All names and numbers are invented. main.py never imports this file.
"""
from __future__ import annotations

import sys

from aegis.detect import detect_file

_BS = chr(92)

# (line, strings that MUST be found, strings that MUST survive)
CASES = [
    # medical and staff text that only looks like a name
    ("Paracetamol ko continue karein.", [], ["Paracetamol"]),
    ("Metformin ka dose badha diya.", [], ["Metformin"]),
    ("Insulin ki zarurat hai.", [], ["Insulin"]),
    ("Amlodipine ke saath Telmisartan lena hai.", [], ["Amlodipine", "Telmisartan"]),
    ("Dengue ne bahut kamzor kar diya.", [], ["Dengue"]),
    ("Echo ka report pending hai.", [], ["Echo"]),
    ("City Diagnostics 9876543210", ["9876543210"], ["City Diagnostics"]),
    ("Apollo Pharmacy Counter ph 9876511111", ["9876511111"], ["Apollo Pharmacy Counter"]),
    ("C/O Chest Pain since 2 days", [], ["Chest Pain"]),
    ("K/C/O DM2 x 9 yrs, HTN on treatment.", [], ["DM2", "HTN", "9 yrs"]),
    ("Cushing's syndrome and Graves disease.", [], ["Cushing", "Graves"]),
    ("Dr. Anil Mehta ji ne dekha.", [], ["Anil Mehta"]),
    ("ASHA didi ne visit kiya.", [], ["ASHA"]),
    ("Patient Education given about diet.", [], ["Education"]),
    ("BP 112/78, Tab Meclizine 25 mg 1-0-1 x 5 days", [], ["112/78", "25 mg", "1-0-1", "5 days"]),
    ("Platelet Count 150000-410000 /uL", [], ["150000-410000"]),
    # personal data in wording the practice files do not use
    ("Name of the Patient - Lakshmi Iyer", ["Lakshmi Iyer"], []),
    ("Her husband Venkat informed us.", ["Venkat"], []),
    ("Spoke to Mr Ramakrishnan, reachable on 098450 33221.", ["Ramakrishnan", "098450 33221"], []),
    ("Discussed with daughter Priya on phone.", ["Priya"], []),
    ("Lakshmi ko kal se chakkar aa raha hai.", ["Lakshmi"], ["chakkar"]),
    ("Dinesh ka BP 120/80 hai.", ["Dinesh"], ["120/80"]),
    ("Hosp. No.: KGH/0042917", ["0042917"], []),
    ("रोगी का नाम - लक्ष्मी अय्यर, निवासी ग्राम बेलापुर, मो. ९८४५०११२२३",
     ["लक्ष्मी अय्यर", "बेलापुर", "९८४५०११२२३"], []),
    ("Address: Qtr 17/B, Shastri Colony, beside Water Tank, Belapur",
     ["Qtr 17/B", "Shastri Colony", "beside Water Tank", "Belapur"], []),
    # found by cheap-model stress cases: labels in the middle of a line, unfamiliar ID formats and relative words
    ("Rec# : HOSP/2023/07/00123, Diagnosis: Hypertension.", ["HOSP/2023/07/00123"], ["Hypertension"]),
    ("Seen today; C.R. No. 55/24; BP 118/76 mmHg", ["55/24"], ["118/76"]),
    ("Pt ID: #A1B2C3, Rx: Lisinopril 10mg", ["A1B2C3"], ["Lisinopril 10mg"]),
    ("Aadhaar No: 1111-2222-3333, prescribed Levothyroxine 50 mcg.", ["1111-2222-3333"], ["Levothyroxine"]),
    ("PAN QWXDE7391K on file", ["QWXDE7391K"], []),
    ("Informant (H: 98.50.44.2211); ferritin 9 ng/mL", ["98.50.44.2211"], ["ferritin 9"]),
    ("guardian: maternal uncle Prakash Jha; Azithromycin 250 mg OD", ["Prakash Jha"], ["Azithromycin"]),
    ("attendant - bua (paternal aunt) Kamlesh; bill INR 4200", ["Kamlesh"], ["INR 4200"]),
    ("insured Rahul Deshmukh; fasting glucose 102 mg/dL", ["Rahul Deshmukh"], ["102 mg/dL"]),
    ("c/o- 14, Nehru Marg, Model Town, Karnal; SpO2 98% on room air", ["Nehru Marg", "Model Town"], ["SpO2 98%"]),
    ("Near: Lotus Temple, Diagnosis: Migraine.", ["Lotus Temple"], ["Migraine"]),
    ("श्रीमती अंजलि वर्मा को 10mg दवा दी गई।", ["अंजलि वर्मा"], ["10mg"]),
    ("Village: Rampur, Diagnosis: Malaria, WBC 12,000", ["Rampur"], ["Malaria", "WBC 12,000"]),
    # round 2: names with no label, address chains, more ID shapes (all invented)
    ("Discharged Gurleen Kaur Sandhu in stable condition on Tab. Metformin.", ["Gurleen Kaur Sandhu"], ["Metformin"]),
    ("Handover: bed 4 given to Pallavi Hegde, afebrile overnight.", ["Pallavi Hegde"], ["afebrile"]),
    ("History taken from Tshering Wangdi, 61 yrs, via phone.", ["Tshering Wangdi"], []),
    ("आज सुबह गोविंद नारायण शुक्ला को भर्ती किया गया।", ["गोविंद नारायण शुक्ला"], ["भर्ती"]),
    ("Harbans Lal ki patni Kiran Bala dawa lene aayi.", ["Harbans Lal", "Kiran Bala"], ["dawa"]),
    ("F/o Ishani Ghosh signed the consent form.", ["Ishani Ghosh"], ["consent form"]),
    ("Flat 14, Teynampet, 600018; Tab. Dapsone 100mg", ["Flat 14", "Teynampet", "600018"], ["Dapsone 100mg"]),
    ("Seen at home, Kothapet, 522001. Gopal Naidu was resting.", ["Kothapet", "522001", "Gopal Naidu"], []),
    ("Ref MRN-GWL-55210-C and IPD#25/66120 today", ["MRN-GWL-55210-C", "IPD#25/66120"], []),
    ("MRN IPD-2025-061 reviewed", ["IPD-2025-061"], ["reviewed"]),
    ("Mob 97 31 20 45 88, Door No. 12-3-45, Opp. Water Tanki", ["97 31 20 45 88", "12-3-45", "Opp. Water Tanki"], []),
    ("Claim ref NIVA-POL-7731204 approved", ["NIVA-POL-7731204"], ["approved"]),
    # round 2 traps: places, staff and report text that hold surname-like or capitalised words
    ("Referred to Ram Manohar Lohia Hospital for further care.", [], ["Ram Manohar Lohia"]),
    ("Treated at Sharma Nursing Home, report from Gupta Diagnostics.", [], ["Sharma", "Gupta"]),
    ("Seen by Nurse Mary Thomas and Sister Anita Nair.", [], ["Mary Thomas", "Anita Nair"]),
    ("पाटलिपुत्र केयर अस्पताल में जांच हुई।", [], ["केयर"]),
    ("Platelet Count, 150000, WBC, 11000, normal.", [], ["150000", "11000"]),
    ("Total bill, 148500, paid in cash.", [], ["148500"]),
    ("Review at Village Health Nutrition Day camp.", [], ["Health Nutrition"]),
    ("रात को नींद की दवा दी गई।", [], ["रात"]),
    # round 3: whole stretches of medical text must not disappear with a nearby ID or address label
    ("PAN QWXPE4412L: BP 122/80 mmHg, Amoxyclav 625mg 1-0-1.", ["QWXPE4412L"], ["BP 122/80", "Amoxyclav 625mg", "1-0-1"]),
    ("मरीज (पता: शिवाजी पेठ, 411030) को डॉ. नीलम राव ने एस्प्रिन 75mg 0-1-0 दी, कुल खर्च रु. 6,100 रहा।",
     ["शिवाजी पेठ", "411030"], ["एस्प्रिन 75mg", "0-1-0", "रु. 6,100"]),
    ("आशा दीदी रजनी के साथ आई।", [], ["आशा"]),
    ("Seen at Sardar Patel PHC today.", [], ["Sardar Patel"]),
    ("Platelets, 245100 and WBC, 118200 today.", [], ["245100", "118200"]),
    # round 3: more shapes
    ("Joseph D'Mello D/o Peter D'Mello admitted.", ["Joseph D'Mello", "Peter D'Mello"], []),
    ("Ref IP#NICU-25-771 and NGP/CHW/25/40021", ["NICU-25-771", "NGP/CHW/25/40021"], []),
    ("यूएचआईडी KDR/7714 दर्ज", ["KDR/7714"], []),
    ("Claim TPA-MEDI-771204 under PMJAY-MH-25-884210", ["TPA-MEDI-771204", "PMJAY-MH-25-884210"], []),
    ("Collected from Shastri Ward area, Nehru Nagar, 440012 yesterday.", ["Nehru Nagar", "440012"], []),
    ("सुखदेव उइके को भर्ती किया।", ["सुखदेव उइके"], []),
    # lowercase PAN, more phone layouts, key=value logs, lowercase names
    ("billing: pan mkrpd4821q noted, Tab. Cefixime 200 mg", ["mkrpd4821q"], ["Cefixime 200 mg"]),
    ("Reach on (912) 455-7781 or 934/221/6650; SpO2 97%", ["(912) 455-7781", "934/221/6650"], ["SpO2 97%"]),
    ("Landline 0512-2345678, alt (0581) 456789 and 022 2567 8901.",
     ["0512-2345678", "(0581) 456789", "022 2567 8901"], []),
    ("Ward office 0591-245566 open till 5; lot 0042-118, batch 0007-123456789",
     ["0591-245566"], ["0042-118", "0007-123456789"]),
    ("BP 130/80/72, counts 150/900/1100, ref range 4000-11000, dose 0.5-1.0 mg", [], ["130/80/72", "4000-11000", "0.5-1.0"]),
    ("caller=devika ranganathan dial=912/450/7781", ["devika ranganathan", "912/450/7781"], []),
    ("caller=Barnali Thengal status=resolved", ["Barnali Thengal"], ["resolved"]),
    ("patient=stable name=unknown pt=afebrile", [], ["stable", "unknown", "afebrile"]),
    ("pt devika ranganathan ko do din se bukhar hai", ["devika ranganathan"], ["bukhar"]),
    ("mahesh tripathi s/o ramnaresh tripathi admitted kal raat", ["mahesh tripathi", "ramnaresh tripathi"], ["admitted"]),
    ("pichle das din se pet dard, lal chakte, x ray normal, khan pan theek", [],
     ["das din", "pet dard", "lal chakte", "x ray normal", "khan pan"]),
    ("patient has chest pain and mild fever, advised rest at home", [], ["chest pain", "mild fever", "rest at home"]),
    # lowercase "h.no"; "q4h no 2" is a dose schedule, not a house
    ("Lives at h.no 58/C, since 2019.", ["h.no 58/C"], []),
    ("Old record says hno. 212 only.", ["hno. 212"], []),
    ("Syrup q4h no 2 more doses today.", [], ["q4h no 2"]),
    # "r/o" also means "rule out": a disease after it is not a village
    ("Tremor, r/o Parkinson's disease, advise MRI.", [], ["Parkinson"]),
    ("Fever 3 days, r/o Dengue.", [], ["Dengue"]),
    ("Chest pain, r/o MI.", [], ["MI"]),
    ("Persistent cough, R/O TB.", [], ["TB"]),
    ("Weakness, r/o Guillain Barre syndrome.", [], ["Guillain"]),
    ("RLQ pain, r/o Appendicitis.", [], ["Appendicitis"]),
    ("65 yr male R/o Barhalganj, seen in OPD.", ["Barhalganj"], []),
    ("Pt r/o Sikandarpur fever since 3 days.", ["Sikandarpur"], []),
    # a real village must still go, whatever follows it or however its name ends
    ("R/o Barhalganj Patient stable today.", ["Barhalganj"], []),
    ("Woman r/o Sikandarpur heart disease on treatment.", ["Sikandarpur"], []),
    ("Man r/o Phuluria for ten years.", ["Phuluria"], []),
    # dotted and "+91/" phones, mixed Aadhaar separators
    ("Call 97.31.20.45.88 or +91/8123/004455; Na 138.5", ["97.31.20.45.88", "+91/8123/004455"], ["138.5"]),
    ("ID seen 5821-7734 9012 at desk, HbA1c 7.2", ["5821-7734 9012"], ["HbA1c 7.2"]),
    ("Card 8831.0057.2294 on file; build 2024.0115.1030, HbA1c 7.2, Hb 11.4.2", ["8831.0057.2294"], ["2024.0115.1030", "HbA1c 7.2"]),
    # zero-width characters, look-alike letters, accents (typed whole or as separate marks)
    ("Patient: Bar\u200bnali Then\u200dgal, mob 97312\u200b04588", ["Bar\u200bnali Then\u200dgal", "97312\u200b04588"], []),
    ("Patient: B\u0430rn\u0430li Thengal (44/F)", ["B\u0430rn\u0430li Thengal"], []),
    ("Patient Name: H\u00e9ctor Pereira", ["H\u00e9ctor Pereira"], []),
    ("Patient Name: He\u0301ctor Pereira", ["He\u0301ctor Pereira"], []),
    ("TSH 2.1 \u03bcIU/mL, dose 50 \u00b5g, TNF-\u03b1 raised", [], ["\u03bcIU/mL", "50 \u00b5g", "TNF-\u03b1"]),
    # years from 1800: the date is found and shifted; a 4-digit time of day is not a year
    ("DOB 14/03/1893, seen 02 Feb 1895", ["14/03/1893", "02 Feb 1895"], []),
    ("Born 1889-07-21; registered 1889/07/22", ["1889-07-21", "1889/07/22"], []),
    ("Admitted 12 Mar 1830 hrs with BP 120/80, Tab Aspirin 75 mg 0-1-0", [], ["1830 hrs", "BP 120/80", "Aspirin 75 mg"]),
    # URL escapes: found where they stand in the original text, and the words between them are not read as a name
    ("Scan: https://his.example/files/Tarun%20Wadhwa%5Creport.pdf?tel=%2B91%2098765%2043210",
     ["Tarun%20Wadhwa", "%2B91%2098765%2043210"], ["report.pdf"]),
    ("file:///D%3A%5CRecords%5CKavya_Chaudhary%5Ccase_notes.pdf", ["Kavya_Chaudhary"], ["case_notes"]),
    ("Open summary_Zubin_Pathak_2026.pdf and Lab_Reports_Singh_Block.csv", ["Zubin_Pathak"], ["Lab_Reports", "Singh_Block"]),
    ("view?patient=Agust%C3%ADn%20Fonseca&visit=3", ["Agust%C3%ADn%20Fonseca"], ["visit=3"]),
    ("log: patient=Zorawar Khetarpal ward=3 status=stable", ["Zorawar Khetarpal"], ["ward=3", "status=stable"]),
    ("SpO2 96%, 5%DEXTROSE drip at 40%20 ml/hr, Tab Paracetamol 650 mg", [], ["96%", "5%DEXTROSE", "Paracetamol 650 mg"]),
    ("Keep 100%25 oxygen; Hb 9.8 g/dL", [], ["Hb 9.8 g/dL"]),
    # given names with no surname: only where the sentence says the person did something ("signed the", "took discharge")
    ("Meenal signed the surgical consent form.", ["Meenal"], ["consent form"]),
    ("Tarun took discharge against medical advice on 14/08/2026.", ["Tarun"], ["medical advice"]),
    ("Consent signed by guardian. Nurse signed the form. Uncle signed the consent. Dr. Rao signed the order.", [],
     ["Consent", "Nurse", "Uncle", "guardian"]),
    ("Wheezing returned after 2 days. Itching signed off by physician. Pharmacy signed the bill.", [],
     ["Wheezing", "Itching", "Pharmacy"]),
    # Scrubadub-inspired improvements + English/Hindi/Hinglish translations
    ("Contact ramesh.verma at gmail dot com or ph 98.45.01.12.23; BP 118/76.",
     ["ramesh.verma at gmail dot com", "98.45.01.12.23"], ["118/76"]),
    ("Patient: Ra\u200bhul\u200d Chatur\u200bvedi, Mob: 73053\u200b31651, Co-admitted: Dеvikа Rаo.",
     ["Ra\u200bhul\u200d Chatur\u200bvedi", "73053\u200b31651", "Dеvikа Rаo"], []),
    ("URL ref: https://portal.example/view?patient=Priyanka%20Sengupta&tel=%2B91%207759130735",
     ["Priyanka%20Sengupta", "%2B91%207759130735"], []),
    # escapes written out as text: "\uXXXX" sequences and HTML entities (the whole escaped name is the finding)
    (f"Attendant: {_BS}u0053unita Mishra, tel {_BS}u0039811100041, Tab Telmisartan 40 mg OD.",
     [f"{_BS}u0053unita Mishra", f"{_BS}u0039811100041"], ["Telmisartan 40 mg"]),
    ("Attendant: &#83;unita Mishra &amp; son, BP 142/90 &amp; HR 78, Tab Amlodipine 5 mg &lt; 6 weeks.",
     ["&#83;unita Mishra"], ["142/90", "Amlodipine 5 mg"]),
    ("attendant " + "".join(f"{_BS}u{ord(c):04x}" if ord(c) > 127 else c for c in "लता बैरवा आयी"),
     ["".join(f"{_BS}u{ord(c):04x}" for c in "लता")], []),
    ("Drip 5%DEXTROSE at 40%20 ml/hr, folder C:" + _BS + "users" + _BS + "x, e.g. R&D; team.", [], ["5%DEXTROSE", "users", "R&D;"]),
    # a cue word in an English line followed by a name written in Devanagari; Hindi function words are not names
    ("attendant लता बैरवा came with her", ["लता बैरवा"], []),
    ("wife के साथ आये, father को sugar है", [], ["के साथ"]),
    ("Satyendra discharged in stable condition on Tab Azithromycin 500 mg.",
     ["Satyendra"], ["Azithromycin 500 mg"]),
    ("Priyanka ne sign kiya aur Rohan ko chhutti mili; BP 120/80.",
     ["Priyanka", "Rohan"], ["120/80"]),
    ("रमेश ने हस्ताक्षर किए और प्रिया को छुट्टी दी गई; पैरासिटामोल 500mg जारी।",
     ["रमेश", "प्रिया"], ["पैरासिटामोल 500mg"]),
    ("Follow up with Pema Choden and Agustín Fonseca; PAN gxlpv2692s.",
     ["Pema Choden", "Agustín Fonseca", "gxlpv2692s"], []),
    # the same new rules must leave report and ward text alone
    ("Culture verified, Repeat CBC signed.", [], ["Culture", "Repeat CBC"]),
    ("Troponin, Negative called to physician.", [], ["Negative"]),
    ("Seen at 10 at AIIMS dot in OPD.", [], ["AIIMS"]),
    ("Lobsang verified the payment receipt at the counter.", ["Lobsang"], []),
    ("Culture verified the organism; Smear signed out by pathologist.", [], ["Culture", "Smear"]),
    ("Janam tithi 14/05/1988, जन्मतिथि 12-08-1992.", ["14/05/1988", "12-08-1992"], []),
    # Kumari and Devi after a first name are part of the name, not a title
    ("Patient: Km. Barsha Kumari came with cough.", ["Barsha Kumari"], ["cough"]),
    # doctor titles in capitals or with a courtesy title in brackets
    ("Chemo plan by DR.(MRS) TARULATA MAHANTA today.", [], ["TARULATA MAHANTA"]),
    # relation words and separators
    ("Consent taken. Son = Nandlal. Will pay tomorrow.", ["Nandlal"], ["Consent"]),
    ("elder bro Ompal waiting outside, will sign.", ["Ompal"], ["waiting"]),
    ("sibling Kiruba also screened, report normal.", ["Kiruba"], ["screened"]),
    ("Call bahu Jasleen if he wanders at night.", ["Jasleen"], ["night"]),
    ("dtr Rituparna will collect the reports.", ["Rituparna"], ["reports"]),
    ("Family history: sibling Diabetes since 2019.", [], ["Diabetes"]),
    # record and insurance numbers announced by a label
    ("UHID-->QRS/OP/0045127 || BP 130/84", ["QRS/OP/0045127"], ["130/84"]),
    ("Old file MR# 31-207-5568 traced.", ["31-207-5568"], ["traced"]),
    ("TPA card no. ZXC7-00518837-04 pending, bill Rs 12,500", ["ZXC7-00518837-04"], ["12,500"]),
    ("आयुष्मान कार्ड संख्या RJ-QX-66120934 दर्ज, खुराक 500mg", ["RJ-QX-66120934"], ["500mg"]),
    ("TPA card not available, HbA1c 8.1% noted.", [], ["HbA1c 8.1%", "not available"]),
    # birth dates written with a Hindi or roman-numeral month
    ("जन्मतिथि ३ फ़रवरी १९७९, वज़न 62 kg", ["३ फ़रवरी १९७९"], ["62 kg"]),
    ("DOB 21/XI/1958, on Telmisartan.", ["21/XI/1958"], ["Telmisartan"]),
    ("Stage II/IV disease, grade III/2020 criteria.", [], ["II/IV", "III/2020"]),
    # "Name- value" with a dash and no space before it
    ("पंजीकरण काउंटर; नाम- सुमित्रा महंत", ["सुमित्रा महंत"], ["काउंटर"]),
    ("Follow- up after two weeks.", [], ["up after two weeks"]),
    # HL7 style names, and HL7 doctors and test names that look similar
    ("PID Mahanta^Tarulata admitted to HDU.", ["Mahanta^Tarulata"], ["HDU"]),
    ("Attending Dr^Rathi^Ompal on call.", [], ["Rathi", "Ompal"]),
    ("OBX Glucose^Fasting 102 mg/dL", [], ["Glucose^Fasting"]),
    # "near old <place>"
    ("Lives near old Hanuman Temple, on Amlodipine.", ["near old Hanuman Temple"], ["Amlodipine"]),

    # a tight dash only introduces a value after a label that says "name"
    ("Patient- stable today, BP 120/80.", [], ["stable"]),
    ("मरीज- को बुखार है, खुराक 500mg", [], ["बुखार"]),
    # doctor protection must never spread over the patient who follows, whatever the capitals
    ("REF DR RATHI PATIENT SUMITRA MAHANTA ADMITTED", ["SUMITRA MAHANTA"], []),
    ("SEEN BY DR RATHI PT NAME NANDLAL HAZARIKA", ["NANDLAL HAZARIKA"], []),
    ("Ref DR RATHI Mrs Barsha Hazarika came", ["Barsha Hazarika"], []),
    ("ref dr Rathi Patient Sumitra Mahanta admitted", ["Sumitra Mahanta"], []),
    ("UNDER DR RATHI MR OMPAL MAHANTA BP 120/80", ["OMPAL MAHANTA"], ["120/80"]),
    ("Ref Dr Rathi Patient Sumitra Mahanta admitted", ["Sumitra Mahanta"], []),
    ("DR.(MRS) MAHANTA PATIENT NANDLAL HAZARIKA", ["NANDLAL HAZARIKA"], []),
    # a dash after a name label never takes over from a later colon
    ("Patient Name- verified: Barsha Hazarika", ["Barsha Hazarika"], []),
    # a leading word that is not a name must not take the name after it down with it
    ("Witness Barsha Hazarika tel 9412730518", ["Barsha Hazarika", "9412730518"], []),
    ("Admitted Ompal (father: Nandlal Mahanta) of H.No. 9, 781014", ["Ompal", "Nandlal Mahanta"], []),
    # Hindi honorifics and relation words before a name; the name ends at a comma, particle, verb, number or medical word
    ("श्रीमान गिरधारी लोहनी, उम्र 61, को मधुमेह है। इंसुलिन 12 यूनिट।", ["गिरधारी लोहनी"], ["मधुमेह", "इंसुलिन 12 यूनिट"]),
    ("सुश्री कलावती फॉलो-अप के लिए आईं। रक्त शर्करा 190 mg/dl।", ["कलावती"], ["फॉलो", "190 mg/dl"]),
    ("स्व. श्री हरकिशन टम्टा की पुत्री मीनाक्षी भर्ती हैं। बुखार 101 F।", ["हरकिशन टम्टा", "मीनाक्षी"], ["बुखार", "101 F"]),
    ("साथ में भतीजा तेजपाल चंदोला आए और दवा की पर्ची दी। डॉ. रस्तोगी ने देखा।", ["तेजपाल चंदोला"], ["दवा", "रस्तोगी"]),
    ("पत्नी सुमित्रा ने बताया कि सांस फूल रही है।", ["सुमित्रा"], ["सांस"]),
    ("मरीज़ का दामाद योगेश, निवासी भानपुर, कल सुबह आया। फ़ॉलो-अप 2 हफ्ते बाद।", ["योगेश", "भानपुर"], ["2 हफ्ते"]),
    ("कल रात धनौरा से लाए गए, रक्तचाप 150/95 है।", ["धनौरा"], ["रक्तचाप", "150/95"]),
    ("बहन तारा, निवासी: कुम्हारपुर, साथ थीं।", ["तारा", "कुम्हारपुर"], []),
    # a relation word that is followed by a medical word, a particle or a doctor is not a name
    ("पति को बुखार है और बेटे का BP 150/90 है।", [], ["पति", "बेटे", "BP 150/90"]),
    ("माता जी को मधुमेह है। भाई साहब को सांस की तकलीफ है।", [], ["माता", "भाई", "मधुमेह"]),
    ("पत्नी डॉ. अवस्थी से मिलने आईं। बेटी को खांसी है।", [], ["पत्नी", "बेटी", "अवस्थी", "खांसी"]),
    ("भर्ती रोगी: सावित्री चौरसिया\nपुत्र: नवल चौरसिया\nउम्र: 31 वर्ष   लिंग: महिला\nनिदान: मधुमेह",
     ["सावित्री चौरसिया", "नवल चौरसिया"], ["उम्र", "लिंग", "निदान", "मधुमेह", "महिला"]),
    ("पिता का नाम: जगदीश मौर्य\nउम्र: 63 वर्ष\nपति: हरिप्रसाद\nबीमारी: उच्च रक्तचाप\nश्रीमती उर्मिला\nइलाज: जारी",
     ["जगदीश मौर्य", "हरिप्रसाद", "उर्मिला"], ["उम्र", "बीमारी", "रक्तचाप", "इलाज", "पिता का नाम"]),
    ("पिता रोज़ सुबह इंसुलिन लेते हैं। घर से लेकर आए, अस्पताल से लाए गए।", [], ["पिता", "इंसुलिन", "घर", "अस्पताल"]),
    # Hinglish relation words before a name, a locality after "Ghar", a landmark cue, a name in brackets (invented)
    ("Bete Vinod Kharwar ne dawa nahi li. Tab. Telmisartan 40 mg 1-0-0.", ["Vinod Kharwar"], ["Telmisartan 40 mg", "1-0-0", "Bete"]),
    ("Patni Savita Munda ko sugar hai, bhatija Deepak Toppo saath aaya, SpO2 95%.",
     ["Savita Munda", "Deepak Toppo"], ["sugar", "SpO2 95%", "Patni", "bhatija"]),
    ("Saas Kamla Oram aur damaad Pritam Lakra mile. Dr. Neelam Bakshi ne dekha.", ["Kamla Oram", "Pritam Lakra"], ["Neelam Bakshi", "Saas"]),
    ("Ghar Shanti Colony mein hai, landmark Blue Gate School. BP 124/82 mmHg.",
     ["Shanti Colony", "Blue Gate School"], ["BP 124/82 mmHg", "Ghar"]),
    ("Makaan Ambedkar Vihar mein hai. Subhash Nagar ke paas. Syp. Cetirizine 5 mg HS.",
     ["Ambedkar Vihar", "Subhash Nagar"], ["Cetirizine 5 mg", "ke paas"]),
    ("Mareez Girish ji (Girish Lakda) ko Pantop 40 mg di gayi, Metformin 500 mg 1-0-1.",
     ["Lakda"], ["Pantop 40 mg", "Metformin 500 mg", "1-0-1"]),
    ("Sunita Minz ne raat ko dawa nahi li; Metformin 500 mg 1-0-1.", ["Sunita Minz"], ["Metformin 500 mg", "dawa nahi li"]),
    # ... and what is NOT a name: relation word + particle or medical word, drugs, "Beta Blocker", doctors
    ("Beta ko bukhar nahi hai. Pati ko TB hai. Bhai ka BP 150/90. Bete ne dawa li.", [], ["Beta", "Pati", "Bhai", "Bete", "150/90", "bukhar"]),
    ("Beta Blocker (Metoprolol 25 mg) shuru kiya. Beta Thalassemia trait.", [], ["Beta Blocker", "Metoprolol 25 mg", "Beta Thalassemia"]),
    ("Dengue ne aaj bahut kamzor kar diya, platelet 90000. Dr. Rekha Soren ke paas refer.", [], ["Dengue", "platelet 90000", "Rekha Soren"]),
    ("Bhai Sahab ne dawa li. Pita Ji ka BP 140/90 hai. Ghar Hospital mein hai.", [], ["Bhai", "Pita", "140/90", "Hospital"]),
    ("Patni Savita Devi (MD Pathology) ka report aaya, Hb 10.2 g/dl.", ["Savita Devi"], ["Pathology", "Hb 10.2 g/dl"]),
    # mail subject lines: the title is a topic, not the patient's name; the name in it and a short record number go
    ("From: desk4@clinic.example\nSubject: Referral - Chandni Mamgain (IPD 6204)\n\nSodium 131 mmol/L. "
     "Referral accepted; Mamgain to attend Monday.", ["Chandni Mamgain", "6204"],
     ["Referral", "Sodium 131", "accepted"]),
    ("Subject: Discharge summary - Tilak Rawolia, 52/M", ["Tilak Rawolia"], ["Discharge summary"]),
    ("Re: Fwd: Transfer of Smt. Basanti Koranga", ["Basanti Koranga"], ["Transfer"]),
    ("Re: Referral Ruchira Mamgain (UHID No. 7719)", ["Ruchira Mamgain", "7719"], ["Referral"]),
    ("Subject: रेफरल - भुवनेश्वरी कोरंगा (IPD 3381)", ["भुवनेश्वरी कोरंगा", "3381"], ["रेफरल"]),
    # what "Subject:" as a patient label used to remove is still removed, without the document words around it
    ("Subject: Tilak Rawolia", ["Tilak Rawolia"], []),
    ("Subject: Referral for Chandni Mamgain", ["Chandni Mamgain"], ["Referral"]),
    ("Subject: Discharge Summary Tilak Rawolia", ["Tilak Rawolia"], ["Discharge Summary"]),
    # subject lines with no person in them keep all their words, and a year is not a record number
    ("Subject: Referral Letter\nPlease see the referral note.", [], ["Referral Letter", "referral note"]),
    ("Subject: Lab Report - Liver Function", [], ["Lab Report", "Liver Function"]),
    ("Subject: Referral - Knee Replacement", [], ["Referral", "Knee Replacement"]),
    ("Re: Wound Dehiscence", [], ["Wound Dehiscence"]),
    ("Subject: Appointment Reminder\nSub: Fire Safety Drill", [], ["Appointment Reminder", "Fire Safety Drill"]),
    ("Subject: Referral - CKD Stage 4, IP 2024 audit", [], ["CKD Stage 4", "2024"]),
]


def _run_line(line: str) -> list[str]:
    record = {"record_id": "t.txt#doc", "file": "t.txt", "loc": "doc", "fmt": "text",
              "fields": [{"path": "text", "kind": "text", "context": None, "value": line}]}
    return [f["text"] for f in detect_file([record])[0]["findings"]
            if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]


# whole-column cases: (headers, rows, header -> expected finding type for every row, or None = nothing flagged)
TABLES = [
    # recent years under an unreadable header are events, not birth years
    (["Q_YR"], [["2009"], ["2014"], ["2021"], ["2024"]], {"Q_YR": None}),
    # "Surname, Given" in an unreadable column, a birth-year column, Hindi-in-Latin headers
    (["PX_LBL", "X_YOB", "CLIN_TXT"], [["Thengal, Barnali", "1968", "stable"], ["Pereira, Hector", "1981", "afebrile"],
                                       ["Oraon, Suraj", "2003", "review"]],
     {"PX_LBL": "PATIENT_NAME", "X_YOB": "DOB", "CLIN_TXT": None}),
    (["rogee", "pehchaan_sankhya", "postal6", "nidan"], [["Barnali Thengal", "1234 5678 9012", "781001", "Anemia"]],
     {"rogee": "PATIENT_NAME", "pehchaan_sankhya": "AADHAAR", "postal6": "PIN", "nidan": None}),
    (["P_NOM", "K_SUP", "M_RXR", "Q_LOC", "Z_6D", "N_MEMO"],
     [["Anirban Sen", "Mitali Sen", "Farhan Qureshi", "21A Lake Road, Near City Park", "700029", "seen by Dr. Farhan Qureshi"],
      ["Lalita Oraon", "Birsu Oraon", "Neha Kapoor", "H.No. 4, Station Road, Ranchi", "834001", "Dr. Neha Kapoor advised rest"],
      ["Joseph Kurien", "Anna Kurien", "Farhan Qureshi", "Flat 9, Gandhi Nagar, Near Bus Stand", "682020", "stable"]],
     {"P_NOM": "PATIENT_NAME", "K_SUP": "RELATIVE_NAME", "M_RXR": None, "Q_LOC": "HOUSE", "Z_6D": "PIN"}),
    # one patient shares a doctor's name: the column is still the patients
    (["P_NOM", "MEMO"], [["Amit Sharma", "stable"], ["Renu Bhagat", "stable"], ["Suraj Oraon", "stable"],
                         ["Lalita Nair", "seen by Dr. Amit Sharma"]], {"P_NOM": "PATIENT_NAME"}),
    (["fullName", "familyHeadRelation", "orderingClinician", "labRchId", "Village/Mohalla"],
     [["Renu Bhagat", "Father Suraj Bhagat", "Gautam Pillai", "RCH-JH-25-11902", "Rampur Kalan"]],
     {"familyHeadRelation": "RELATIVE_NAME", "orderingClinician": None, "labRchId": "MRN", "Village/Mohalla": "VILLAGE"}),
    (["पता_ग्राम_पिन", "वार्ड"], [["मकान नं. 5/ए, ग्राम रामपुर, 263139", "कस्तूरबा वार्ड"]],
     {"पता_ग्राम_पिन": "HOUSE", "वार्ड": None}),
    # "ref" does not mean doctor; real referrer and reference-range columns are still kept
    (["case_sheet_ref", "patient_ref", "mrn_ref", "ref_by", "ref_doctor", "ref_range", "dak_code", "sample_code"],
     [["31145549", "31147001", "31149002", "Neha Kapoor", "Farhan Qureshi", "4000-11000", "226010", "880123"]],
     {"case_sheet_ref": "MRN", "patient_ref": "MRN", "mrn_ref": "MRN", "ref_by": None, "ref_doctor": None,
      "ref_range": None, "dak_code": "PIN", "sample_code": None}),
    # a column of people under headers the label rules do not know: every row is flagged, whether or not its surname
    # is on the list; diagnosis, medicine, ward and trade columns beside it keep their text
    (["Enrollee", "Chaperone", "Working Impression", "Planned Test", "Treatment Given", "Occupation", "Ward Allotted"],
     [["Tarun Wadhwani", "Hemant Wadhwani", "Iron Deficiency", "Lipid Profile", "Inj. Ceftriaxone 1 g IV BD", "Daily Wager", "Lotus Care"],
      ["Meera Ghanekar", "Sunita Ghanekar", "Viral Hepatitis", "Liver Function Test", "Tab. Telmisartan 40 mg OD", "Home Maker", "Lakeview Ward"],
      ["Siddharth Shirodkar", "Rekha Shirodkar", "Renal Colic", "Complete Blood Count", "Syp. Cetirizine 5 ml HS", "Govt Employee", "Lotus Care"],
      ["Anjali Tendulkar", "Vivek Chaudhry", "Dengue Fever", "Chest Xray", "Tab. Metformin 500 mg BD", "Daily Wager", "Lakeview Ward"]],
     {"Enrollee": "PATIENT_NAME", "Chaperone": "RELATIVE_NAME", "Working Impression": None, "Planned Test": None,
      "Treatment Given": None, "Occupation": None, "Ward Allotted": None}),
    # the same in Devanagari, with a Hindi diagnosis column and a drug column that must survive
    (["आवेदक", "सहचर", "प्रारंभिक आकलन", "औषधि"],
     [["कमला नागपाल", "रमेश नागपाल", "तीव्र बुखार", "पैरासिटामोल गोली"],
      ["दीपक सहगल", "सुनीता सहगल", "उच्च रक्तचाप", "मेटफॉर्मिन टैबलेट"],
      ["रेखा ठाकरे", "मोहन ठाकरे", "मधुमेह रोग", "एमलोडिपिन गोली"],
      ["अमन वाघमारे", "पूजा वाघमारे", "निमोनिया संक्रमण", "सिरप सेटिरिजिन"]],
     {"आवेदक": "PATIENT_NAME", "सहचर": "RELATIVE_NAME", "प्रारंभिक आकलन": None, "औषधि": None}),
    # two-word organisms, drugs and vaccines under unknown headers look like names but are not: no listed surname
    # and no surname shared row by row with another column of people, so every cell keeps its text
    (["Isolate", "Sensitive To", "Vaccine Given", "Next Due"],
     [["Escherichia Coli", "Piperacillin Tazobactam", "Pentavalent Booster", "Measles Rubella"],
      ["Klebsiella Pneumoniae", "Meropenem Imipenem", "Rotavirus Oral", "Japanese Encephalitis"],
      ["Staphylococcus Aureus", "Vancomycin Linezolid", "Inactivated Polio", "Typhoid Conjugate"],
      ["Pseudomonas Aeruginosa", "Colistin Polymyxin", "Measles Rubella", "Vitamin Supplement"]],
     {"Isolate": None, "Sensitive To": None, "Vaccine Given": None, "Next Due": None}),
    # a column of repeated two-word categories is not a column of people
    (["Care Route", "Pickup"], [["Walk In", "Open Camp"], ["Open Camp", "Walk In"], ["Walk In", "Walk In"],
                                ["Walk In", "Open Camp"], ["Open Camp", "Open Camp"]],
     {"Care Route": None, "Pickup": None}),
    # twelve digits grouped 4-4-4 with dots are an Aadhaar number; a date-time stamp, a version and lab values are not
    (["KYC Number", "Log Stamp", "Build", "Result"],
     [["3540.4903.0424", "2024.0115.1030", "4.2.1", "1.0234"], ["6472.2828.3610", "2025.1130.0905", "4.2.2", "7.5000"],
      ["8831.0057.2294", "2023.0302.2350", "4.3.0", "0.9981"]],
     {"KYC Number": "AADHAAR", "Log Stamp": None, "Build": None, "Result": None}),
    # an unreadable header over phone numbers written with odd spacing; other long numbers are not phones
    (["zz_reach", "zz_bill"], [["9412 7 30518", "4500.00"], ["70112-904-18", "1200.50"], ["8800 41 2276", "980.00"]],
     {"zz_reach": "PHONE", "zz_bill": None}),
]


def _run_tables() -> int:
    failed = 0
    for headers, rows, expected in TABLES:
        records = [{"record_id": f"t.csv#row:{n}", "file": "t.csv", "loc": f"row:{n}", "fmt": "csv",
                    "fields": [{"path": f"col:{i}", "kind": "value", "context": h, "value": v}
                               for i, (h, v) in enumerate(zip(headers, row))]} for n, row in enumerate(rows, 1)]
        for n, result in enumerate(detect_file(records)):
            for header, kind in expected.items():
                found = [f["type"] for f in result["findings"] if f["path"] == f"col:{headers.index(header)}"]
                if (kind is None and found) or (kind is not None and kind not in found):
                    failed += 1
                    print(f"FAIL  column {header} row {n + 1}: expected {kind}, got {found}")
    return failed


# one column: (header, cell, strings that MUST be found, strings that MUST survive). The header is only a hint:
# a "PIN" column may hold the whole address, and "Ward / Patient" holds a bed number and a person
CELLS = [
    ("res_pin", "7/21, Teliarganj, 211004", ["7/21", "Teliarganj", "211004"], []),
    ("Postal Entry", "Flat 6-C, Ulubari, 781007", ["Flat 6-C", "Ulubari", "781007"], []),
    ("Dwelling/PIN", "Kachhi Basti, opp. Water Tank, 302016", ["Kachhi Basti", "opp. Water Tank", "302016"], []),
    ("PIN Code", "211004", ["211004"], []),
    ("pin_code", "PIN 211004", ["211004"], ["PIN"]),
    ("Pincode", "not recorded, ask later", [], ["not recorded", "ask later"]),
    ("Ward / Patient", "Bed 21 - Ishrat Jahan Ansari", ["Ishrat Jahan Ansari"], ["Bed 21"]),
    ("bed_patient", "Cot 3: Thangkhal Haokip", ["Thangkhal Haokip"], ["Cot 3"]),
    ("Patient", "Bed 8 - Devika Ranganathan", ["Devika Ranganathan"], ["Bed 8"]),
    ("Patient", "Ward 3 Bed 8 - Devika Ranganathan", ["Devika Ranganathan"], ["Ward 3", "Bed 8"]),
    ("Ward / Patient", "Female Medical Ward", [], ["Female Medical Ward"]),
    ("Ward / Patient", "Surgical Ward B", [], ["Surgical Ward"]),
    ("bed_patient", "Bed 14", [], ["Bed 14"]),
    ("Ward / Patient", "Ward 4 - Male Surgical", [], ["Male Surgical"]),
    ("Ward / Patient", "Ishrat Jahan Ansari", ["Ishrat Jahan Ansari"], []),
    ("patient_ward", "Maternity", [], ["Maternity"]),
    # dotted short forms in headers
    ("P.I.N.", "781014", ["781014"], []),
    ("U.H.I.D.", "55-204-9911", ["55-204-9911"], []),
    # landmark and neighbourhood headers
    ("Landmark", "next to the old post office", ["old post office"], []),
    ("ptNbhd", "Lalpur Basti", ["Lalpur Basti"], []),
    ("Nearby", "dairy booth", ["dairy booth"], []),
    # a notes column stays a notes column even when a nurse or doctor writes it
    ("wardNurseNote", "son Nandlal informed, BP 120/80", ["Nandlal"], ["BP 120/80"]),
    ("Doctor Remarks", "Continue Metformin 500 mg, wife Jasleen counselled", ["Jasleen"], ["Metformin 500 mg"]),
    ("Doctor", "Tarulata Mahanta", [], ["Tarulata Mahanta"]),
    ("Student", "Barsha Hazarika", ["Barsha Hazarika"], []),
    # relative columns that put the relation first, or in brackets after the name
    ("kin_mentioned", "amma - Kiruba", ["Kiruba"], []),
    ("Relative", "papa Nandlal, didi Barsha", ["Nandlal", "Barsha"], []),
    ("Relative", "devrani Sumitra", ["Sumitra"], []),
    ("Brought By (with relation)", "Jasleen Gill (wife)", ["Jasleen Gill"], []),
    ("Brought By (with relation)", "self (walk in)", [], ["self"]),
    # an insurance number with an Aadhaar-looking tail is removed whole
    ("Policy No", "ACMEGEN-4821-5530-9917", ["ACMEGEN-4821-5530-9917"], []),

    # a name cell that runs into a sentence stops there, but never when another person follows
    ("Patient", "Barsha came with cough", ["Barsha"], ["cough"]),
    ("Patient", "Barsha with Nandlal", ["Barsha", "Nandlal"], []),
    ("Patient", "Barsha came with husband nandlal", ["Barsha", "nandlal"], []),
    # a header that is newly understood must not switch off the search for names
    ("P.I.N.", "wife Barsha Hazarika", ["Barsha Hazarika"], []),
    ("PIN", "ask wife Barsha Hazarika", ["Barsha Hazarika"], []),
    ("Student", "Ompal Rathi came with wife Barsha Hazarika", ["Barsha Hazarika"], []),
    ("Landmark", "Ompal Rathi came with wife Barsha Hazarika", ["Ompal Rathi", "Barsha Hazarika"], []),
    ("Landmark", "Paracetamol given since 2 days", [], ["Paracetamol"]),
    ("fon_no", "9412 7 30518", ["9412 7 30518"], []),
    ("fon_no", "ask wife Barsha Hazarika", ["Barsha Hazarika"], []),
    # only a plain "student" column holds names; a hospital near by is not a landmark of a home
    ("student_vision", "normal both eyes", [], ["normal"]),
    ("Student Remarks", "attends regularly, weight low", [], ["attends"]),
    ("Nearby Hospital", "District Hospital Sehore", [], ["District Hospital"]),
    # "relative contact" columns hold a name, a number or both, even though "contact" reads as a phone label
    ("परिजन_संपर्क", "भाई नंदलाल महंत", ["नंदलाल महंत"], []),
    ("Guardian Contact", "Barsha Hazarika 94127-30518", ["Barsha Hazarika", "94127-30518"], []),
    ("Guardian Contact", "94127 30518", ["94127 30518"], []),
    ("Attendant Mobile", "not available", [], ["not available"]),
]


def _run_mixed_column() -> int:
    """Mostly phone numbers under an unreadable header: the one cell that names a person must still be searched."""
    values = ["9412 7 30518", "70112-904-18", "8800 41 2276", "9435 2 11870", "ask wife Barsha Hazarika"]
    records = [{"record_id": f"t.csv#row:{n}", "file": "t.csv", "loc": f"row:{n}", "fmt": "csv",
                "fields": [{"path": "col:0", "kind": "value", "context": "zz_reach2", "value": v}]}
               for n, v in enumerate(values, 1)]
    found = [f["text"] for f in detect_file(records)[-1]["findings"]]
    if not any("Barsha Hazarika" in f for f in found):
        print(f"FAIL  mixed phone column: found {found}")
        return 1
    return 0


def _run_cells() -> int:
    failed = 0
    for header, value, must_find, must_keep in CELLS:
        record = {"record_id": "t.csv#row:1", "file": "t.csv", "loc": "row:1", "fmt": "csv",
                  "fields": [{"path": "col:0", "kind": "value", "context": header, "value": value}]}
        found = [f["text"] for f in detect_file([record])[0]["findings"]
                 if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]
        missed = [x for x in must_find if not any(x in f for f in found)]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        if missed or eaten:
            failed += 1
            print(f"FAIL  {header}: {value}\n      missed={missed} wrongly_removed={eaten}")
    return failed


# JSON cases: (pointer -> value or key, strings that MUST be found, strings that MUST survive)
DOCS = [
    # an unlisted two-word value is a person only when its label says so
    ({"organism": "Escherichia Coli", "sign": "Murphy Positive", "reviewer": "Tshering Wangdi"},
     ["Tshering Wangdi"], ["Escherichia Coli", "Murphy Positive"]),
    # lookup tables keyed by people, whatever the table is called
    ({"on_call_map": {"Barnali Thengal": "bed 3"}}, ["Barnali Thengal"], ["bed 3"]),
    ({"drug_index": {"Amlodipine Besylate": "5 mg"}, "ward_map": {"General Ward": "2"},
      "vital_signs": {"Heart Rate": "88", "Chief Complaint": "cough"}},
     [], ["Amlodipine Besylate", "General Ward", "Heart Rate", "Chief Complaint"]),
    ({"column_map": {"Referral Source": "ref_src"}, "patient_tests": [{"name": "Lipid Profile"}]},
     [], ["Referral Source", "Lipid Profile"]),
    # a table whose name says nothing about people keeps its keys
    ({"billing_map": {"Room Rent": "1200"}, "symptom_index": {"Joint Stiffness": "1"}, "discount_map": {"Senior Citizen": "10"},
      "organization": {"contact": {"name": "Help Desk"}}}, [], ["Room Rent", "Joint Stiffness", "Senior Citizen", "Help Desk"]),
    # the closest parent decides whose name it is
    ({"organization": {"patient": {"name": "Barnali Thengal"}, "contact": {"name": "Devika Ranganathan"}}},
     ["Barnali Thengal", "Devika Ranganathan"], []),
    ({"organization": {"name": "Sunrise Care Centre", "department": {"name": "Cardiology"}},
      "patient": {"insurer": {"name": "Star Health"}}}, [], ["Sunrise Care Centre", "Cardiology", "Star Health"]),
    # FHIR: the identifier of a Patient / RelatedPerson is removed whatever its shape; everything else in the bundle stays
    ({"resourceType": "Bundle", "type": "collection", "entry": [
        {"fullUrl": "urn:uuid:pt-71", "resource": {
            "resourceType": "Patient", "id": "pt-71",
            "identifier": [{"system": "https://example.org/patient-no", "value": "7340192"},
                           {"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]},
                            "value": "4123"},
                           {"system": "https://example.org/opaque", "value": "QZ-AB"}],
            "gender": "female"}},
        {"fullUrl": "urn:uuid:rp-72", "resource": {
            "resourceType": "RelatedPerson", "id": "rp-72", "patient": {"reference": "Patient/pt-71"},
            "identifier": [{"system": "https://example.org/rel-no", "value": "88123"}]}},
        {"fullUrl": "urn:uuid:enc-73", "resource": {
            "resourceType": "Encounter", "id": "enc-73", "status": "finished",
            "identifier": [{"system": "https://example.org/visits", "value": "6650217"}],
            "subject": {"reference": "Patient/pt-71"}}},
        {"fullUrl": "urn:uuid:obs-74", "resource": {
            "resourceType": "Observation", "id": "obs-74", "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "718-7", "display": "Haemoglobin"}]},
            "subject": {"reference": "Patient/pt-71"}, "valueQuantity": {"value": 10.4, "unit": "g/dL"}}},
        {"fullUrl": "urn:uuid:org-75", "resource": {
            "resourceType": "Organization", "id": "org-75", "identifier": [{"value": "5509134"}]}}]},
     ["7340192", "4123", "QZ-AB", "88123"],
     ["6650217", "718-7", "10.4", "g/dL", "Patient/pt-71", "http://loinc.org", "5509134", "pt-71", "Haemoglobin"]),
    # the patient's identifier inside another resource's subject reference
    ({"resourceType": "Observation", "id": "o1", "subject": {"identifier": {"system": "https://example.org/uhid", "value": "3120045"}},
      "code": {"coding": [{"system": "http://snomed.info/sct", "code": "271649006"}]}, "valueQuantity": {"value": 128}},
     ["3120045"], ["271649006", "128", "http://snomed.info/sct"]),
    # JSON that is not FHIR but has the same shape: a patient's identifier list, any shape
    ({"patients": [{"identifier": [{"system": "hospital-no", "value": "60918"}], "visit": {"identifier": [{"value": "7712093"}]}}],
      "organization": {"identifier": [{"value": "9034112"}]}},
     ["60918"], ["7712093", "9034112"]),
    # plain JSON (no resourceType): the "display" / "text" / "full" of a key that names only a person is that person's
    # name, and its parts are then removed from the notes
    ({"subject": {"display": "Devika Pharswan"}, "notes": "Devika reviewed, Pharswan family informed. Pulse 76, Hb 10.9."},
     ["Devika Pharswan", "Devika", "Pharswan"], ["Pulse 76", "Hb 10.9", "reviewed"]),
    ({"beneficiary": [{"display": "Smt. T. K. Jhinkwan (46 F)"}], "guardian": {"text": "Omwati Bisht"},
      "patientDetails": {"full": "Negi, Harshul"}}, ["T. K. Jhinkwan", "Omwati Bisht", "Negi, Harshul"], ["46 F"]),
    ({"patient": {"text": "फूलमती रावत"}, "insured": {"text": "Shri Bhuwan Kholiya"},
      "notes": "Bhuwan counselled. K/C/O DM2."}, ["फूलमती रावत", "Bhuwan Kholiya", "Bhuwan"], ["K/C/O DM2", "counselled"]),
    # the same keys holding anything but a name, and keys that are not only a person, keep their text
    ({"subject": {"text": "Medication Review"}, "message": {"subject": {"display": "Discharge Summary"}},
      "patient": {"text": "Under Observation", "display": "Type 2 Diabetes"}, "member": {"display": "Gold Plan 2"},
      "client": {"display": "City Diagnostics"}, "person": {"text": "Plan Iron Sucrose 100 mg"},
      "subjectCategory": {"display": "Senior Citizen"}, "patientCondition": {"text": "Chronic Gastritis"},
      "patient_education": {"display": "Foot Exercises"}, "product": {"display": "Oral Rehydration Salts"},
      "code": {"text": "Peripheral Smear"}, "pt": {"text": "Lives Alone"}, "client_ref": {"text": "High Risk"}},
     [], ["Medication Review", "Discharge Summary", "Under Observation", "Type 2 Diabetes", "Gold Plan",
          "City Diagnostics", "Iron Sucrose", "Senior Citizen", "Chronic Gastritis", "Foot Exercises",
          "Rehydration", "Peripheral Smear", "Lives Alone", "High Risk"]),
    # an e-mail saved as JSON: its "subject" is a title when it holds a document word
    ({"subject": "Referral - Chandni Mamgain (IPD 6204)", "body": "Referral enclosed. Mamgain is on Tab. Torsemide 10 mg."},
     ["Chandni Mamgain", "6204", "Mamgain"], ["Referral", "Torsemide 10 mg"]),
]


def _walk(node, ptr=""):
    items = node.items() if isinstance(node, dict) else enumerate(node)
    for k, v in items:
        child = f"{ptr}/{k}"
        if isinstance(node, dict):
            yield {"path": f"key:{child}", "kind": "key", "context": None, "value": k}
        if isinstance(v, (dict, list)):
            yield from _walk(v, child)
        else:
            yield {"path": child, "kind": "value", "context": str(k), "value": str(v)}


def _run_docs() -> int:
    failed = 0
    for data, must_find, must_keep in DOCS:
        record = {"record_id": "t.json#doc", "file": "t.json", "loc": "doc", "fmt": "json", "fields": list(_walk(data))}
        found = [f["text"] for f in detect_file([record])[0]["findings"]
                 if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]
        missed = [x for x in must_find if x not in found]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        if missed or eaten:
            failed += 1
            print(f"FAIL  {data}\n      missed={missed} wrongly_removed={eaten}")
    return failed


# a name run together or in lowercase inside a file name: (file name, text, expected pieces found in the file name)
FILENAMES = [
    ("बरनाली_शर्मा_पर्चा.txt", "BP 110/70\n", ["बरनाली_शर्मा"]),
    ("ds-barnalithengal-31145549.txt", "Patient Name: Barnali Thengal\n", ["barnalithengal"]),
    ("ds_devika_ranganathan.txt", "Patient Name: Devika Ranganathan\n", ["devika_ranganathan"]),
    ("referral.txt", "Subject: Referral - Chandni Mamgain (IPD 6204)\nReferral enclosed.\n", []),
]


def _run_filenames() -> int:
    failed = 0
    for name, text, expected in FILENAMES:
        records = [{"record_id": f"{name}#@file", "file": name, "loc": "@file", "fmt": "text",
                    "fields": [{"path": "filename", "kind": "filename", "context": None, "value": name}]},
                   {"record_id": f"{name}#doc", "file": name, "loc": "doc", "fmt": "text",
                    "fields": [{"path": "text", "kind": "text", "context": None, "value": text}]}]
        found = [f["text"] for f in detect_file(records)[0]["findings"]]
        # nothing expected: the file name must be left as it is
        if not all(any(x in f for f in found) for x in expected) or (not expected and found):
            failed += 1
            print(f"FAIL  file name {name}: found {found}")
    return failed


# HL7 v2 messages saved as text (invented data): each segment is {field number: text}; the separator between segments
# is given per message (\n, \r or \r\n). (segments, separator, strings that MUST be found, strings that MUST survive)
_MSH = "MSH|^~" + _BS + "&|ADT1|CITYCLINIC|LIS|CITYCLINIC|20250614093015||ORU^R01|C20991|P|2.5"


def _seg(name: str, fields: dict[int, str]) -> str:
    return name + "".join("|" + fields.get(i, "") for i in range(1, max(fields) + 1))


HL7_MESSAGES = [
    ([_MSH,
      _seg("PID", {1: "1", 2: "88120045", 3: "702194^^^CC^MR~551203998877^^^GOV^NI", 5: "GUPTA^NEELAM^KAMLA", 6: "MISHRA^SAVITRI",
                   7: "19720809", 8: "F", 11: "14 Gandhi Marg^Behind Post Office^Raebareli^UP^229001^IN",
                   13: "0535-2271904^PRN^PH~9936120045^PRN^CP", 19: "334-55-9021"}),
      _seg("NK1", {1: "1", 2: "TIWARI^ASHOK", 3: "BRO", 4: "7 Station Road^^Raebareli^UP^229001", 5: "9936555010"}),
      _seg("PV1", {1: "1", 2: "I", 3: "MEDWARD^12^B", 7: "4455^SHARMA^KIRAN", 44: "20250613120000"}),
      _seg("OBR", {1: "1", 2: "ORD551", 3: "FIL778", 4: "CBC^Complete Blood Count", 7: "20250614080000"}),
      _seg("OBX", {1: "1", 2: "NM", 3: "718-7^Hemoglobin^LN", 5: "9.8", 6: "g/dL", 7: "12.0-15.5", 8: "L", 11: "F"}),
      _seg("OBX", {1: "2", 2: "ST", 3: "630-4^Culture^LN", 5: "No growth after 48 hours", 11: "F"}),
      _seg("NTE", {1: "1", 3: "Result discussed with Neelam Gupta."})],
     "\n",
     ["GUPTA", "NEELAM", "KAMLA", "MISHRA", "SAVITRI", "702194", "551203998877", "19720809", "334-55-9021", "14 Gandhi Marg",
      "Behind Post Office", "Raebareli", "229001", "0535-2271904", "9936120045", "TIWARI", "ASHOK", "7 Station Road", "9936555010",
      "Neelam Gupta"],
     ["Hemoglobin", "9.8", "g/dL", "12.0-15.5", "718-7", "No growth after 48 hours", "MEDWARD", "Complete Blood Count",
      "20250614093015", "20250614080000", "20250613120000", "CITYCLINIC", "ORD551", "FIL778"]),
    # segments ending in a bare carriage return (the HL7 standard), and a guarantor and an insured person
    ([_MSH.replace("20250614093015", "202507021415"),
      _seg("EVN", {1: "A04", 2: "202507021415"}),
      _seg("PID", {1: "1", 3: "KM-904170^^^SUN^MR", 5: "VERMA^SUNITA", 7: "19881104", 8: "F", 11: "22 Lake View^^Mohan Nagar^MP^462003",
                   13: "(0755)4017733"}),
      _seg("GT1", {1: "1", 3: "VERMA^PRAKASH", 5: "5 Temple Rd^^Mohan Nagar^MP^462003", 6: "9425011100"}),
      _seg("IN1", {1: "1", 2: "PLAN9", 4: "STAR CARE", 16: "VERMA^SUNITA", 17: "SELF", 18: "19881104", 36: "POL4455120"}),
      _seg("OBX", {1: "1", 2: "NM", 3: "2160-0^Creatinine^LN", 5: "1.1", 6: "mg/dL", 7: "0.6-1.2", 8: "N"})],
     "\r",
     ["VERMA", "SUNITA", "PRAKASH", "KM-904170", "19881104", "22 Lake View", "Mohan Nagar", "462003", "(0755)4017733", "5 Temple Rd",
      "9425011100", "POL4455120"],
     ["Creatinine", "1.1", "mg/dL", "0.6-1.2", "2160-0", "202507021415", "PLAN9", "STAR CARE", "SUNRISEMED"]),
    # coded fields are not free text: the message type "ORU^R01" next to "M7" (a control id) is not an age and sex,
    # a unit code "F01" is not a name; a phone written into a coded field is still found
    (["MSH|^~\\&|LIS|DISTLAB|EMR|DISTLAB|202504110930||ORU^R01|M7|P|2.5",
      _seg("PID", {1: "1", 3: "330918^^^DL^MR", 5: "KANDPAL^REKHA", 7: "19650304", 8: "F"}),
      _seg("OBR", {1: "1", 4: "LFT^Liver Function^L", 16: "F01^BHATT^ANIL"}),
      _seg("OBX", {1: "1", 2: "NM", 3: "1742-6^ALT^LN", 5: "64", 6: "U/L", 7: "7-56", 8: "H", 11: "F", 16: "9412088123"})],
     "\n",
     ["KANDPAL", "REKHA", "330918", "19650304", "9412088123"],
     ["ORU^R01", "M7", "Liver Function", "1742-6", "ALT", "64", "U/L", "7-56", "202504110930"]),
    # not a message: pipes in ordinary text, and a message with no MSH line, are read as free text only
    (["Rx|Tab Paracetamol 500 mg|1-0-1", "BP|112/78|mmHg"], "\n", [], ["Paracetamol", "112/78"]),
]


def _run_hl7() -> int:
    failed = 0
    for segments, sep, must_find, must_keep in HL7_MESSAGES:
        text = sep.join(segments) + sep
        record = {"record_id": "m.txt#doc", "file": "m.txt", "loc": "doc", "fmt": "text",
                  "fields": [{"path": "text", "kind": "text", "context": None, "value": text}]}
        findings = detect_file([record])[0]["findings"]
        kept = [f for f in findings if f["type"] not in ("CONDITION", "DISTRICT", "GENDER")]
        found = [f["text"] for f in kept]
        missed = [x for x in must_find if not any(x in f for f in found)]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        # every finding replaced by a placeholder: same segments, same number of fields, same separators in each
        out = text
        for f in sorted(kept, key=lambda f: -f["start"]):
            out = out[:f["start"]] + "[X]" + out[f["end"]:]
        was, now = text.split(sep), out.split(sep)
        shape = len(was) == len(now) and all(a.count("|") == b.count("|") and a.count("~") == b.count("~")
                                             and (len(a.split("|")[0]) == 3) == (len(b.split("|")[0]) == 3)
                                             and (a.split("|")[0] == b.split("|")[0]) for a, b in zip(was, now))
        if segments[0].startswith("MSH"):
            shape = shape and all(a.count("^") >= b.count("^") for a, b in zip(was, now)) and all(
                a.count("^") == b.count("^") for a, b in zip(was, now) if not a.startswith("NTE"))
        if missed or eaten or not shape:
            failed += 1
            print(f"FAIL  HL7 message {segments[2][:30]}...: missed={missed} wrongly_removed={eaten} shape_kept={shape}")
    return failed


def main() -> int:
    failed = 0
    for line, must_find, must_keep in CASES:
        found = _run_line(line)
        missed = [x for x in must_find if not any(x in f for f in found)]
        eaten = [x for x in must_keep if any(x in f or f in x for f in found)]
        if missed or eaten:
            failed += 1
            print(f"FAIL  {line}\n      missed={missed} wrongly_removed={eaten}")
    table_failures = _run_tables() + _run_mixed_column()
    print(f"{len(TABLES)} column tables checked, {table_failures} problems")
    cell_failures = _run_cells()
    print(f"{len(CELLS)} single cells checked, {cell_failures} problems")
    table_failures += cell_failures
    doc_failures = _run_docs() + _run_filenames()
    print(f"{len(DOCS)} JSON documents and {len(FILENAMES)} file names checked, {doc_failures} problems")
    hl7_failures = _run_hl7()
    print(f"{len(HL7_MESSAGES)} HL7 v2 messages checked, {hl7_failures} problems")
    doc_failures += hl7_failures
    print(f"{len(CASES) - failed}/{len(CASES)} cases passed")  # keep last: tools read the last line
    return 1 if failed or table_failures or doc_failures else 0


if __name__ == "__main__":
    sys.exit(main())
