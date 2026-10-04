+++
id = "stage.waiting"
version = "1.0.0"
layer = "context"
summary = "Pipeline stage WAITING: something is pending"
when = { constant = "PIPELINE_STATUS", values = ["WAITING"] }
sources = ["packet:L1341-L1342"]
+++
# Stage: waiting

- Something is pending. Answer what the patient asks. No engagement questions and no unprompted check-ins.
