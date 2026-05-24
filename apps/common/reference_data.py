from apps.auth.errors import AuthError
from apps.reference_data.models import RefValue


def get_ref_value(domain_code: str, value_code: str) -> RefValue:
    try:
        return RefValue.objects.get(domain__domain_code=domain_code, value_code=value_code)
    except RefValue.DoesNotExist as exc:
        raise AuthError(
            "REFERENCE_VALUE_NOT_FOUND",
            f"Unknown reference value {domain_code}:{value_code}.",
            400,
        ) from exc
