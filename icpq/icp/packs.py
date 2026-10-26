"""Industry suggestion packs for the ICP wizard. They are SUGGESTIONS only: the wizard shows them as one-click chips, and
anything can be removed, edited or replaced with custom criteria. The engine never reads a pack directly; only the saved
profile counts.

Each signal suggestion: id, label, category, patterns (phrases / re:regex), markers (explicit-proof phrases), requirement
(mandatory|preferred|negative|info), weight, use_case."""


def S(id, label, category, patterns, markers=(), requirement="preferred", weight=10, use_case=""):
    return {"id": id, "label": label, "category": category, "patterns": list(patterns), "markers": list(markers),
            "requirement": requirement, "weight": weight, "use_case": use_case or label}


COMMON_BUYING = [
    S("hiring_growth", "Hiring / team growth", "buying", ["we're hiring", "we are hiring", "join our team", "open positions", "now hiring"], weight=5),
    S("new_locations", "Opening new locations", "buying", ["new location", "grand opening", "now open in", "opening soon", "newest location"], weight=10),
    S("funding", "Recent funding / investment", "financial", ["raised", "series a", "series b", "series c", "funding round", "investment from"], weight=10),
    S("acquisition", "Acquisition / merger activity", "organizational", ["acquired", "acquisition of", "merger with", "has acquired"], weight=8),
    S("rfp", "Open RFP / procurement", "buying", ["request for proposal", "rfp", "request for proposals", "invitation to bid"], weight=15),
]

