# account/views.py

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, TransactionForm, UserProfileForm, PasswordChangeForm, AccountForm, TransactionPresetForm, BudgetForm
from django.contrib.auth.forms import AuthenticationForm
from django.urls import reverse
from django.contrib import messages
from .models import Account, Transaction, TransactionPreset, Budget
from datetime import date, datetime
from django.utils.dateparse import parse_date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.db.models import Sum, F, Window, Q
from django.db.models.functions import Coalesce
from django.db import transaction

# --- 인증 관련 뷰 ---

def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            Account.objects.create(owner=user, type='순자산', name='기초잔액', category='GENERAL')
            Account.objects.create(owner=user, type='자산', name='현금', category='VARIABLE')
            Account.objects.create(owner=user, type='자산', name='적금', category='SAVING')
            Account.objects.create(owner=user, type='부채', name='신용카드', category='VARIABLE')
            Account.objects.create(owner=user, type='수익', name='급여', category='FIXED')
            Account.objects.create(owner=user, type='비용', name='식비', category='VARIABLE')

            messages.success(request, '회원가입이 완료되었고, 기본 계정 항목들이 생성되었습니다!')
            return redirect('account:transaction_list')
    else:
        form = CustomUserCreationForm()
    return render(request, 'account/signup.html', {'form': form})

def index_view(request):
    if request.user.is_authenticated:
        return redirect('account:transaction_create')
    else:
        return redirect('account:login')

