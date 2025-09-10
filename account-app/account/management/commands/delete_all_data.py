from django.core.management.base import BaseCommand
from account.models import Transaction, Account

class Command(BaseCommand):
    help = 'Deletes all transaction and account data.'

    def handle(self, *args, **options):
        # 외래 키 제약 조건 때문에 Transaction을 먼저 삭제해야 합니다.
        t_deleted, _ = Transaction.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {t_deleted} transactions.'))

        a_deleted, _ = Account.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {a_deleted} accounts.'))

        self.stdout.write(self.style.WARNING('All data has been cleared.'))