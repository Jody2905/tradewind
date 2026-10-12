from django.core.management.base import BaseCommand

from shop.services import expire_unpaid_orders


class Command(BaseCommand):
    help = "Cancel orders that weren't paid by their deadline and put their stock back. Run once a day."

    def handle(self, *args, **options):
        expired = expire_unpaid_orders()
        for order in expired:
            self.stdout.write(f"Cancelled {order.number} (unpaid since {order.placed_at:%d %b})")
        self.stdout.write(self.style.SUCCESS(f"{len(expired)} unpaid order(s) cancelled."))
