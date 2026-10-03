"""Python port of the packet's tool functions (packet L321-671).

Each function returns exactly what its TypeScript original returns for the same
arguments, reading tables and canned results from `ToolData`. Arguments are read the
way the TypeScript reads them: unknown keys are ignored and `None` behaves like
`undefined`. Argument validation belongs to the registry. Results are deep copies, so
callers cannot change the fixture.
"""

import copy
from collections.abc import Callable, Mapping
from typing import Any

from doctours_reply.tools.data import Record, ToolData

Args = Mapping[str, Any]

# String.prototype.trim strips ECMAScript WhiteSpace and LineTerminator code points,
# which differ from Python's str.isspace (e.g. U+FEFF is stripped, U+0085 is not).
_JS_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009"
    "\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def find_clinic(data: ToolData, args: Args) -> Record | None:
    clinic_id = args.get("clinicId")
    if clinic_id:
        return next((clinic for clinic in data.clinics if clinic["id"] == clinic_id), None)
    clinic_name = args.get("clinicName")
    name = clinic_name.strip(_JS_WHITESPACE).lower() if clinic_name is not None else ""
    if not name:
        return None
    matchers: tuple[Callable[[str], bool], ...] = (
        lambda candidate: candidate == name,
        lambda candidate: name in candidate,
        lambda candidate: candidate in name,
    )
    for matches in matchers:
        found = next((c for c in data.clinics if matches(c["name"].lower())), None)
        if found is not None:
            return found
    return None


def get_all_clinics(data: ToolData, args: Args) -> Record:
    return copy.deepcopy({"clinics": data.clinics})


def get_clinic_doctors(data: ToolData, args: Args) -> Record | None:
    clinic = find_clinic(data, args)
    if clinic is None:
        return None
    return copy.deepcopy(
        {
            "clinicId": clinic["id"],
            "clinicName": clinic["name"],
            "doctors": [d for d in data.doctors if d["clinicId"] == clinic["id"]],
        }
    )


def get_clinic_packages(data: ToolData, args: Args) -> Record | None:
    clinic = find_clinic(data, args)
    if clinic is None:
        return None
    return copy.deepcopy(
        {
            "clinicName": clinic["name"],
            "clinic_flags": clinic["clinic_flags"],
            "currency": "USD",
            "packages": [p for p in data.packages if p["clinicId"] == clinic["id"]],
        }
    )


def get_consultation_reschedule_link(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.consultation_reschedule_link)


def get_full_calls(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.full_calls)


def get_latest_assessment(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.latest_assessment)


def get_patient_context(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.patient_context)


def get_patient_images(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.patient_images)


def get_payment_link(data: ToolData, args: Args) -> Record | None:
    link_type = args.get("type")
    package_id = args.get("clinicPackageId")
    pkg = next((p for p in data.packages if p["id"] == package_id), None)
    if link_type == "payment" and pkg is not None:
        clinic = next((c for c in data.clinics if c["id"] == pkg["clinicId"]), None)
        return copy.deepcopy(
            {
                "clinicId": pkg["clinicId"],
                "clinicName": clinic["name"] if clinic is not None else None,
                "clinicPackageId": pkg["id"],
                "clinicPackageName": pkg["name"],
                "linkType": "payment",
                "reason": None,
                "status": "ready",
                "url": f"https://www.doctours.com/payment/{pkg['id']}",
            }
        )
    if link_type == "checkout":
        clinic_id = args.get("clinicId")
        clinic = next((c for c in data.clinics if c["id"] == clinic_id), None)
        if clinic is None:
            return None
        return copy.deepcopy(
            {
                "clinicId": clinic["id"],
                "clinicName": clinic["name"],
                "clinicPackageId": None,
                "clinicPackageName": None,
                "linkType": "checkout",
                "reason": None,
                "status": "ready",
                "url": f"https://www.doctours.com/clinic/{clinic['slug']}/checkout",
            }
        )
    if link_type == "payment":
        return {
            "clinicId": None,
            "clinicName": None,
            "clinicPackageId": None,
            "clinicPackageName": None,
            "linkType": "payment",
            "reason": "missing_or_malformed_clinic_package_id",
            "status": "missing_input",
            "url": None,
        }
    return None


def get_saved_clinics(data: ToolData, args: Args) -> Record:
    saved = data.saved_clinics
    return copy.deepcopy(
        {
            "count": saved.count,
            "recommendationStatus": saved.recommendationStatus,
            "savedClinics": [
                {"clinic": clinic, "clinicId": clinic["id"], "id": saved.ids[i], "ranking": i + 1}
                for i, clinic in enumerate(data.clinics)
            ],
        }
    )


def issue_promo_code(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.promo_code)


def update_user(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.update_user)


def update_user_clinic_preferences(data: ToolData, args: Args) -> Record | None:
    selection = args.get("clinicSelection")
    if not isinstance(selection, Mapping):
        selection = {}
    selected_clinic_id = selection.get("selectedClinicId")
    selected_package_id = selection.get("selectedPackageId")
    clinic_ok = selected_clinic_id is None or any(
        c["id"] == selected_clinic_id for c in data.clinics
    )
    package_ok = selected_package_id is None or any(
        p["id"] == selected_package_id for p in data.packages
    )
    if not clinic_ok or not package_ok:
        return None
    preferences = data.clinic_preferences
    return copy.deepcopy(
        {
            "clinicSelection": {
                "budgetMax": None,
                "excludedDestinations": [],
                "preferredDestinations": [],
                "selectedClinicId": selected_clinic_id,
                "selectedPackageId": selected_package_id,
                "softClinicInterestIds": [],
                "softPackageInterestIds": [],
            },
            "dropped": [],
            "lockedReason": None,
            "tentativeProcedureDates": preferences.tentativeProcedureDates,
            "updated": True,
            "userId": preferences.userId,
        }
    )


def update_working_memory(data: ToolData, args: Args) -> Record:
    return copy.deepcopy(data.update_working_memory)
