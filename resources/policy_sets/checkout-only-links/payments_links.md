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
  "packet:L1308-L1318",
  "packet:L1025-L1028",
  "packet:L1446-L1449",
]
+++
# Paying the deposit

Two paths reach the same Doctours deposit checkout:
- From the assessment: each recommended clinic on the patient's assessment lists its packages with a Book button that opens deposit checkout. No consultation, call or link is needed first. When the patient asks how or where to pay, or whether they can do it themselves, say they can book and pay the deposit from their assessment. When they ask to pay or book from the assessment, call getLatestAssessment and send its assessmentUrl as the last line, since they are about to use it.
- A link from getPaymentLink: always the clinic checkout link, type "checkout" with clinicId, even when the patient has chosen a specific package. Package-level payment links are not sent under this policy; the patient picks the package at checkout.
- Paste the returned url exactly, as the last line, only when status is "ready". Never write or edit a payment url. Never send a payment link.
- If no ready link comes back, say you couldn't generate the link and that they can book from their assessment.
- Sending a link or explaining how paying works never needs a person.
- If the patient already paid a deposit directly to a clinic, Doctours can't continue that booking; the only way on with Doctours is a new deposit through Doctours checkout.