PACKS = [
    {"id": "saas", "label": "B2B software / SaaS", "match": ["software", "saas", "platform", "app", "cloud", "api", "crm", "erp"],
     "ideal": "Mid-market companies with a sales or operations team that still relies on spreadsheets and manual work.",
     "industries": ["Software", "Information Technology", "Financial Services", "Professional Services", "Retail", "Manufacturing"],
     "segments": [("TECH", "Technology", ["software", "information technology", "internet", "computer"]),
                  ("FINANCIAL", "Financial Services", ["bank", "financial", "insurance", "credit"]),
                  ("HEALTHCARE", "Healthcare", ["health", "hospital", "medical", "clinic"]),
                  ("RETAIL", "Retail & eCommerce", ["retail", "ecommerce", "e-commerce", "consumer"])],
     "signals": [S("sales_team", "Has a sales / customer team", "organizational", ["sales team", "account executive", "customer success", "sales representatives"], weight=10),
                 S("manual_process", "Manual / spreadsheet processes", "problem", ["spreadsheet", "manual process", "paper forms", "re:\\bexcel\\b"], weight=15),
                 S("integrations_page", "Publishes integrations / API", "technology", ["integrations", "api documentation", "developer portal"], weight=8),
                 S("free_trial", "Self-serve product (trial / pricing page)", "behavioral", ["free trial", "start your trial", "pricing plans", "request a demo"], weight=5),
                 S("security_compliance", "Security / compliance commitments", "compliance", ["soc 2", "iso 27001", "gdpr", "hipaa"], ["soc 2 type ii", "iso 27001 certified"], weight=10)],
     "technologies": ["Salesforce", "HubSpot", "Microsoft Dynamics", "Zendesk", "Shopify", "NetSuite", "Slack"],
     "titles": ["VP Sales", "Head of Revenue Operations", "CTO", "VP Operations", "Director of IT"], "departments": ["Sales", "RevOps", "IT", "Operations"],
     "search": ['site:{domain} "{signal}"'],
     "link_hints": ["product", "platform", "integrations", "pricing", "careers", "about", "security"]},

    {"id": "healthcare", "label": "Healthcare / clinics", "match": ["health", "clinic", "patient", "medical", "dental", "hospital", "pharma", "care"],
     "ideal": "Multi-location clinic groups and hospitals with high patient volume and online scheduling.",
     "industries": ["Hospitals and Health Care", "Medical Practices", "Dental", "Mental Health Care", "Veterinary"],
     "segments": [("HOSPITALS", "Hospitals", ["hospital", "health system"]), ("CLINICS", "Clinics & practices", ["clinic", "medical practice", "physicians"]),
                  ("DENTAL", "Dental", ["dental", "orthodont"]), ("BEHAVIORAL", "Behavioral health", ["mental health", "behavioral", "counsel"])],
     "signals": [S("online_booking", "Online appointment booking", "behavioral", ["book an appointment", "schedule an appointment", "book online", "request an appointment"], ["book online", "schedule online"], "mandatory", 20, "Appointment scheduling"),
                 S("multi_location", "Multiple locations", "operational", ["our locations", "find a location", "locations near you", "re:\\b\\d{2,4}\\s+(?:locations|clinics|offices)\\b"], ["find a location"], weight=15, use_case="Multi-site operations"),
                 S("patient_portal", "Patient portal", "technology", ["patient portal", "mychart", "patient login"], weight=10, use_case="Patient engagement"),
                 S("telehealth", "Telehealth offered", "behavioral", ["telehealth", "virtual visit", "telemedicine", "video visit"], weight=10, use_case="Virtual care"),
                 S("accepts_insurance", "Accepts insurance", "financial", ["insurance accepted", "we accept most insurance", "in-network"], weight=5)],
     "technologies": ["Epic", "Cerner", "athenahealth", "eClinicalWorks", "NextGen", "Dentrix", "Zocdoc"],
     "titles": ["Practice Administrator", "Director of Patient Access", "COO", "VP Operations", "CIO"], "departments": ["Operations", "Patient Access", "IT"],
     "disq": [("public_agency", "Government agency", "domain", ["re:\\.gov$"], "REVIEW")],
     "link_hints": ["locations", "appointment", "patients", "portal", "telehealth", "insurance", "services"]},

    {"id": "industrial", "label": "Manufacturing / industrial", "match": ["manufactur", "industrial", "factory", "machin", "parts", "supply", "equipment"],
     "ideal": "Manufacturers with multiple plants that sell through distributors and run an ERP.",
     "industries": ["Manufacturing", "Industrial Machinery", "Automotive", "Chemicals", "Plastics", "Food and Beverage Manufacturing"],
     "segments": [("DISCRETE", "Discrete manufacturing", ["machinery", "automotive", "electronics", "aerospace"]),
                  ("PROCESS", "Process manufacturing", ["chemical", "plastics", "food", "beverage", "pharmaceutical"]),
                  ("DISTRIBUTION", "Distribution", ["wholesale", "distribution", "distributor"])],
     "signals": [S("plants", "Multiple plants / facilities", "operational", ["manufacturing facilities", "our plants", "production facility", "re:\\b\\d+\\s+(?:plants|facilities)\\b"], weight=15),
                 S("iso_cert", "ISO / quality certification", "compliance", ["iso 9001", "as9100", "iatf 16949", "iso 13485"], ["iso 9001:2015", "certified to iso"], weight=10),
                 S("distributors", "Sells through distributors / dealers", "operational", ["find a distributor", "dealer locator", "authorized distributor", "become a dealer"], weight=10),
                 S("erp", "Runs an ERP", "technology", ["re:\\b(?:sap|oracle|epicor|infor|netsuite|dynamics 365)\\b"], weight=10),
                 S("capacity_expansion", "Capacity expansion", "buying", ["expansion", "new facility", "groundbreaking", "increase capacity"], weight=15)],
     "technologies": ["SAP", "Oracle", "Epicor", "Infor", "NetSuite", "Siemens", "Rockwell Automation"],
     "titles": ["Plant Manager", "VP Manufacturing", "Director of Operations", "Supply Chain Director", "CFO"], "departments": ["Operations", "Supply Chain", "Engineering", "Finance"],
     "link_hints": ["facilities", "quality", "certifications", "distributors", "about", "capabilities", "news"]},

    {"id": "logistics", "label": "Logistics / fleet / transportation", "match": ["fleet", "logistic", "truck", "transport", "freight", "delivery", "telematic", "shipping"],
     "ideal": "Companies running their own vehicle fleets: field service, delivery, construction and transportation.",
     "industries": ["Transportation", "Trucking", "Logistics", "Construction", "Utilities", "Field Services"],
     "segments": [("TRUCKING", "Trucking & freight", ["truck", "freight", "transport"]), ("FIELD", "Field services", ["hvac", "plumbing", "electrical", "pest", "landscap"]),
                  ("CONSTRUCTION", "Construction", ["construction", "contractor"]), ("DELIVERY", "Delivery", ["delivery", "courier", "logistics"])],
     "signals": [S("fleet", "Operates a vehicle fleet", "operational", ["our fleet", "fleet of", "trucks", "service vehicles", "re:\\b\\d+\\s+(?:trucks|vehicles|tractors)\\b"], ["fleet of"], "mandatory", 20, "Fleet operations"),
                 S("drivers_hiring", "Hiring drivers / technicians", "buying", ["cdl", "now hiring drivers", "driver jobs", "service technician"], weight=15, use_case="Workforce growth"),
                 S("dot_number", "DOT / MC registered", "compliance", ["re:\\busdot\\s*#?\\s*\\d{4,8}\\b", "re:\\bmc\\s*#?\\s*\\d{5,7}\\b", "dot number"], ["usdot"], weight=10),
                 S("service_area", "Multi-state service area", "operational", ["service area", "we serve", "serving customers in", "nationwide"], weight=5),
                 S("dispatch", "Dispatch / scheduling operation", "operational", ["dispatch", "same-day service", "24/7 service", "emergency service"], weight=10)],
     "technologies": ["Samsara", "Geotab", "Verizon Connect", "Motive", "ServiceTitan", "Omnitracs"],
     "titles": ["Fleet Manager", "Director of Operations", "VP Operations", "Safety Director", "Owner"], "departments": ["Fleet", "Operations", "Safety"],
     "link_hints": ["fleet", "careers", "drivers", "services", "about", "safety", "locations"]},

    {"id": "fintech", "label": "Financial services / fintech", "match": ["bank", "payment", "fintech", "lending", "credit", "insurance", "wealth", "financial"],
     "ideal": "Community banks and credit unions with digital banking and multiple branches.",
     "industries": ["Banking", "Credit Unions", "Insurance", "Financial Services", "Lending"],
     "segments": [("BANKS", "Banks", ["bank"]), ("CREDIT_UNIONS", "Credit unions", ["credit union"]), ("INSURANCE", "Insurance", ["insurance"]),
                  ("LENDING", "Lending", ["mortgage", "loan", "lending"])],
     "signals": [S("digital_banking", "Online / mobile banking", "technology", ["online banking", "mobile banking", "mobile app", "digital banking"], weight=15, use_case="Digital banking"),
                 S("branches", "Multiple branches", "operational", ["branch locations", "find a branch", "our branches", "atm locator"], weight=10),
                 S("fdic_ncua", "Regulated institution (FDIC / NCUA)", "compliance", ["member fdic", "federally insured by ncua", "equal housing lender"], ["member fdic", "ncua"], weight=10),
                 S("fraud_alerts", "Customer alerts programme", "behavioral", ["account alerts", "fraud alerts", "balance alerts"], weight=10, use_case="Account notifications")],
     "technologies": ["Jack Henry", "Fiserv", "FIS", "Q2", "Alkami", "nCino", "Temenos"],
     "titles": ["Chief Digital Officer", "VP Retail Banking", "CIO", "VP Marketing", "COO"], "departments": ["Digital", "Retail Banking", "IT", "Marketing"],
     "link_hints": ["online banking", "mobile", "locations", "branches", "security", "about", "alerts"]},

    {"id": "messaging", "label": "Customer messaging / communications", "match": ["sms", "text messag", "messaging", "voice", "contact center", "ccaas", "communication", "notification", "cpaas"],
     "ideal": "Organisations that already send their own text-message programmes (alerts, reminders, opt-in offers) at scale.",
     "industries": ["Higher Education", "Hospitals and Health Care", "Banking", "Retail", "Government Administration"],
     "segments": [("FINANCIAL_SERVICES", "Financial Services", ["bank", "credit", "insurance", "financial"]), ("HIGHER_ED", "Higher Education", ["higher education", "university", "college"]),
                  ("HEALTHCARE", "Healthcare", ["hospital", "health", "medical", "dental"]), ("GOVERNMENT_MUNICIPAL", "Government / Municipal", ["government", "public safety", "municipal"])],
     "signals": [S("sms_program", "Own text-message programme", "behavioral",
                   ["text alerts", "text message alerts", "sms alerts", "text reminders", "re:\\btext\\s+[\"'“]?\\w{2,15}[\"'”]?\\s+to\\s+\\d{5,6}\\b", "consent to receive text",
                    "agree to receive text", "re:\\breply\\s+[\"'“]?stop\\b", "msg & data rates", "message and data rates", "sms terms"],
                   ["reply stop", "reply help", "msg & data rates", "message and data rates", "message frequency varies", "re:\\btext\\s+\\w{2,15}\\s+to\\s+\\d{5,6}\\b", "short code"],
                   "mandatory", 30, "Text programme"),
                 S("two_way", "Two-way texting with customers", "behavioral", ["text us at", "text us anytime", "chat by text", "two-way texting"], weight=10, use_case="Customer service"),
                 S("contact_center", "Runs a contact center", "operational", ["contact center", "call center", "customer care center"], weight=10, use_case="Contact center"),
                 S("otp", "Verification codes by text", "technology", ["re:\\b(?:verification|security|one-time)\\s+(?:pass)?code\\b.{0,60}\\b(?:text|sms)\\b"], weight=10, use_case="OTP/authentication")],
     "use_cases": [("Appointment reminders", ["appointment", "reminder"]), ("Payment reminders", ["payment", "billing", "past due"]),
                   ("Emergency alerts", ["emergency", "closure", "weather"]), ("Marketing offers", ["offers", "promo", "deals", "discount"]),
                   ("Account notifications", ["balance", "fraud", "transaction", "account alert"])],
     "negative_context": ["scam", "smish", "phish", "fraudulent text", "never text", "crisis text line", "hotline"],
     "technologies": ["Genesys", "Five9", "Zendesk", "Salesforce Service Cloud", "Amazon Connect", "NICE CXone"],
     "titles": ["VP Customer Experience", "Director of Contact Center", "CMO", "Director of Digital Communications", "CIO"],
     "departments": ["Customer Experience", "Contact Center", "Marketing", "IT"],
     "sitemap_hints": ["sms", "text", "alerts", "notifications", "opt-in"],
     "common_paths": ["/sms-terms", "/privacy-policy", "/terms", "/text-messaging", "/privacy"],
     "search": ['site:{domain} "text message" OR sms OR "text alerts" OR "agree to receive"'],
     "link_hints": ["sms", "text", "alerts", "notifications", "privacy", "terms", "mobile", "opt-in", "contact"]},

    {"id": "services", "label": "Professional / marketing services", "match": ["agency", "consult", "marketing", "services", "advis", "staffing", "recruit"],
     "ideal": "Growing companies with a marketing team that invests in paid acquisition and events.",
     "industries": ["Retail", "Consumer Services", "Software", "Hospitality", "Real Estate"],
     "segments": [("CONSUMER", "Consumer brands", ["retail", "consumer", "apparel", "restaurant"]), ("B2B", "B2B companies", ["software", "manufacturing", "services"]),
                  ("HOSPITALITY", "Hospitality", ["hotel", "hospitality", "restaurant", "travel"])],
     "signals": [S("marketing_team", "In-house marketing team", "organizational", ["marketing team", "marketing manager", "brand manager", "head of marketing"], weight=10),
                 S("events", "Runs events / webinars", "behavioral", ["upcoming events", "webinar", "conference", "trade show"], weight=10),
                 S("ecommerce", "Sells online", "behavioral", ["add to cart", "shop now", "free shipping", "checkout"], weight=10),
                 S("loyalty", "Loyalty / rewards programme", "behavioral", ["rewards program", "loyalty program", "join our rewards"], weight=10)],
     "technologies": ["HubSpot", "Marketo", "Salesforce Marketing Cloud", "Klaviyo", "Google Analytics", "Shopify"],
     "titles": ["CMO", "VP Marketing", "Director of Demand Generation", "Head of Growth", "Brand Director"], "departments": ["Marketing", "Growth", "Brand"],
     "link_hints": ["about", "careers", "events", "shop", "rewards", "blog", "news"]},

    {"id": "realestate", "label": "Real estate / property", "match": ["real estate", "property", "proptech", "apartment", "rental", "home", "housing"],
     "ideal": "Property managers with large residential portfolios across several markets.",
     "industries": ["Real Estate", "Property Management", "Construction", "Hospitality"],
     "segments": [("RESIDENTIAL", "Residential", ["apartment", "residential", "multifamily", "homes"]), ("COMMERCIAL", "Commercial", ["commercial", "office", "industrial"]),
                  ("HOSPITALITY", "Hospitality", ["hotel", "resort", "vacation"])],
     "signals": [S("portfolio", "Large property portfolio", "operational", ["communities", "properties", "units", "re:\\b\\d{1,3}(?:,\\d{3})+\\s+(?:units|apartment homes)\\b"], weight=15),
                 S("online_leasing", "Online leasing / applications", "behavioral", ["apply online", "schedule a tour", "resident portal", "pay rent online"], weight=15),
                 S("multi_market", "Operates in several markets", "operational", ["markets", "states", "nationwide", "metro areas"], weight=10)],
     "technologies": ["Yardi", "RealPage", "AppFolio", "Entrata", "Buildium"],
     "titles": ["VP Property Management", "Regional Manager", "COO", "Director of Operations"], "departments": ["Operations", "Leasing", "IT"],
     "link_hints": ["communities", "properties", "residents", "apply", "about", "locations"]},
]

