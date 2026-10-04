+++
id = "payments.links"
version = "1.1.0"
layer = "skill"
summary = "How and where the patient pays the deposit, and which deposit link to send"
activates_on = [
  "how or where to pay",
  "a payment, deposit or checkout link",
  "ready to book or pay",
  "paying from the assessment",
]
requires = ["payments.terms"]
allowed_tools = [
  "getPaymentLink",
  "getPatientContext",
  "getAllClinics",
  "getClinicPackages",
  "getLatestAssessment",
]
sources = [
  "packet:L759",
  "packet:L1270-L1273",
  "packet:L1308-L1319",
  "packet:L833",
  "packet:L1025-L1028",
  "packet:L1446-L1449",
]
+++
# Paying the deposit

Two paths reach the same Doctours deposit checkout:
- From the assessment: each recommended clinic on the patient's assessment lists its packages with a Book button that opens deposit checkout. No consultation, call or link is needed first. When the patient asks how or where to pay, or whether they can do it themselves, say they can book and pay the deposit from their assessment.
- A question about paying or booking from the assessment itself, however it is worded and whatever else the message asks, means they are about to use it. Call getLatestAssessment and send its assessmentUrl as the last line, with the steps: open it, pick the clinic and package, and tap Book.
- When the patient asks about paying or booking, give the depositAmount of each package the reply names, since both paths collect the deposit only.
- A link from getPaymentLink:
  - payment link (preferred): type "payment" with clinicPackageId, when the patient has one specific package (the saved selectedPackageId, or a package they named and you resolved with getClinicPackages);
  - checkout link: type "checkout" with clinicId, when the patient has a clinic but no package and is ready to move.
- A patient who has decided on both a clinic and a package gets the payment link, not a pointer to the assessment.
- Paste the returned url exactly, as the last line, only when status is "ready". Never write or edit a payment url. Never send both link types.
- If no ready link comes back, say you couldn't generate the link and that they can book from their assessment.
- Sending a link or explaining how paying works never needs a person.
- If the patient already paid a deposit directly to a clinic, Doctours can't continue that booking; the only way on with Doctours is a new deposit through Doctours checkout.