def login_view(request):
    if request.user.is_authenticated:
        return redirect('account:transaction_create')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if request.POST.get('remember_me'):
                request.session.set_expiry(1209600) 
            else:
                request.session.set_expiry(0) 
            return redirect('account:transaction_create')
    else:
        form = AuthenticationForm()
    return render(request, 'account/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('account:login')

# --- 핵심 기능 뷰 ---

@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(owner=request.user).select_related('debit_account', 'credit_account')
    
    today = date.today()
    q_account = request.GET.get('account', '')
    q_debit = request.GET.get('debit_account', '')
    q_credit = request.GET.get('credit_account', '')
    q_item = request.GET.get('item', '')
    q_memo = request.GET.get('memo', '')
    q_start = request.GET.get('start_date', '')
    q_end = request.GET.get('end_date', '')
    q_year = request.GET.get('year', '')
    q_month = request.GET.get('month', '')

    if q_year and q_month:
        try:
            year, month = int(q_year), int(q_month)
            start_date_obj = date(year, month, 1)
            end_date_obj = start_date_obj + relativedelta(months=1) - relativedelta(days=1)
        except (ValueError, TypeError):
            start_date_obj = today.replace(day=1)
            end_date_obj = start_date_obj + relativedelta(months=1) - relativedelta(days=1)
    elif q_start and q_end:
        start_date_obj = date.fromisoformat(q_start)
        end_date_obj = date.fromisoformat(q_end)
    else:
        start_date_obj = today - relativedelta(months=1)
        end_date_obj = today

    transactions = transactions.filter(date__range=[start_date_obj, end_date_obj])

    if q_debit:
        transactions = transactions.filter(debit_account_id=q_debit)
    if q_credit:
        transactions = transactions.filter(credit_account_id=q_credit)
    if q_account:
        transactions = transactions.filter(
            Q(debit_account_id=q_account) | Q(credit_account_id=q_account)
        )
    if q_item:
        transactions = transactions.filter(item__icontains=q_item)
    if q_memo:
        transactions = transactions.filter(memo__icontains=q_memo)
    
    transactions = transactions.order_by('-date', '-created_at')
    
    period_total = transactions.aggregate(total=Sum('amount'))['total'] or Decimal(0)

    cumulative_total = None
    selected_account = None
    account_id_for_cumulative = q_account or q_debit or q_credit
    
    if account_id_for_cumulative:
        try:
            selected_account = Account.objects.get(id=account_id_for_cumulative, owner=request.user)
            if selected_account.type in ['자산', '부채']:
                initial_debits = Transaction.objects.filter(owner=request.user, debit_account=selected_account, date__lt=start_date_obj).aggregate(sum=Sum('amount'))['sum'] or Decimal(0)
                initial_credits = Transaction.objects.filter(owner=request.user, credit_account=selected_account, date__lt=start_date_obj).aggregate(sum=Sum('amount'))['sum'] or Decimal(0)
                
                if selected_account.type == '자산':
                    balance = initial_debits - initial_credits
                else:
                    balance = initial_credits - initial_debits

                temp_transactions = list(transactions.order_by('date', 'created_at'))
                for tx in temp_transactions:
                    if tx.debit_account == selected_account:
                        balance += tx.amount if selected_account.type == '자산' else -tx.amount
                    elif tx.credit_account == selected_account:
                        balance -= tx.amount if selected_account.type == '자산' else -tx.amount
                    tx.balance = balance
                
                transactions = sorted(temp_transactions, key=lambda x: (x.date, x.created_at), reverse=True)
                cumulative_total = balance
        except Account.DoesNotExist:
            pass

    all_accounts = Account.objects.filter(owner=request.user)
    years = range(2020, today.year + 2)
    months = range(1, 13)
    
    context = {
        'transactions': transactions,
        'all_accounts': all_accounts,
        'period_total': period_total,
        'cumulative_total': cumulative_total,
        'selected_account_name': selected_account.name if selected_account else None,
        'years': years,
        'months': months,
        'filters': {
            'account': q_account,
            'debit_account': q_debit, 
            'credit_account': q_credit,
            'item': q_item, 
            'memo': q_memo, 
            'start_date': start_date_obj.strftime('%Y-%m-%d'),
            'end_date': end_date_obj.strftime('%Y-%m-%d'),
            'year': int(q_year) if q_year else start_date_obj.year,
            'month': int(q_month) if q_month else start_date_obj.month,
        }
    }
    return render(request, 'account/transaction_list.html', context)

@login_required
def transaction_create(request):
    if request.method == 'POST':
        is_repayment = request.POST.get('is_repayment') == 'on'
        date_str = request.POST.get('date')
        item = request.POST.get('item')
        memo = request.POST.get('memo')
        amount = Decimal(request.POST.get('amount'))
        debit_account_id = request.POST.get('debit_account')
        credit_account_id = request.POST.get('credit_account')

        debit_account = get_object_or_404(Account, id=debit_account_id, owner=request.user)
        credit_account = get_object_or_404(Account, id=credit_account_id, owner=request.user)
        start_date = parse_date(date_str)
        
        if '//' in item:
            parts = item.split('//')
            if len(parts) == 2:
                item_name = parts[0].strip()
                try:
                    months = int(parts[1])
                    monthly_amount = round(amount / months)

                    for i in range(months):
                        transaction_date = start_date + relativedelta(months=i)
                        Transaction.objects.create(
                            owner=request.user,
                            date=transaction_date, item=item_name,
                            memo=f"{item_name} ({i+1}/{months}회차)", amount=monthly_amount,
                            debit_account=debit_account, credit_account=credit_account,
                            is_repayment=is_repayment
                        )
                    messages.success(request, f'{months}개월 할부 거래가 성공적으로 입력되었습니다!')
                except (ValueError, ZeroDivisionError):
                    messages.error(request, "할부 개월수가 잘못되었습니다. '아이템//숫자' 형식으로 입력해주세요.")
                    return redirect(reverse('account:transaction_create'))
            else:
                messages.error(request, "할부 형식이 잘못되었습니다. '아이템//숫자' 형식으로 입력해주세요.")
                return redirect(reverse('account:transaction_create'))
        else:
            Transaction.objects.create(
                owner=request.user,
                date=start_date, item=item, memo=memo, amount=amount,
                debit_account=debit_account, credit_account=credit_account,
                is_repayment=is_repayment
            )
            if credit_account.name == '체크카드':
                try:
                    cash_account = Account.objects.get(owner=request.user, name='현금')
                    Transaction.objects.create(
                        owner=request.user,
                        date=start_date, item=item, memo="체크카드 자동출금", amount=amount,
                        debit_account=credit_account,
                        credit_account=cash_account
                    )
                except Account.DoesNotExist:
                    messages.warning(request, "'현금' 계정이 없어 체크카드 자동출금 거래를 생성하지 못했습니다.")
            
            messages.success(request, '거래가 성공적으로 입력되었습니다!')

        return redirect(reverse('account:transaction_create'))

    debit_accounts = {}
    credit_accounts = {}
    
    for acc in Account.objects.filter(owner=request.user).exclude(type='수익').order_by('name'):
        if acc.type not in debit_accounts: debit_accounts[acc.type] = []
        debit_accounts[acc.type].append(acc)

    for acc in Account.objects.filter(owner=request.user).exclude(type='비용').order_by('name'):
        if acc.type not in credit_accounts: credit_accounts[acc.type] = []
        credit_accounts[acc.type].append(acc)

    fixed_presets = TransactionPreset.objects.filter(owner=request.user, preset_type='FIXED').order_by('day_of_month', 'name')
    frequent_presets = TransactionPreset.objects.filter(owner=request.user, preset_type='FREQUENT').order_by('name')
    recent_transactions = Transaction.objects.filter(owner=request.user).select_related('debit_account', 'credit_account').order_by('-created_at')[:20]

    context = {
        'debit_accounts': debit_accounts, 'credit_accounts': credit_accounts,
        'today': date.today(), 'fixed_presets': fixed_presets,
        'frequent_presets': frequent_presets, 'recent_transactions': recent_transactions,
    }
    return render(request, 'account/transaction_form.html', context)

@login_required
def transaction_update(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, owner=request.user)
    next_url = request.GET.get('next', reverse('account:transaction_list'))

    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=transaction, user=request.user)
        if form.is_valid():
            form.save()
            return redirect(next_url)
    else:
        form = TransactionForm(instance=transaction, user=request.user)
    
    debit_accounts = {}
    credit_accounts = {}
    for acc in Account.objects.filter(owner=request.user).exclude(type='수익').order_by('name'):
        if acc.type not in debit_accounts: debit_accounts[acc.type] = []
        debit_accounts[acc.type].append(acc)
    for acc in Account.objects.filter(owner=request.user).exclude(type='비용').order_by('name'):
        if acc.type not in credit_accounts: credit_accounts[acc.type] = []
        credit_accounts[acc.type].append(acc)
    
    context = {
        'form': form, 'transaction': transaction, 'next': next_url,
        'debit_accounts': debit_accounts, 'credit_accounts': credit_accounts,
    }
    return render(request, 'account/transaction_update_form.html', context)

