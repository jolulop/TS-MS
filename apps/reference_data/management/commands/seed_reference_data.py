from django.core.management.base import BaseCommand
from django.db import transaction

from apps.reference_data.models import RefDomain, RefValue
from apps.reference_data.seeds import REFERENCE_DATA


class Command(BaseCommand):
    help = "Load mandatory TS system reference data."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        created_domains = 0
        updated_domains = 0
        created_values = 0
        updated_values = 0

        for domain_code, domain_data in REFERENCE_DATA.items():
            domain, created = RefDomain.objects.update_or_create(
                domain_code=domain_code,
                defaults={
                    "name": domain_data["name"],
                    "description": domain_data.get("description", ""),
                    "active_flag": domain_data.get("active_flag", True),
                },
            )
            if created:
                created_domains += 1
            else:
                updated_domains += 1

            for value in domain_data["values"]:
                _, created = RefValue.objects.update_or_create(
                    domain=domain,
                    value_code=value["code"],
                    defaults={
                        "value_label": value["label"],
                        "description": value.get("description", ""),
                        "sort_order": value.get("sort_order", 0),
                        "active_flag": value.get("active_flag", True),
                        "system_flag": value.get("system_flag", True),
                    },
                )
                if created:
                    created_values += 1
                    self.stdout.write(self.style.SUCCESS(f"Created {domain_code}:{value['code']}"))
                else:
                    updated_values += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Reference data seed completed "
                f"for {created_domains + updated_domains} domains and "
                f"{created_values + updated_values} values "
                f"with {updated_domains + updated_values} updates."
            )
        )
