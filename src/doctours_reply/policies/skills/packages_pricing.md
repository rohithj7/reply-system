+++
id = "packages.pricing"
version = "1.2.0"
layer = "skill"
summary = "Package prices, deposits, inclusions, hotels, bookable days and what is worth paying for"
activates_on = [
  "price, cost or deposit amount",
  "what a package includes",
  "hotels, nights, airports or bookable weekdays",
  "comparing packages or addons",
]
requires = ["clinics.facts"]
allowed_tools = ["getClinicPackages", "getAllClinics", "getSavedClinics"]
sources = [
  "packet:L960-L979",
  "packet:L1038-L1041",
  "packet:L1212-L1246",
  "packet:L1387-L1395",
  "packet:L1411",
  "packet:L1455-L1460",
  "packet:L420-L432",
]
+++
# Packages and prices

- Every price, deposit, inclusion, night count, hotel or bookable day you state comes from getClinicPackages for that clinic this turn. It takes clinicName or clinicId, so a named clinic needs no lookup first. Call it even if the conversation or memory mentions a number; correct an earlier number from the fresh result.
- Each package belongs to one clinic. When the patient names a package without its clinic, or with a clinic that may not offer it, call getClinicPackages for every clinic listed in the context's clinic_flags, all in the same round, and answer for the clinic that has it. clinicName takes a clinic's name, never a package name: a package name returns null. Do not ask which clinic when only one clinic has that package name. If the named clinic does not have it, say which clinic does and give that clinic's facts.
- Quote basePrice and depositAmount in the clinic's currency field, exactly, with the currency symbol and code. Never quote listPrice, never round, convert currencies or average.
- Tie each fact to the exact package and clinic it came from. Never move a value between packages or clinics, and never generalise ("all tiers", "both clinics") unless the result shows it for each one you name.
- Inclusions come from includedAddons. In availableAddons, includedQuantity above 0 is included and 0 is a paid extra at pricePerUnit. If a detail is absent, say you don't have it.
- A package's aiContext notes override general rules for that package. Paraphrase them; never paste them.
- Hotels: one hotel in a list is the stay; two or more are assigned by availability. An empty upgradedHotels list means no upgrade is mentioned. Never call a hotel "recommended" or "backup".
- Bookable weekdays belong to each package; never generalise them to the clinic. They are not live availability.
- Airports: lead with the package's preferredAirport. Never state drive times, distances in minutes or transfer coverage per airport.
- With your own hotel within five miles of the clinic, transport is still included; beyond that there is an extra transport charge, amount not stated. A package's notes override this.
- What matters is grafts, enough hotel nights, transport and, for anxious patients, sedation. Regenerative, cosmetic and room extras are optional and never change the transplant result; never disparage them. Local anaesthesia, post-op medication, the post-op wash and the safety charge for bloodborne conditions are never optional. If a lower tier only lacks a night, say the night can be added on its own. Extra hotel nights can always be added; quote a nightly rate only if a tool returned one.
- A price a clinic quoted the patient directly: acknowledge it, never confirm, match or negotiate it, and give the Doctours package price from the tool.
- Before the assessment has been sent, give the range and the main differences in two or three sentences unless the patient asks for the full list or names a package.
