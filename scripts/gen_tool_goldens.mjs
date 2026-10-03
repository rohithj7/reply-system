// Regenerate the tool goldens by running the verbatim TypeScript tools over a fixed argument matrix.
//
// Usage (Node 22.6+, for type stripping):
//   node --experimental-strip-types scripts/gen_tool_goldens.mjs          # write the goldens
//   node --experimental-strip-types scripts/gen_tool_goldens.mjs --check  # fail if they changed
//
// Development only. CI checks the Python port against the committed goldens without Node.

import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = join(ROOT, "tests/conformance/reference/packet_tools.ts");
const GOLDENS = join(ROOT, "tests/conformance/goldens/packet_tools.json");

const FUNCTIONS = [
  "findClinic",
  "getAllClinics",
  "getClinicDoctors",
  "getClinicPackages",
  "getConsultationRescheduleLink",
  "getFullCalls",
  "getLatestAssessment",
  "getPatientContext",
  "getPatientImages",
  "getPaymentLink",
  "getSavedClinics",
  "issuePromoCode",
  "updateUser",
  "updateUserClinicPreferences",
  "updateWorkingMemory",
];

const HEVA = "11111111-1111-4111-8111-111111111111";
const HAKAN = "22222222-2222-4222-8222-222222222222";
const SILVER = "44444444-4444-4444-8444-444444444441";
const GOLD = "44444444-4444-4444-8444-444444444442";
const SAPPHIRE = "55555555-5555-4555-8555-555555555551";
const USER = "7c2e1a40-6b8f-4d3a-9e15-2f0a8b6c4d11";

const CLINIC_NAMES = [
  "Heva Clinic",
  "heva clinic",
  "HEVA CLINIC",
  "  Heva Clinic  ",
  "\tDr. Hakan Clinic\n",
  "Dr. Hakan Clinic",
  "Heva",
  "heva",
  "Hakan",
  "dr. hakan",
  "Clinic",
  "I want Heva Clinic please",
  "Dr Hakan",
  "unknown clinic",
  "",
  "   ",
  "\uFEFFHeva",
  "\u00A0Heva\u00A0",
  "\u3000Hakan\u2028",
  "\u0085Heva",
  "\u001CHeva",
  "\u200BHeva",
];

const CLINIC_INPUTS = [
  {},
  { clinicId: HEVA },
  { clinicId: HAKAN },
  { clinicId: "33333333-3333-4333-8333-333333333333" },
  { clinicId: "" },
  { clinicId: "", clinicName: "Heva" },
  { clinicId: HEVA, clinicName: "Dr. Hakan Clinic" },
  { clinicId: "not-a-clinic", clinicName: "Heva Clinic" },
  { clinicId: null, clinicName: "Hakan" },
  { clinicName: null },
  ...CLINIC_NAMES.map((clinicName) => ({ clinicName })),
  { clinicName: "Heva", unknownKey: "ignored" },
];

const USER_INPUTS = [{}, { userId: USER }, { userId: "someone-else" }, { unknownKey: 1 }];