@login_required
def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, owner=request.user)
    next_url = request.GET.get('next', reverse('account:transaction_list'))
    if request.method == 'POST':
        transaction.delete()
        return redirect(next_url)
    return render(request, 'account/transaction_confirm_delete.html', {'transaction': transaction, 'next': next_url})


@login_required
def asset_status(request):
    today = date.today()
    selected_year = int(request.GET.get('year', today.year))
    selected_month = int(request.GET.get('month', today.month))
    
    # --- 월별 현황 계산 ---
    monthly_transactions = Transaction.objects.filter(
        owner=request.user,
        date__year=selected_year,
        date__month=selected_month
    )
    monthly_income = monthly_transactions.filter(credit_account__type='수익').aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    monthly_expense = monthly_transactions.filter(debit_account__type='비용').aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    monthly_savings = monthly_transactions.filter(
        debit_account__type='자산', debit_account__category='SAVING'
    ).aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    monthly_repayments = monthly_transactions.filter(is_repayment=True).aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    monthly_net_profit = monthly_income - monthly_expense
    available_cash = monthly_net_profit - monthly_savings - monthly_repayments

    # --- 자산/부채 잔액 계산 ---
    accounts = Account.objects.filter(owner=request.user)
    
    all_debits = {
        item['debit_account_id']: item['total'] for item in
        Transaction.objects.filter(owner=request.user).values('debit_account_id').annotate(total=Sum('amount'))
    }
    all_credits = {
        item['credit_account_id']: item['total'] for item in
        Transaction.objects.filter(owner=request.user).values('credit_account_id').annotate(total=Sum('amount'))
    }
    
    current_debits = {
        item['debit_account_id']: item['total'] for item in
        Transaction.objects.filter(owner=request.user, date__lte=today).values('debit_account_id').annotate(total=Sum('amount'))
    }
    current_credits = {
        item['credit_account_id']: item['total'] for item in
        Transaction.objects.filter(owner=request.user, date__lte=today).values('credit_account_id').annotate(total=Sum('amount'))
    }

    for acc in accounts:
        total_debit = all_debits.get(acc.id, Decimal(0))
        total_credit = all_credits.get(acc.id, Decimal(0))
        current_debit = current_debits.get(acc.id, Decimal(0))
        current_credit = current_credits.get(acc.id, Decimal(0))

        if acc.type in ['자산', '비용']:
            acc.current_balance = current_debit - current_credit
            acc.total_balance = total_debit - total_credit
        else:
            acc.current_balance = current_credit - current_debit
            acc.total_balance = total_credit - total_debit

    assets = [acc for acc in accounts if acc.type == '자산' and acc.category != 'SAVING']
    savings = [acc for acc in accounts if acc.type == '자산' and acc.category == 'SAVING']
    liabilities = [acc for acc in accounts if acc.type == '부채']
    
    current_total_assets = sum(acc.current_balance for acc in assets)
    current_total_savings = sum(acc.current_balance for acc in savings)
    current_total_liabilities = sum(acc.current_balance for acc in liabilities)
    current_net_worth = current_total_assets + current_total_savings - current_total_liabilities

    total_assets = sum(acc.total_balance for acc in assets)
    total_savings = sum(acc.total_balance for acc in savings)
    total_liabilities = sum(acc.total_balance for acc in liabilities)
    net_worth = total_assets + total_savings - total_liabilities

    all_balances = [abs(acc.current_balance) for acc in assets + savings + liabilities]
    max_graph_value = max(all_balances) if all_balances else 1
    
    context = {
        'assets': assets, 'savings': savings, 'liabilities': liabilities,
        'current_total_assets': current_total_assets,
        'current_total_savings': current_total_savings,
        'current_total_liabilities': current_total_liabilities,
        'current_net_worth': current_net_worth,
        'total_assets': total_assets,
        'total_savings': total_savings,
        'total_liabilities': total_liabilities,
        'net_worth': net_worth,
        'max_graph_value': max_graph_value,
        'selected_year': selected_year, 'selected_month': selected_month,
        'monthly_income': monthly_income, 'monthly_expense': monthly_expense,
        'monthly_savings': monthly_savings, 'monthly_repayments': monthly_repayments,
        'monthly_net_profit': monthly_net_profit,
        'available_cash': available_cash,
        'years': range(2020, today.year + 2
                       ), 'months': range(1, 13),
    }

    chart_data = {
        'labels': [],
        'net_worth_data': [],
    }

    # --- 기간 설정 로직 수정: 최근 1년 (현재 월 포함) ---
    today = date.today()
    # 루프 종료일은 이번 달의 오늘 날짜
    end_date = today 
    # 루프 시작일은 11개월 전의 1일 (오늘이 8월이면 작년 9월 1일부터 시작)
    start_date = (today - relativedelta(months=11)).replace(day=1)

    # 설정된 기간 내에 거래가 있는 경우에만 차트 데이터 생성
    if Transaction.objects.filter(owner=request.user, date__gte=start_date).exists():
        current_date = start_date
        
        # start_date부터 end_date까지 월별로 순회
        while current_date <= end_date:
            # 해당 월의 마지막 날짜 계산
            month_end_date = current_date + relativedelta(months=1) - relativedelta(days=1)
            # 단, 루프의 마지막 달에는 오늘 날짜를 기준으로 계산
            if current_date.year == end_date.year and current_date.month == end_date.month:
                month_end_date = end_date

            # 해당 월말까지의 자산/부채 계산
            asset_accounts = Account.objects.filter(owner=request.user, type='자산')
            liabilities_accounts = Account.objects.filter(owner=request.user, type='부채')

            total_assets_at_month_end = 0
            for acc in asset_accounts:
                debits = Transaction.objects.filter(owner=request.user, debit_account=acc, date__lte=month_end_date).aggregate(sum=Coalesce(Sum('amount'), Decimal(0)))['sum']
                credits = Transaction.objects.filter(owner=request.user, credit_account=acc, date__lte=month_end_date).aggregate(sum=Coalesce(Sum('amount'), Decimal(0)))['sum']
                total_assets_at_month_end += debits - credits

            total_liabilities_at_month_end = 0
            for acc in liabilities_accounts:
                debits = Transaction.objects.filter(owner=request.user, debit_account=acc, date__lte=month_end_date).aggregate(sum=Coalesce(Sum('amount'), Decimal(0)))['sum']
                credits = Transaction.objects.filter(owner=request.user, credit_account=acc, date__lte=month_end_date).aggregate(sum=Coalesce(Sum('amount'), Decimal(0)))['sum']
                total_liabilities_at_month_end += credits - debits

            net_worth_at_month_end = total_assets_at_month_end - total_liabilities_at_month_end
            
            chart_data['labels'].append(current_date.strftime('%Y-%m'))
            chart_data['net_worth_data'].append(float(net_worth_at_month_end))
            
            # 다음 달로 이동
            current_date += relativedelta(months=1)

    # context에 chart_data_json 추가 (이 부분은 그대로 유지)
    context['chart_data_json'] = json.dumps(chart_data)
    # --- ▲▲▲▲▲ 여기까지 코드 추가 ▲▲▲▲▲ ---


    return render(request, 'account/asset_status.html', context)

