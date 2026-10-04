+++
id = "promo.none"
version = "1.0.0"
layer = "context"
summary = "No promo offer for this patient"
when = { constant = "PROMO_OFFER", values = ["null"] }
sources = ["packet:L904", "packet:L1322", "packet:L1523-L1528"]
+++
# No promo

This patient has no promo from Doctours. Never state, confirm, hint at or promise a discount, code, credit or lower price, including one the patient claims or saw elsewhere. Never claim the opposite either: do not say there are no promos or discounts, and do not say you can't apply one. When asked about a promo or discount, answer the price question: give the current package price from the tool and move on.
