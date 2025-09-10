# account/management/commands/import_data.py

import csv
from django.core.management.base import BaseCommand
from account.models import Account, Transaction
from django.contrib.auth.models import User
from decimal import Decimal, InvalidOperation

class Command(BaseCommand):
    help = '특정 사용자의 계정으로 CSV 파일의 금융 데이터를 가져옵니다.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='데이터를 추가할 사용자의 아이디')

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"'{username}' 사용자가 존재하지 않습니다."))
            return

        # --- 1. 계정 정보(_계정목록.csv) 가져오기 ---
        try:
            with open('_계정목록.csv', 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    Account.objects.get_or_create(
                        owner=user,
                        type=row['계정'],
                        name=row['계좌명']
                    )
            self.stdout.write(self.style.SUCCESS('계정 목록을 성공적으로 가져왔습니다.'))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('_계정목록.csv 파일을 찾을 수 없습니다. manage.py와 같은 위치에 파일을 두세요.'))
            return

        # --- 2. 거래 내역(_거래내역.csv) 가져오기 ---
        transactions_to_create = []
        try:
            with open('_거래내역.csv', 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    try:
                        amount_str = row.get('금액', '0').replace('₩', '').replace(',', '').strip()

                        if not amount_str:
                            amount_val = Decimal('0')
                        else:
                            amount_val = Decimal(amount_str)

                        debit_account = Account.objects.get(owner=user, name=row['차변계정명'])
                        credit_account = Account.objects.get(owner=user, name=row['대변계정명'])

                        date_parts = [p.strip() for p in row['거래일'].replace('.', '').split()]
                        formatted_date = f"{date_parts[0]}-{int(date_parts[1]):02d}-{int(date_parts[2]):02d}"

                        transaction = Transaction(
                            owner=user,
                            date=formatted_date,
                            item=row['항목'],
                            memo=row['메모'],
                            amount=amount_val,
                            debit_account=debit_account,
                            credit_account=credit_account
                        )
                        transactions_to_create.append(transaction)

                    except Account.DoesNotExist as e:
                        self.stdout.write(self.style.ERROR(f"'{e}' 계정을 찾을 수 없습니다. 건너뜁니다: {row}"))
                    except (InvalidOperation, IndexError, ValueError):
                        self.stdout.write(self.style.WARNING(f"데이터 형식 오류. 건너뜁니다: {row}"))

            Transaction.objects.bulk_create(transactions_to_create)
            self.stdout.write(self.style.SUCCESS(f'거래 내역 {len(transactions_to_create)}건을 성공적으로 가져왔습니다.'))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('_거래내역.csv 파일을 찾을 수 없습니다. manage.py와 같은 위치에 파일을 두세요.'))