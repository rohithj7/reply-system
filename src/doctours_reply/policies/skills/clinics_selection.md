+++
id = "clinics.selection"
version = "1.0.0"
layer = "skill"
summary = "Saving the patient's clinic and package choice, interest and tentative timing"
activates_on = [
  "leaning toward, choosing or torn between clinics or packages",
  "a month, season or date range for the procedure",
]
requires = ["clinics.facts"]
allowed_tools = [
  "updateUserClinicPreferences",
  "getPatientContext",
  "getSavedClinics",
  "getAllClinics",
  "getClinicPackages",
]
sources = ["packet:L1276-L1306", "packet:L1413-L1414", "packet:L1435"]
+++
# Saving a choice

Save with updateUserClinicPreferences, passing userId and a clinicSelection object. Use only clinic and package ids a tool returned this turn; resolve a named clinic with getAllClinics or getSavedClinics first.

- A lean toward ONE clinic counts as a selection: "I'm leaning toward X", "X sounds good", "probably X", "I think X is the one". Save it as clinicSelection.selectedClinicId this turn.
- Use clinicSelection.softClinicInterestIds only when the patient is genuinely torn between two or more clinics with no clear lean.
- One package chosen: clinicSelection.selectedPackageId, from the selected clinic's own package list. Torn between packages: clinicSelection.softPackageInterestIds. If a name matches more than one package, ask which one before saving.
- A month, season or date range: clinicSelection.tentativeProcedureDates as {"text": a short faithful paraphrase, "strength": "strong" | "medium" | "weak"}. Never invent dates. Tentative dates never go into working memory.
- Save at most once per turn, with everything the patient stated in that one call.
- After saving, reply as normal; do not announce that you saved anything.
