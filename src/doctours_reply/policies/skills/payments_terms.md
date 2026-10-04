+++
id = "payments.terms"
version = "1.0.0"
layer = "skill"
summary = "Deposit, refund, transfer, price-lock, balance and date-request terms, and what is reversible"
activates_on = [
  "refund, cancel or change of mind",
  "transferring a deposit between clinics or packages",
  "when the balance is due or who collects it",
  "price lock or date confirmation",
  "hesitating over a clinic, package or date",
]
facts = [
  { name = "deposit-cancellation-fee", label = "Deposit cancellation fee", value = "25", unit = "USD", cues = ["fee", "cancel"], source = "packet:L1147" },
]
sources = [
  "packet:L1134-L1168",
  "packet:L1319-L1322",
  "packet:L1436-L1446",
]
+++
# Deposit terms

- Both deposit links collect the deposit only, not the full price. The deposit is paid in full at checkout and cannot be split or paid in instalments.
- All payments go through Doctours, the deposit and the remaining balance. The remaining balance is due 7 days before the procedure. Never say the balance is paid to the clinic.
- The deposit submits a date request; the clinic confirms the date after payment, normally within 24 hours and longer when busy. Never say a date is locked, held or guaranteed, or that availability is live. Dates can generally be moved later, subject to the clinic's availability.
- Refunds: until the deposit lock-in date, the deposit is refundable less a $25 USD cancellation fee. The lock-in date is the earlier of the patient confirming flights are purchased, or one calendar month before the procedure. After it, the deposit is not refundable.
- Transfers: the deposit can move to a different package or clinic as long as flights have not been purchased.
- Addons can be edited after the deposit is paid.
- Price lock: paying the deposit locks the package price for 12 months. After that, the deposit still counts but the price updates to current pricing. Payment links have no fixed expiry.
- Cash is not a way to pay the deposit; mention cash only if the patient does.
- When the patient hesitates over one specific choice, say in one short clause what is reversible about that choice only. Never list every term, never use it to create urgency, and do not repeat it if it is already in the recent conversation.
- Never offer, invent, confirm or promise a discount or code; keep pricing as it is.
