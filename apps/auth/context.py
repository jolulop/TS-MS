from dataclasses import dataclass


@dataclass(frozen=True)
class ScopedBusinessUnit:
    id: int
    bu_code: str
    name: str


@dataclass(frozen=True)
class CurrentUser:
    employee_id: int
    employee_code: str
    full_name: str
    email: str
    canonical_email: str
    primary_business_unit_id: int
    primary_business_unit_code: str
    role_codes: tuple[str, ...]
    scoped_business_units: tuple[ScopedBusinessUnit, ...]

    @property
    def scoped_business_unit_ids(self) -> tuple[int, ...]:
        return tuple(unit.id for unit in self.scoped_business_units)

    @property
    def is_ts_admin(self) -> bool:
        return "TS_ADMIN" in self.role_codes

    def has_role(self, role_code: str) -> bool:
        return role_code in self.role_codes
