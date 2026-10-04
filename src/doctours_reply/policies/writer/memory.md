+++
id = "writer.memory"
version = "1.0.0"
layer = "writer"
summary = "What goes into workingMemoryUpdates"
sources = ["packet:L1471-L1505", "packet:L1414", "packet:L1551-L1554"]
+++
# Working memory

workingMemoryUpdates holds only the memory fields this message changed, or null when nothing changed. Fields: patientName, procedureArea, targetProcedureWindow, communicationStyle, keyConcerns, promisesMade, preferredPaymentMethod, collectionState. The current memory is in the context; do not repeat unchanged values.

- Store stable facts the patient just shared: their name, the area they want treated, a relative window such as "in the next 3 months", how they write, what worries them, how they want to pay.
- promisesMade records a check-in you set this turn.
- Never store dates, months or seasons for the procedure; those are saved as tentative dates by the clinic preferences tool, not in memory.
- Never store card details, clinic or package selections, or prices.
- Do not set escalationFlags.