GENERIC = {"id": "generic", "label": "Something else (start blank)", "match": [], "ideal": "", "industries": [], "segments": [], "signals": [],
           "technologies": [], "titles": [], "departments": [], "link_hints": []}

DISQUALIFIER_CHOICES = [
    {"id": "competitor", "label": "Competitors / vendors of what I sell", "field": "name", "patterns": [], "action": "DQ"},
    {"id": "agency", "label": "Agencies & consultancies", "field": "industry", "patterns": ["advertising services", "marketing services", "business consulting"], "action": "DQ"},
    {"id": "fund", "label": "Investment funds & holding companies", "field": "industry", "patterns": ["venture capital", "private equity", "holding companies", "investment management"], "action": "DQ"},
    {"id": "government", "label": "Government bodies", "field": "domain", "patterns": ["re:\\.(?:gov|mil)$"], "action": "DQ"},
    {"id": "education", "label": "Schools & universities", "field": "domain", "patterns": ["re:\\.edu$", "re:\\.k12\\."], "action": "DQ"},
    {"id": "nonprofit", "label": "Non-profits", "field": "industry", "patterns": ["non-profit", "nonprofit", "philanthropy", "civic and social"], "action": "DQ"},
    {"id": "closed", "label": "Closed / acquired companies (site says so)", "field": "page", "patterns": ["has been acquired by", "is now part of", "permanently closed", "ceased operations"], "action": "REVIEW"},
]