@login_required
def budget_view(request):
    today = date.today()
    try:
        selected_year = int(request.GET.get('year', today.year))
        selected_month = int(request.GET.get('month', today.month))
        target_date = date(selected_year, selected_month, 1)
    except (ValueError, TypeError):
        target_date = today
        selected_year = today.year
        selected_month = today.month

    start_of_month = target_date.replace(day=1)
    end_of_month = start_of_month + relativedelta(months=1) - relativedelta(days=1)

    income_transactions = Transaction.objects.filter(
        owner=request.user, date__range=[start_of_month, end_of_month], credit_account__type='수익'
    )
    expense_transactions = Transaction.objects.filter(
        owner=request.user, date__range=[start_of_month, end_of_month], debit_account__type='비용'
    )

    income_actuals = {
        item['credit_account__name']: item['total']
        for item in income_transactions.values('credit_account__name').annotate(total=Sum('amount'))
    }
    expense_actuals = {
        item['debit_account__name']: item['total']
        for item in expense_transactions.values('debit_account__name').annotate(total=Sum('amount'))
    }

    all_income_accounts = Account.objects.filter(owner=request.user, type='수익')
    all_expense_accounts = Account.objects.filter(owner=request.user, type='비용')

    fixed_income_details = []
    other_income_total = 0
    for acc in all_income_accounts:
        actual = income_actuals.get(acc.name, 0)
        if acc.category == 'FIXED':
            fixed_income_details.append({'name': acc.name, 'actual': actual})
        else:
            other_income_total += actual

    fixed_expense_details = []
    other_expense_total = 0
    for acc in all_expense_accounts:
        actual = expense_actuals.get(acc.name, 0)
        if acc.category == 'FIXED':
            fixed_expense_details.append({'name': acc.name, 'actual': actual})
        else:
            other_expense_total += actual

    total_income = sum(item['actual'] for item in fixed_income_details) + other_income_total
    total_expense = sum(item['actual'] for item in fixed_expense_details) + other_expense_total

    context = {
        'year': selected_year,
        'month': selected_month,
        'years': range(2020, today.year + 2),
        'months': range(1, 13),
        'fixed_income_details': fixed_income_details,
        'other_income_total': other_income_total,
        'fixed_expense_details': fixed_expense_details,
        'other_expense_total': other_expense_total,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_total': total_income - total_expense,
    }
    return render(request, 'account/budget_view.html', context)

