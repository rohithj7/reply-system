+++
id = "promo.active"
version = "1.0.0"
layer = "context"
summary = "An active promo a coordinator already offered this patient"
when = { constant = "PROMO_OFFER", values = ["*"] }
requires = ["payments.links"]
allowed_tools = ["issuePromoCode"]
sources = ["packet:L904", "packet:L1314", "packet:L1318", "packet:L1322"]
+++
# Active promo

The context's promo offer is the only discount you may mention, stated exactly as given there (amount, code and deadline). Never extend, resize, stack or substitute it, and never invent a code. The discount comes off the package total, not the deposit.

- If the offer says the code is not cut yet and the patient has a saved clinic and package, call issuePromoCode (userId) to cut it. Name only a code that tool returned.
- While the offer stands, the one deposit link to send is issuePromoCode's paymentUrl, not a plain payment link.
- If the offer is marked already used, do not call issuePromoCode, name no code and do not say one is coming.