def find(pack_id):
    return next((p for p in PACKS if p["id"] == pack_id), GENERIC)


def guess(text):
    t = (text or "").lower()
    best, score = GENERIC, 0
    for p in PACKS:
        n = sum(1 for m in p["match"] if m in t)
        if n > score:
            best, score = p, n
    return best["id"]


def public():
    """What the wizard shows: packs (without regex internals hidden; users see them and can edit) + disqualifier choices."""
    out = []
    for p in PACKS + [GENERIC]:
        out.append({"id": p["id"], "label": p["label"], "ideal": p.get("ideal", ""), "industries": p.get("industries", []),
                    "segments": [{"key": k, "label": lbl, "patterns": pats} for k, lbl, pats in p.get("segments", [])],
                    "signals": p.get("signals", []) + ([] if p["id"] == "generic" else []),
                    "buying": COMMON_BUYING, "technologies": p.get("technologies", []), "titles": p.get("titles", []),
                    "departments": p.get("departments", []), "use_cases": [{"tag": t, "patterns": pats} for t, pats in p.get("use_cases", [])],
                    "negative_context": p.get("negative_context", []), "sitemap_hints": p.get("sitemap_hints", []),
                    "common_paths": p.get("common_paths", []), "search": p.get("search", []), "link_hints": p.get("link_hints", []),
                    "disq": [{"id": i, "label": lbl, "field": f, "patterns": pats, "action": a} for i, lbl, f, pats, a in p.get("disq", [])]})
    return {"packs": out, "disqualifiers": DISQUALIFIER_CHOICES}
