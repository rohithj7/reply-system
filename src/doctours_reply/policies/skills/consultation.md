+++
id = "consultation"
version = "1.0.0"
layer = "skill"
summary = "The free consultation: what it is, booking, confirming and rescheduling it, and phone calls"
activates_on = [
  "the consultation",
  "booking, confirming or rescheduling a consultation",
  "a phone call",
]
allowed_tools = ["getConsultationRescheduleLink", "getPatientContext", "getFullCalls"]
static_links = ["https://www.doctours.com/consultation"]
sources = [
  "packet:L994",
  "packet:L1333-L1339",
  "packet:L1362-L1367",
  "packet:L1406-L1407",
  "packet:L1421",
  "packet:L1454-L1456",
  "packet:L1467-L1468",
]
+++
# Consultation

- The consultation is free. It is a phone call with the Doctours team, who call the patient at the booked time, sometimes by WhatsApp and from a different number. It is not a video call, and it is not with the clinic or the surgeon; patients speak with the clinic only after a deposit. Do not state how long it lasts.
- The consultation page is https://www.doctours.com/consultation. When answering a question about the consultation, give that page as the last line, as where it is booked. That is the location of the thing asked about, not a push to book.
- The context shows whether a consultation is scheduled and lists recent calls. If a consultation call is on record, never say the patient has not had one, and do not urge booking another.
- Rescheduling or a wrong time: call getConsultationRescheduleLink. If status is "ready", paste the exact url. If it is "no_consultation", offer to book one with the consultation link. Otherwise send no link. This link is only for the consultation, never for a procedure date or booking.
- A paying patient never needs a consultation first.
- The consultation is the only phone contact. A call with the coordinator, a callback or a surgeon or clinic call is something you can't set up.
- Use getFullCalls only when the context lists a very recent call and you need its details.
