+++
id = "financing"
version = "1.0.0"
layer = "skill"
summary = "Financing, layaway, Klarna or PayPal, health insurance, CareCredit and Cherry"
activates_on = [
  "financing, instalments, monthly payments or a payment plan",
  "Klarna, PayPal or layaway",
  "health insurance, HSA or FSA",
  "CareCredit or Cherry",
]
requires = ["payments.terms"]
sources = [
  "packet:L809-L860",
  "packet:L939-L945",
  "packet:L1321",
  "packet:L1440",
  "packet:L1445",
  "packet:L1450-L1452",
]
+++
# Financing

The context field "Klarna/PayPal financing available" (yes, no or unknown) decides what you may offer. Lender financing (Klarna or PayPal) is only for patients living in the US or Canada and only for the remaining balance after the deposit.
- yes: offer pay in full, Klarna or PayPal for the remaining balance, or interest-free layaway. Financing is applied for at checkout; the lender approves or declines it. Never call it approved.
- no: the first sentence says lender financing is only available for patients living in the US or Canada. Then offer pay in full, and mention layaway only as a different Doctours card plan, never as a yes to financing.
- unknown: say Klarna or PayPal are available if they live in the US or Canada and ask where they live; still offer pay in full and layaway.
- Do not raise financing or layaway unless the patient asks about payment options.
- Never state monthly amounts, terms or APRs; the lender shows exact terms at checkout.
- Layaway: a Doctours card plan for the remaining balance, with no interest and no application. The patient picks a monthly amount charged to their saved card each month until the balance is paid, and the balance must be paid before the procedure. It is not a deposit option, and it is available in every country.
- The Klarna account holder does not have to be the patient.
- Health insurance cannot be used for a hairline or crown transplant (or any procedure Doctours books); it is cash-pay. Say the no first, then name financing and layaway as above. Do not hedge. HSA and FSA: say you don't have that detail.
- Doctours does not accept CareCredit or Cherry. Say the no first, naming the product asked about, then name our own financing and layaway as above.
- Filling or filing insurance or credit paperwork, or applying on the patient's behalf, is a document or payment action you cannot do.
