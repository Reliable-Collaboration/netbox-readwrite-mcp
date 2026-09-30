"""Write normalization qualified against NetBox 4.7.2 DeviceSerializer.

description/serial use DRF CharField(trim_whitespace=True); status is a ChoiceField.
Keep raw input separately for audit and idempotency. Never normalize a pre-image
silently: existing noncanonical values cannot be restored exactly through REST.
"""


def canonical_changes(changes):
    return {
        key: value.strip() if key in {"description", "serial"} else value for key, value in changes.items()
    }


def exact_inverse(operation):
    return {
        key: value
        for key, value in operation["before_values"].items()
        if value != operation["after_values"][key]
    }


def exact_correction(original, correction):
    return correction["after_values"] == exact_inverse(original)