@login_required
def settings_view(request):
    user_profile_form = UserProfileForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)
    account_form = AccountForm()
    preset_form = TransactionPresetForm(user=request.user)

    if request.method == 'POST':
        if 'update_profile' in request.POST:
            user_profile_form = UserProfileForm(request.POST, instance=request.user)
            if user_profile_form.is_valid():
                user_profile_form.save()
                messages.success(request, '사용자 정보가 업데이트되었습니다.')
                return redirect(reverse('account:settings') + '#profile-section')

        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, '비밀번호가 변경되었습니다.')
                return redirect(reverse('account:settings') + '#password-section')

        elif 'add_account' in request.POST:
            account_form = AccountForm(request.POST)
            if account_form.is_valid():
                account = account_form.save(commit=False)
                account.owner = request.user
                account.save()
                messages.success(request, '새로운 회계 계정이 추가되었습니다.')
                return redirect(reverse('account:settings') + '#account-section')

        elif 'add_preset' in request.POST:
            preset_form = TransactionPresetForm(request.POST, user=request.user)
            if preset_form.is_valid():
                preset = preset_form.save(commit=False)
                preset.owner = request.user
                preset.save()
                messages.success(request, '새로운 거래 프리셋이 추가되었습니다.')
                return redirect(reverse('account:settings') + '#preset-section')

    user_accounts = Account.objects.filter(owner=request.user).order_by('type', 'name')
    user_presets = TransactionPreset.objects.filter(owner=request.user).order_by('preset_type', 'name')

    context = {
        'user_profile_form': user_profile_form,
        'password_form': password_form,
        'account_form': account_form,
        'preset_form': preset_form,
        'user_accounts': user_accounts,
        'user_presets': user_presets,
    }
    return render(request, 'account/settings.html', context)

