# account/forms.py

from django import forms
from .models import Transaction, Account, TransactionPreset, Budget
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm as AuthPasswordChangeForm

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ("first_name",)

class TransactionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(TransactionForm, self).__init__(*args, **kwargs)
        if user:
            self.fields['debit_account'].queryset = Account.objects.filter(owner=user)
            self.fields['credit_account'].queryset = Account.objects.filter(owner=user)

    class Meta:
        model = Transaction
        # ▼▼▼▼▼ [수정됨] 'is_repayment' 필드를 명시적으로 포함 ▼▼▼▼▼
        fields = ['date', 'item', 'memo', 'amount', 'debit_account', 'credit_account', 'is_repayment']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'is_repayment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_repayment': '이 거래를 부채상환으로 처리합니다.'
        }

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        labels = {
            'username': '사용자 이름',
            'first_name': '이름',
            'last_name': '성',
            'email': '이메일',
        }
        help_texts = {
            'username': '사용자 이름은 고유해야 합니다.',
        }

class PasswordChangeForm(AuthPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = '현재 비밀번호'
        self.fields['new_password1'].label = '새 비밀번호'
        self.fields['new_password2'].label = '새 비밀번호 확인'

class AccountForm(forms.ModelForm):
    ACCOUNT_TYPE_CHOICES = [
        ('자산', '자산'),
        ('부채', '부채'),
        ('수익', '수익'),
        ('비용', '비용'),
        ('순자산', '순자산'),
    ]

    type = forms.ChoiceField(
        choices=ACCOUNT_TYPE_CHOICES,
        label="계정 타입",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Account
        fields = ['type', 'name', 'category']
        labels = {
            'name': '항목명',
            'category': '계정 유형',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        account_type = cleaned_data.get("type")
        category = cleaned_data.get("category")

        if not (account_type and category):
            return cleaned_data

        if account_type == '순자산' and category != 'GENERAL':
            self.add_error('category', "순자산 타입은 '일반' 유형만 선택할 수 있습니다.")
        
        elif account_type == '자산' and category not in ['GENERAL', 'VARIABLE', 'SAVING']:
             self.add_error('category', "'자산' 타입은 '일반', '유동', '저축' 유형만 선택할 수 있습니다.")

        elif account_type == '부채' and category not in ['GENERAL', 'VARIABLE']:
             self.add_error('category', "'부채' 타입은 '일반', '유동' 유형만 선택할 수 있습니다.")

        elif account_type in ['수익', '비용'] and category not in ['FIXED', 'VARIABLE']:
            self.add_error('category', f"'{account_type}' 타입은 '고정' 또는 '유동' 유형만 선택할 수 있습니다.")

        return cleaned_data

class TransactionPresetForm(forms.ModelForm):
    class Meta:
        model = TransactionPreset
        # ▼▼▼▼▼ [수정됨] FieldError를 해결하기 위해 올바른 필드명으로 수정 ▼▼▼▼▼
        fields = ['name', 'preset_type', 'item', 'amount', 'debit_account', 'credit_account', 'day_of_month']
        # ▲▲▲▲▲ 여기까지 수정 ▲▲▲▲▲
        labels = {
            'name': '프리셋 이름',
            'preset_type': '프리셋 타입',
            'item': '아이템',
            'amount': '금액',
            'debit_account': '차변 계정',
            'credit_account': '대변 계정',
            'day_of_month': '고정 일자 (고정항목 시)',
        }
        widgets = {
            'preset_type': forms.Select(attrs={'class': 'form-select'}),
            'item': forms.TextInput(attrs={'class': 'form-input'}),
            'amount': forms.NumberInput(attrs={'class': 'form-input'}),
            'day_of_month': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '1-31 (고정항목만 해당)'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['debit_account'].queryset = Account.objects.filter(owner=user)
            self.fields['credit_account'].queryset = Account.objects.filter(owner=user)
        
        if self.instance and self.instance.preset_type == 'FREQUENT':
            self.fields['amount'].required = False
            self.fields['day_of_month'].required = False
        elif self.initial.get('preset_type') == 'FREQUENT':
            self.fields['amount'].required = False
            self.fields['day_of_month'].required = False

    def clean(self):
        cleaned_data = super().clean()
        preset_type = cleaned_data.get('preset_type')
        amount = cleaned_data.get('amount')
        day_of_month = cleaned_data.get('day_of_month')

        if preset_type == 'FIXED':
            if amount is None:
                self.add_error('amount', '고정항목은 금액을 필수로 입력해야 합니다.')
            if day_of_month is None:
                self.add_error('day_of_month', '고정항목은 고정 일자를 필수로 입력해야 합니다.')
            elif not (1 <= day_of_month <= 31):
                self.add_error('day_of_month', '고정 일자는 1에서 31 사이의 숫자여야 합니다.')
        elif preset_type == 'FREQUENT':
            pass
        return cleaned_data

class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        # ▼▼▼▼▼ [수정됨] ImproperlyConfigured 오류를 해결하기 위해 fields 추가 ▼▼▼▼▼
        fields = ['account', 'amount']
        labels = {
            'account': '비용 계정',
            'amount': '예산 금액',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['account'].queryset = Account.objects.filter(owner=user, type='비용')
