from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from account.models import Account, TransactionPreset

class TransactionPresetTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.debit = Account.objects.create(owner=self.user, type='비용', name='식비', category='FIXED')
        self.credit = Account.objects.create(owner=self.user, type='자산', name='보통예금', category='GENERAL')
        self.client = Client()
        self.client.login(username='testuser', password='password123')

    def test_create_fixed_preset_success(self):
        url = reverse('account:settings')
        data = {
            'add_preset': '1',
            'name': '월세 고정지출',
            'preset_type': 'FIXED',
            'item': '월세',
            'amount': '500000',
            'day_of_month': '25',
            'debit_account': str(self.debit.id),
            'credit_account': str(self.credit.id),
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TransactionPreset.objects.filter(owner=self.user, name='월세 고정지출').exists())

    def test_create_fixed_preset_missing_day_of_month_fails(self):
        url = reverse('account:settings')
        data = {
            'add_preset': '1',
            'name': '잘못된 고정지출',
            'preset_type': 'FIXED',
            'item': '월세',
            'amount': '500000',
            'day_of_month': '',
            'debit_account': str(self.debit.id),
            'credit_account': str(self.credit.id),
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TransactionPreset.objects.filter(owner=self.user, name='잘못된 고정지출').exists())
        self.assertContains(response, '고정항목은 고정 일자를 필수로 입력해야 합니다.')