@login_required
def preset_update(request, pk):
    preset = get_object_or_404(TransactionPreset, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = TransactionPresetForm(request.POST, instance=preset, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, '프리셋이 성공적으로 수정되었습니다.')
            return redirect(reverse('account:settings') + '#preset-section')
    else:
        form = TransactionPresetForm(instance=preset, user=request.user)
    return render(request, 'account/preset_form_update.html', {'form': form})

@login_required
def preset_delete(request, pk):
    preset = get_object_or_404(TransactionPreset, pk=pk, owner=request.user)
    if request.method == 'POST':
        preset.delete()
        messages.success(request, '프리셋이 삭제되었습니다.')
        return redirect(reverse('account:settings') + '#preset-section')
    return render(request, 'account/confirm_delete.html', {'object': preset})

@login_required
def account_update(request, pk):
    account = get_object_or_404(Account, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, '계정 항목이 성공적으로 수정되었습니다.')
            return redirect(reverse('account:settings') + '#account-section')
    else:
        form = AccountForm(instance=account)
    return render(request, 'account/account_form_update.html', {'form': form})

@login_required
def account_delete(request, pk):
    account = get_object_or_404(Account, pk=pk, owner=request.user)
    if request.method == 'POST':
        account.delete()
        messages.success(request, '계정 항목이 삭제되었습니다.')
        return redirect(reverse('account:settings') + '#account-section')
    return render(request, 'account/confirm_delete.html', {'object': account})


@login_required
def reports_view(request):
    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year = today.year
        month = today.month

    # '전달 예산 가져오기' 버튼 처리
    if 'copy_last_month_budget' in request.POST:
        # 1. 이전 달 날짜 계산
        current_month_start = date(year, month, 1)
        last_month_end = current_month_start - relativedelta(days=1)
        last_month_year = last_month_end.year
        last_month_month = last_month_end.month
        
        # 2. 이전 달 예산 조회
        last_month_budgets = Budget.objects.filter(
            owner=request.user,
            year=last_month_year,
            month=last_month_month
        )

        if last_month_budgets.exists():
            # 3. 현재 달 예산을 모두 지우고, 이전 달 예산을 새로 생성 (원자적 트랜잭션)
            with transaction.atomic():
                Budget.objects.filter(owner=request.user, year=year, month=month).delete()
                new_budgets = []
                for budget in last_month_budgets:
                    new_budgets.append(
                        Budget(
                            owner=request.user,
                            year=year,
                            month=month,
                            account=budget.account,
                            amount=budget.amount
                        )
                    )
                Budget.objects.bulk_create(new_budgets)
            messages.success(request, f'{last_month_year}년 {last_month_month}월의 예산을 성공적으로 복사했습니다.')
        else:
            messages.info(request, '복사할 전달 예산 데이터가 없습니다.')
        
        return redirect(reverse('account:reports') + f'?year={year}&month={month}')


    if request.method == 'POST':
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget, created = Budget.objects.update_or_create(
                owner=request.user,
                year=year,
                month=month,
                account=form.cleaned_data['account'],
                defaults={'amount': form.cleaned_data['amount']}
            )
            messages.success(request, '예산이 저장되었습니다.')
            return redirect(reverse('account:reports') + f'?year={year}&month={month}')
    else:
        form = BudgetForm(user=request.user)

    # --- 데이터 준비 (이전과 동일) ---
    all_expense_accounts = Account.objects.filter(owner=request.user, type='비용').order_by('name')
    fixed_expense_accounts = all_expense_accounts.filter(category='FIXED')
    
    monthly_spending_query = Transaction.objects.filter(
        owner=request.user, date__year=year, date__month=month, debit_account__type='비용'
    ).values('debit_account__name').annotate(total_spent=Sum('amount'))
    
    spending_dict = {item['debit_account__name']: item['total_spent'] for item in monthly_spending_query}

    budgets = Budget.objects.filter(owner=request.user, year=year, month=month)
    budget_dict = {b.account.name: b.amount for b in budgets}

    # --- 고정 비용 세부 내역 만들기 (이전과 동일) ---
    fixed_expense_details = []
    for account in fixed_expense_accounts:
        spent = spending_dict.get(account.name, Decimal(0))
        fixed_expense_details.append({
            'debit_account__name': account.name,
            'total_spent': spent,
        })
    fixed_expenses_total = sum(item['total_spent'] for item in fixed_expense_details)
    for item in fixed_expense_details:
        item['percentage'] = int((item['total_spent'] / fixed_expenses_total) * 100) if fixed_expenses_total > 0 else 0
    fixed_expense_details.sort(key=lambda x: x['total_spent'], reverse=True)

    # --- 전체 리포트 데이터 만들기 (이전과 동일) ---
    report_data = []
    for account in all_expense_accounts:
        account_name = account.name
        spent = spending_dict.get(account_name, Decimal(0))
        budget = budget_dict.get(account_name, Decimal(0))
        usage_percent = int((spent / budget * 100)) if budget > 0 else 0
        report_data.append({
            'name': account_name, 'spent': spent, 'budget': budget, 'usage_percent': usage_percent,
        })

    # --- 월별 예산 합계 계산 (추가된 부분) ---
    total_budget = sum(budget_dict.values())
    
    context = {
        'year': year,
        'month': month,
        'report_data': report_data,
        'fixed_expenses_total': fixed_expenses_total,
        'fixed_expense_details': fixed_expense_details,
        'total_budget': total_budget,  # <-- 템플릿에 전달할 예산 합계
        'years': range(today.year - 3, today.year + 2),
        'months': range(1, 13),
        'form': form,
    }
    return render(request, 'account/reports.html', context)