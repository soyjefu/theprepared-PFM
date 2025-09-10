from django.contrib import admin
from .models import Account, Transaction, TransactionPreset, Budget

# Account 모델을 관리자 페이지에서 볼 수 있도록 등록합니다.
@admin.register(Account)
class AccountAdmin(admin.ModelAdmin): # ModelAdmin을 admin.ModelAdmin으로 수정
    list_display = ('name', 'type')
    list_filter = ('type',)
    search_fields = ('name',)

# Transaction 모델도 등록합니다.
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin): # ModelAdmin을 admin.ModelAdmin으로 수정
    list_display = ('date', 'item', 'amount', 'debit_account', 'credit_account')
    list_filter = ('date',)
    search_fields = ('item', 'memo')

@admin.register(TransactionPreset)
class TransactionPresetAdmin(admin.ModelAdmin):
    list_display = ('name', 'preset_type', 'item', 'amount', 'day_of_month')
    list_filter = ('preset_type',)
    search_fields = ('name', 'item')

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('owner', 'year', 'month', 'account', 'amount')
    list_filter = ('owner', 'year', 'month')