# account/models.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

class Account(models.Model):
    TYPE_CHOICES = [
        ('자산', '자산'),
        ('부채', '부채'),
        ('순자산', '순자산'),
        ('수익', '수익'),
        ('비용', '비용'),
    ]
    
    ACCOUNT_CATEGORY_CHOICES = [
        ('FIXED', '고정'),
        ('VARIABLE', '유동'),
        ('SAVING', '저축'),
        ('GENERAL', '일반'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=10,
        choices=ACCOUNT_CATEGORY_CHOICES,
        default='GENERAL',
        verbose_name='계정 유형'
    )

    def __str__(self):
        return f"{self.name} ({self.type})"

    class Meta:
        unique_together = ('owner', 'name')    

class Transaction(models.Model):
    date = models.DateField(default=timezone.now, verbose_name="날짜")
    item = models.CharField(max_length=100, verbose_name="아이템")
    memo = models.CharField(max_length=200, blank=True, null=True, verbose_name="메모")
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="금액")
    
    debit_account = models.ForeignKey(Account, related_name='debits', on_delete=models.PROTECT, verbose_name="차변 계정")
    credit_account = models.ForeignKey(Account, related_name='credits', on_delete=models.PROTECT, verbose_name="대변 계정")
    
    is_repayment = models.BooleanField(default=False, verbose_name="부채상환 거래")

    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="소유자")

    class Meta:
        # ▼▼▼▼▼ [수정됨] 기본 정렬 순서를 날짜 내림차순, 생성일 내림차순으로 지정 ▼▼▼▼▼
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} | {self.item} | {self.amount}"
   
class TransactionPreset(models.Model):
    PRESET_TYPES = [
        ('FIXED', '고정항목'),
        ('FREQUENT', '자주입력'),
    ]

    name = models.CharField(max_length=100, verbose_name="프리셋 이름")
    preset_type = models.CharField(max_length=10, choices=PRESET_TYPES, verbose_name="프리셋 타입")
    
    item = models.CharField(max_length=100, verbose_name="아이템")
    amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True, verbose_name="금액 (자주입력은 비워둘 수 있음)")
    debit_account = models.ForeignKey(Account, related_name='debit_presets', on_delete=models.CASCADE, verbose_name="차변 계정")
    credit_account = models.ForeignKey(Account, related_name='credit_presets', on_delete=models.CASCADE, verbose_name="대변 계정")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="소유자")
    
    day_of_month = models.IntegerField(null=True, blank=True, verbose_name="고정 일자 (예: 25)")

    def __str__(self):
        return f"[{self.get_preset_type_display()}] {self.name}"   

class Budget(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="소유자")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, limit_choices_to={'type': '비용'}, verbose_name="비용 계정")
    year = models.IntegerField(verbose_name="연도")
    month = models.IntegerField(verbose_name="월")
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="예산 금액")

    class Meta:
        unique_together = ('owner', 'year', 'month', 'account')

    def __str__(self):
        return f"{self.year}년 {self.month}월 - {self.account.name}: {self.amount}"