const MATRIX = {
  findClinic: CLINIC_INPUTS,
  getAllClinics: [null, {}, { unknownKey: 1 }],
  getClinicDoctors: CLINIC_INPUTS,
  getClinicPackages: CLINIC_INPUTS,
  getConsultationRescheduleLink: USER_INPUTS,
  getFullCalls: [{}, { chatId: "chat-1", limit: 0 }, { limit: 5 }, { unknownKey: 1 }],
  getLatestAssessment: USER_INPUTS,
  getPatientContext: USER_INPUTS,
  getPatientImages: USER_INPUTS,
  getPaymentLink: [
    {},
    { type: "payment", clinicPackageId: SILVER },
    { type: "payment", clinicPackageId: GOLD },
    { type: "payment", clinicPackageId: SAPPHIRE },
    { type: "payment", clinicPackageId: SILVER, clinicId: HAKAN },
    { type: "payment", clinicPackageId: "not-a-package" },
    { type: "payment" },
    { type: "payment", clinicPackageId: null },
    { type: "checkout", clinicId: HEVA },
    { type: "checkout", clinicId: HAKAN },
    { type: "checkout", clinicId: "not-a-clinic" },
    { type: "checkout" },
    { type: "checkout", clinicPackageId: SILVER },
    { type: "Payment", clinicPackageId: SILVER },
    { type: "deposit", clinicPackageId: SILVER },
    { type: null, clinicPackageId: SILVER },
    { clinicPackageId: SILVER },
    { type: "payment", clinicPackageId: GOLD, unknownKey: true },
  ],
  getSavedClinics: USER_INPUTS,
  issuePromoCode: USER_INPUTS,
  updateUser: [
    {},
    { firstName: "Jordan", lastName: "Hale" },
    { firstName: "Sam", userId: "someone-else" },
    { unknownKey: 1 },
  ],
  updateUserClinicPreferences: [
    {},
    { clinicSelection: {} },
    { clinicSelection: null },
    { clinicSelection: { selectedClinicId: HEVA } },
    { clinicSelection: { selectedPackageId: GOLD } },
    { clinicSelection: { selectedClinicId: HEVA, selectedPackageId: GOLD } },
    { clinicSelection: { selectedClinicId: HAKAN, selectedPackageId: SILVER } },
    { clinicSelection: { selectedClinicId: "not-a-clinic" } },
    { clinicSelection: { selectedPackageId: "not-a-package" } },
    { clinicSelection: { selectedClinicId: HEVA, selectedPackageId: "not-a-package" } },
    { clinicSelection: { selectedClinicId: null, selectedPackageId: null } },
    { clinicSelection: { selectedClinicId: "" } },
    { clinicSelection: { selectedClinicId: 123 } },
    { clinicSelection: { selectedClinicId: HEVA, tentativeProcedureDates: { text: "May" } } },
    { userId: "someone-else", clinicSelection: { selectedPackageId: SAPPHIRE } },
  ],
  updateWorkingMemory: [{}, { memory: {} }, { memory: { patientName: "Jordan" } }],
};

async function loadTools(source) {
  const dir = mkdtempSync(join(tmpdir(), "packet-tools-"));
  try {
    const modulePath = join(dir, "packet_tools.mts");
    writeFileSync(modulePath, `${source}\nexport { ${FUNCTIONS.join(", ")} };\n`);
    return await import(pathToFileURL(modulePath).href);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function serialize(value) {
  const text = JSON.stringify(value, null, 2);
  return `${text.replace(/[\u007f-\uffff]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`)}\n`;
}

const source = readFileSync(SOURCE, "utf8");
const tools = await loadTools(source);
const cases = FUNCTIONS.flatMap((fn) =>
  MATRIX[fn].map((args) => ({
    function: fn,
    args,
    result: (args === null ? tools[fn]() : tools[fn](structuredClone(args))) ?? null,
  })),
);
const goldens = {
  generator: "scripts/gen_tool_goldens.mjs",
  node: process.version,
  source_sha256: createHash("sha256").update(source).digest("hex"),
  cases: JSON.parse(JSON.stringify(cases)),
};

if (process.argv.includes("--check")) {
  const committed = JSON.parse(readFileSync(GOLDENS, "utf8"));
  const same =
    committed.source_sha256 === goldens.source_sha256 &&
    isDeepStrictEqual(committed.cases, goldens.cases);
  console.log(
    same
      ? `goldens unchanged: ${cases.length} cases (generated with node ${committed.node}, checked with node ${process.version})`
      : "goldens differ from the TypeScript reference; regenerate and review the diff",
  );
  process.exit(same ? 0 : 1);
}
writeFileSync(GOLDENS, serialize(goldens));
console.log(`wrote ${cases.length} cases with node ${process.version}`);
