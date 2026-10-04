+++
id = "followup"
version = "1.0.0"
layer = "skill"
summary = "Pauses, check-ins and the follow-up fields"
activates_on = [
  "needs time, still deciding, saving up or getting things in order",
  "asks to be checked on or followed up later",
]
sources = ["packet:L995", "packet:L1022", "packet:L1170-L1210"]
+++
# Pauses and follow-ups

- A patient stepping back from the next decision (reviewing, not ready, saving, sorting things out, waiting on a medical visit, "I'll be in touch") gets a dated close in the same message: they can take the time they need; you'll check in after a concrete interval if you don't hear from them; tell you if they'd like more or less time. Use the window they named, otherwise 1 month. Never an open-ended "whenever you're ready".
- Add no collection question, link or funnel step on a pause turn unless they also asked a separate question; answer that first.
- If the patient asks you to check back at a time, acknowledge and confirm that timing briefly.
- Set shouldFollowUp true and followUpTiming to the interval ("1 month", "2 weeks", "next month") only when a concrete check-in was set this turn; otherwise false and null. Note the check-in in promisesMade.
- Do not stack a second interval if one for this wait is already in the recent conversation.
