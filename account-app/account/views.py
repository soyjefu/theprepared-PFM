# account/views.py

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .forms import (
    CustomUserCreationForm,
    TransactionForm,
    UserProfileForm,
    PasswordChangeForm,
    AccountForm,
    TransactionPresetForm,
    BudgetForm,
)
from django.contrib.auth.forms import AuthenticationForm
from django.urls import reverse
from django.contrib import messages
from .models import Account, Transaction, TransactionPreset, Budget
from datetime import date, timedelta
from django.utils.dateparse import parse_date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.db import transaction

# --- 인증 관련 뷰 ---


def signup_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)

            Account.objects.create(
                owner=user, type="순자산", name="기초잔액", category="GENERAL"
            )
            Account.objects.create(
                owner=user, type="자산", name="현금", category="VARIABLE"
            )
            Account.objects.create(
                owner=user, type="자산", name="적금", category="SAVING"
            )
            Account.objects.create(
                owner=user, type="부채", name="신용카드", category="VARIABLE"
            )
            Account.objects.create(
                owner=user, type="수익", name="급여", category="FIXED"
            )
            Account.objects.create(
                owner=user, type="비용", name="식비", category="VARIABLE"
            )

            messages.success(
                request, "회원가입이 완료되었고, 기본 계정 항목들이 생성되었습니다!"
            )
            return redirect("account:transaction_list")
    else:
        form = CustomUserCreationForm()
    return render(request, "account/signup.html", {"form": form})


def index_view(request):
    if request.user.is_authenticated:
        return redirect("account:transaction_create")
    else:
        return redirect("account:login")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("account:transaction_create")
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if request.POST.get("remember_me"):
                request.session.set_expiry(1209600)
            else:
                request.session.set_expiry(0)
            return redirect("account:transaction_create")
    else:
        form = AuthenticationForm()
    return render(request, "account/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("account:login")


# --- 핵심 기능 뷰 ---


@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(owner=request.user).select_related(
        "debit_account", "credit_account"
    )

    today = date.today()
    q_account = request.GET.get("account", "")
    q_debit = request.GET.get("debit_account", "")
    q_credit = request.GET.get("credit_account", "")
    q_item = request.GET.get("item", "")
    q_memo = request.GET.get("memo", "")
    q_start = request.GET.get("start_date", "")
    q_end = request.GET.get("end_date", "")
    q_year = request.GET.get("year", "")
    q_month = request.GET.get("month", "")

    if q_year and q_month:
        try:
            year, month = int(q_year), int(q_month)
            start_date_obj = date(year, month, 1)
            end_date_obj = (
                start_date_obj + relativedelta(months=1) - relativedelta(days=1)
            )
        except (ValueError, TypeError):
            start_date_obj = today.replace(day=1)
            end_date_obj = (
                start_date_obj + relativedelta(months=1) - relativedelta(days=1)
            )
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

    transactions = transactions.order_by("-date", "-created_at")

    period_total = transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)

    cumulative_total = None
    selected_account = None
    account_id_for_cumulative = q_account or q_debit or q_credit

    if account_id_for_cumulative:
        try:
            selected_account = Account.objects.get(
                id=account_id_for_cumulative, owner=request.user
            )
            if selected_account.type in ["자산", "부채"]:
                initial_debits = Transaction.objects.filter(
                    owner=request.user,
                    debit_account=selected_account,
                    date__lt=start_date_obj,
                ).aggregate(sum=Sum("amount"))["sum"] or Decimal(0)
                initial_credits = Transaction.objects.filter(
                    owner=request.user,
                    credit_account=selected_account,
                    date__lt=start_date_obj,
                ).aggregate(sum=Sum("amount"))["sum"] or Decimal(0)

                if selected_account.type == "자산":
                    balance = initial_debits - initial_credits
                else:
                    balance = initial_credits - initial_debits

                temp_transactions = list(transactions.order_by("date", "created_at"))
                for tx in temp_transactions:
                    if tx.debit_account == selected_account:
                        balance += (
                            tx.amount if selected_account.type == "자산" else -tx.amount
                        )
                    elif tx.credit_account == selected_account:
                        balance -= (
                            tx.amount if selected_account.type == "자산" else -tx.amount
                        )
                    tx.balance = balance

                transactions = sorted(
                    temp_transactions,
                    key=lambda x: (x.date, x.created_at),
                    reverse=True,
                )
                cumulative_total = balance
        except Account.DoesNotExist:
            pass

    all_accounts = Account.objects.filter(owner=request.user).order_by("type", "name")
    years = range(2020, today.year + 2)
    months = range(1, 13)

    context = {
        "transactions": transactions,
        "all_accounts": all_accounts,
        "period_total": period_total,
        "cumulative_total": cumulative_total,
        "selected_account_name": selected_account.name if selected_account else None,
        "years": years,
        "months": months,
        "filters": {
            "account": q_account,
            "debit_account": q_debit,
            "credit_account": q_credit,
            "item": q_item,
            "memo": q_memo,
            "start_date": start_date_obj.strftime("%Y-%m-%d"),
            "end_date": end_date_obj.strftime("%Y-%m-%d"),
            "year": int(q_year) if q_year else start_date_obj.year,
            "month": int(q_month) if q_month else start_date_obj.month,
        },
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    is_history_restore = request.headers.get("HX-History-Restore-Request") == "true"
    if is_htmx and not is_history_restore:
        return render(request, "account/partials/transaction_table.html", context)

    return render(request, "account/transaction_list.html", context)


@login_required
def transaction_create(request):
    if request.method == "POST":
        is_repayment = request.POST.get("is_repayment") == "on"
        date_str = request.POST.get("date")
        item = request.POST.get("item")
        memo = request.POST.get("memo")
        amount = Decimal(request.POST.get("amount"))
        debit_account_id = request.POST.get("debit_account")
        credit_account_id = request.POST.get("credit_account")

        debit_account = get_object_or_404(
            Account, id=debit_account_id, owner=request.user
        )
        credit_account = get_object_or_404(
            Account, id=credit_account_id, owner=request.user
        )
        start_date = parse_date(date_str)

        if "//" in item:
            parts = item.split("//")
            if len(parts) == 2:
                item_name = parts[0].strip()
                try:
                    months = int(parts[1])
                    monthly_amount = round(amount / months)

                    for i in range(months):
                        transaction_date = start_date + relativedelta(months=i)
                        Transaction.objects.create(
                            owner=request.user,
                            date=transaction_date,
                            item=item_name,
                            memo=f"{item_name} ({i + 1}/{months}회차)",
                            amount=monthly_amount,
                            debit_account=debit_account,
                            credit_account=credit_account,
                            is_repayment=is_repayment,
                        )
                    messages.success(
                        request, f"{months}개월 할부 거래가 성공적으로 입력되었습니다!"
                    )
                except (ValueError, ZeroDivisionError):
                    messages.error(
                        request,
                        "할부 개월수가 잘못되었습니다. '아이템//숫자' 형식으로 입력해주세요.",
                    )
                    return redirect(reverse("account:transaction_create"))
            else:
                messages.error(
                    request,
                    "할부 형식이 잘못되었습니다. '아이템//숫자' 형식으로 입력해주세요.",
                )
                return redirect(reverse("account:transaction_create"))
        else:
            Transaction.objects.create(
                owner=request.user,
                date=start_date,
                item=item,
                memo=memo,
                amount=amount,
                debit_account=debit_account,
                credit_account=credit_account,
                is_repayment=is_repayment,
            )
            if credit_account.name == "체크카드":
                try:
                    cash_account = Account.objects.get(owner=request.user, name="현금")
                    Transaction.objects.create(
                        owner=request.user,
                        date=start_date,
                        item=item,
                        memo="체크카드 자동출금",
                        amount=amount,
                        debit_account=credit_account,
                        credit_account=cash_account,
                    )
                except Account.DoesNotExist:
                    messages.warning(
                        request,
                        "'현금' 계정이 없어 체크카드 자동출금 거래를 생성하지 못했습니다.",
                    )

            messages.success(request, "거래가 성공적으로 입력되었습니다!")

        return redirect(reverse("account:transaction_create"))

    debit_accounts = {}
    credit_accounts = {}

    for acc in (
        Account.objects.filter(owner=request.user, is_active=True)
        .exclude(type="수익")
        .order_by("name")
    ):
        if acc.type not in debit_accounts:
            debit_accounts[acc.type] = []
        debit_accounts[acc.type].append(acc)

    for acc in (
        Account.objects.filter(owner=request.user, is_active=True)
        .exclude(type="비용")
        .order_by("name")
    ):
        if acc.type not in credit_accounts:
            credit_accounts[acc.type] = []
        credit_accounts[acc.type].append(acc)

    fixed_presets = TransactionPreset.objects.filter(
        owner=request.user, preset_type="FIXED"
    ).order_by("day_of_month", "name")
    frequent_presets = TransactionPreset.objects.filter(
        owner=request.user, preset_type="FREQUENT"
    ).order_by("name")
    recent_transactions = (
        Transaction.objects.filter(owner=request.user)
        .select_related("debit_account", "credit_account")
        .order_by("-created_at")[:20]
    )

    context = {
        "debit_accounts": debit_accounts,
        "credit_accounts": credit_accounts,
        "today": date.today(),
        "fixed_presets": fixed_presets,
        "frequent_presets": frequent_presets,
        "recent_transactions": recent_transactions,
    }
    return render(request, "account/transaction_form.html", context)


@login_required
def transaction_update(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, owner=request.user)
    next_url = request.GET.get("next", reverse("account:transaction_list"))

    if request.method == "POST":
        form = TransactionForm(request.POST, instance=transaction, user=request.user)
        if form.is_valid():
            form.save()
            return redirect(next_url)
    else:
        form = TransactionForm(instance=transaction, user=request.user)

    debit_accounts = {}
    credit_accounts = {}

    # 활성 계정 + 현재 선택된 계정(비활성이어도 포함)
    d_q = Q(is_active=True) | Q(id=transaction.debit_account_id)
    c_q = Q(is_active=True) | Q(id=transaction.credit_account_id)

    for acc in (
        Account.objects.filter(owner=request.user)
        .filter(d_q)
        .exclude(type="수익")
        .order_by("name")
    ):
        if acc.type not in debit_accounts:
            debit_accounts[acc.type] = []
        debit_accounts[acc.type].append(acc)
    for acc in (
        Account.objects.filter(owner=request.user)
        .filter(c_q)
        .exclude(type="비용")
        .order_by("name")
    ):
        if acc.type not in credit_accounts:
            credit_accounts[acc.type] = []
        credit_accounts[acc.type].append(acc)

    context = {
        "form": form,
        "transaction": transaction,
        "next": next_url,
        "debit_accounts": debit_accounts,
        "credit_accounts": credit_accounts,
    }
    return render(request, "account/transaction_update_form.html", context)


@login_required
def transaction_inline_update(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, owner=request.user)
    field = request.GET.get("field")

    if request.method == "POST":
        value = request.POST.get(field)
        if field == "amount":
            try:
                transaction.amount = Decimal(value.replace(",", ""))
            except (ValueError, TypeError, Decimal.InvalidOperation):
                pass
        elif field in ["debit_account", "credit_account"]:
            acc = get_object_or_404(Account, id=value, owner=request.user)
            setattr(transaction, field, acc)
        else:
            setattr(transaction, field, value)
        transaction.save()

        context = {"tx": transaction, "field": field}
        return render(request, "account/partials/inline_field.html", context)

    # 수정용 입력 폼 리턴
    value = getattr(transaction, field)
    context = {"tx": transaction, "field": field, "value": value}

    if field in ["debit_account", "credit_account"]:
        # 계정 선택을 위한 그룹화된 목록 준비
        accounts_grouped = {}
        exclude_type = "수익" if field == "debit_account" else "비용"

        # 활성 계정 + 현재 선택된 계정(비활성이어도 포함)
        current_acc_id = (
            getattr(transaction, field).id if getattr(transaction, field) else None
        )
        q_filter = Q(is_active=True)
        if current_acc_id:
            q_filter |= Q(id=current_acc_id)

        relevant_accounts = (
            Account.objects.filter(owner=request.user)
            .filter(q_filter)
            .order_by("type", "name")
        )

        for acc in relevant_accounts.exclude(type=exclude_type):
            if acc.type not in accounts_grouped:
                accounts_grouped[acc.type] = []
            accounts_grouped[acc.type].append(acc)
        context["accounts_grouped"] = accounts_grouped
        context["selected_id"] = value.id if value else None

    return render(request, "account/partials/inline_form.html", context)


@login_required
def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, owner=request.user)
    next_url = request.GET.get("next", reverse("account:transaction_list"))
    if request.method == "POST":
        transaction.delete()
        return redirect(next_url)
    return render(
        request,
        "account/transaction_confirm_delete.html",
        {"transaction": transaction, "next": next_url},
    )


@login_required
def asset_status(request):
    today = date.today()
    selected_year = int(request.GET.get("year", today.year))
    selected_month = int(request.GET.get("month", today.month))

    # --- 차트 기간 옵션 (Phase 3.1) ---
    range_value = request.GET.get("range", "12")
    range_options = [
        {"value": "3", "label": "3M"},
        {"value": "6", "label": "6M"},
        {"value": "12", "label": "1Y"},
        {"value": "24", "label": "2Y"},
        {"value": "all", "label": "전체"},
    ]
    qs = request.GET.copy()
    qs.pop("range", None)
    qs_without_range = qs.urlencode()

    # --- 월별 현황 계산 ---
    monthly_transactions = Transaction.objects.filter(
        owner=request.user, date__year=selected_year, date__month=selected_month
    )
    monthly_income = monthly_transactions.filter(credit_account__type="수익").aggregate(
        total=Coalesce(Sum("amount"), Decimal(0))
    )["total"]
    monthly_expense = monthly_transactions.filter(debit_account__type="비용").aggregate(
        total=Coalesce(Sum("amount"), Decimal(0))
    )["total"]

    # --- 순 저축액 계산 (저축 입금액 - 저축 출금액) ---
    saving_in = monthly_transactions.filter(
        debit_account__type="자산", debit_account__category="SAVING"
    ).aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]

    saving_out = monthly_transactions.filter(
        credit_account__type="자산", credit_account__category="SAVING"
    ).aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]

    monthly_savings = saving_in - saving_out

    monthly_repayments = monthly_transactions.filter(is_repayment=True).aggregate(
        total=Coalesce(Sum("amount"), Decimal(0))
    )["total"]
    monthly_net_profit = monthly_income - monthly_expense
    available_cash = monthly_net_profit - monthly_savings - monthly_repayments

    # --- 자산/부채 잔액 계산 ---
    accounts = Account.objects.filter(owner=request.user, is_active=True)

    all_debits = {
        item["debit_account_id"]: item["total"]
        for item in Transaction.objects.filter(owner=request.user)
        .values("debit_account_id")
        .annotate(total=Sum("amount"))
    }
    all_credits = {
        item["credit_account_id"]: item["total"]
        for item in Transaction.objects.filter(owner=request.user)
        .values("credit_account_id")
        .annotate(total=Sum("amount"))
    }

    current_debits = {
        item["debit_account_id"]: item["total"]
        for item in Transaction.objects.filter(owner=request.user, date__lte=today)
        .values("debit_account_id")
        .annotate(total=Sum("amount"))
    }
    current_credits = {
        item["credit_account_id"]: item["total"]
        for item in Transaction.objects.filter(owner=request.user, date__lte=today)
        .values("credit_account_id")
        .annotate(total=Sum("amount"))
    }

    # Phase 3.2: 전월말 기준 잔액 (전월 대비 변동 계산용)
    last_month_end = today.replace(day=1) - timedelta(days=1)
    prev_debits = {
        item["debit_account_id"]: item["total"]
        for item in Transaction.objects.filter(
            owner=request.user, date__lte=last_month_end
        )
        .values("debit_account_id")
        .annotate(total=Sum("amount"))
    }
    prev_credits = {
        item["credit_account_id"]: item["total"]
        for item in Transaction.objects.filter(
            owner=request.user, date__lte=last_month_end
        )
        .values("credit_account_id")
        .annotate(total=Sum("amount"))
    }

    for acc in accounts:
        total_debit = all_debits.get(acc.id, Decimal(0))
        total_credit = all_credits.get(acc.id, Decimal(0))
        current_debit = current_debits.get(acc.id, Decimal(0))
        current_credit = current_credits.get(acc.id, Decimal(0))
        prev_debit = prev_debits.get(acc.id, Decimal(0))
        prev_credit = prev_credits.get(acc.id, Decimal(0))

        if acc.type in ["자산", "비용"]:
            acc.current_balance = current_debit - current_credit
            acc.total_balance = total_debit - total_credit
            acc.prev_balance = prev_debit - prev_credit
        else:
            acc.current_balance = current_credit - current_debit
            acc.total_balance = total_credit - total_debit
            acc.prev_balance = prev_credit - prev_debit

    assets = [
        acc for acc in accounts if acc.type == "자산" and acc.category != "SAVING"
    ]
    savings = [
        acc for acc in accounts if acc.type == "자산" and acc.category == "SAVING"
    ]
    liabilities = [acc for acc in accounts if acc.type == "부채"]

    current_total_assets = sum(acc.current_balance for acc in assets)
    current_total_savings = sum(acc.current_balance for acc in savings)
    current_total_liabilities = sum(acc.current_balance for acc in liabilities)
    current_net_worth = (
        current_total_assets + current_total_savings - current_total_liabilities
    )

    total_assets = sum(acc.total_balance for acc in assets)
    total_savings = sum(acc.total_balance for acc in savings)
    total_liabilities = sum(acc.total_balance for acc in liabilities)
    net_worth = total_assets + total_savings - total_liabilities

    # Phase 3.2: 전월 대비 순자산 변동
    prev_total_assets = sum(acc.prev_balance for acc in assets)
    prev_total_savings = sum(acc.prev_balance for acc in savings)
    prev_total_liabilities = sum(acc.prev_balance for acc in liabilities)
    prev_net_worth = prev_total_assets + prev_total_savings - prev_total_liabilities
    net_worth_change = current_net_worth - prev_net_worth

    all_balances = [abs(acc.current_balance) for acc in assets + savings + liabilities]
    max_graph_value = max(all_balances) if all_balances else 1

    # Phase 3.3: 자산/부채 구성 도넛 차트 데이터
    asset_distribution = {}
    for acc in assets + savings:
        if acc.current_balance > 0:
            key = acc.get_category_display() or "일반"
            asset_distribution[key] = (
                asset_distribution.get(key, Decimal(0)) + acc.current_balance
            )
    asset_distribution = {k: float(v) for k, v in asset_distribution.items()}

    liability_distribution = {}
    for acc in liabilities:
        if acc.current_balance > 0:
            liability_distribution[acc.name] = float(acc.current_balance)

    # Phase 3.4: 이번 달 누락 고정 거래
    fixed_presets = TransactionPreset.objects.filter(
        owner=request.user,
        preset_type="FIXED",
        day_of_month__isnull=False,
        day_of_month__lte=today.day,
    ).select_related("debit_account", "credit_account")
    missing_presets = []
    for preset in fixed_presets:
        try:
            expected_date = date(today.year, today.month, preset.day_of_month)
        except ValueError:
            continue
        exists = Transaction.objects.filter(
            owner=request.user,
            date__year=today.year,
            date__month=today.month,
            debit_account=preset.debit_account,
            credit_account=preset.credit_account,
            item=preset.item,
        ).exists()
        if not exists:
            preset.expected_date = expected_date
            missing_presets.append(preset)
    missing_presets.sort(key=lambda p: p.expected_date)

    # --- 투자 계좌 수익률 계산 ---
    all_investment_accounts = [
        acc for acc in accounts if acc.is_investment and acc.type == "자산"
    ]
    investment_accounts = [
        acc for acc in all_investment_accounts if acc.current_balance != 0
    ]
    inv_account_ids = set(acc.id for acc in all_investment_accounts)

    for inv_acc in investment_accounts:
        # 외부 입금 (비투자 계좌에서 들어온 돈만)
        ext_deposits = (
            Transaction.objects.filter(
                owner=request.user, debit_account=inv_acc, date__lte=today
            )
            .exclude(credit_account__type__in=["수익", "비용"])
            .exclude(credit_account_id__in=inv_account_ids)
            .aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
        )
        # 외부 출금 (비투자 계좌로 나간 돈만)
        ext_withdrawals = (
            Transaction.objects.filter(
                owner=request.user, credit_account=inv_acc, date__lte=today
            )
            .exclude(debit_account__type__in=["수익", "비용"])
            .exclude(debit_account_id__in=inv_account_ids)
            .aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
        )
        # 투자계좌 간 입금 (타 투자계좌에서 받은 돈)
        inter_in = (
            Transaction.objects.filter(
                owner=request.user,
                debit_account=inv_acc,
                credit_account_id__in=inv_account_ids,
                date__lte=today,
            )
            .exclude(credit_account__type__in=["수익", "비용"])
            .aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
        )
        # 투자계좌 간 출금 (타 투자계좌로 보낸 돈)
        inter_out = (
            Transaction.objects.filter(
                owner=request.user,
                credit_account=inv_acc,
                debit_account_id__in=inv_account_ids,
                date__lte=today,
            )
            .exclude(debit_account__type__in=["수익", "비용"])
            .aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
        )
        # 투자 수익
        gains = Transaction.objects.filter(
            owner=request.user,
            debit_account=inv_acc,
            credit_account__type="수익",
            date__lte=today,
        ).aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
        # 투자 손실
        losses = Transaction.objects.filter(
            owner=request.user,
            credit_account=inv_acc,
            debit_account__type="비용",
            date__lte=today,
        ).aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]

        inv_acc.ext_deposits = ext_deposits
        inv_acc.ext_withdrawals = ext_withdrawals
        inv_acc.inter_in = inter_in
        inv_acc.inter_out = inter_out
        total_deposits = ext_deposits + inter_in
        total_withdrawals = ext_withdrawals + inter_out
        net_deposits = total_deposits - total_withdrawals
        inv_acc.auto_principal = net_deposits
        inv_acc.principal = (
            inv_acc.investment_principal
            if inv_acc.investment_principal is not None
            else net_deposits
        )
        inv_acc.current_value = inv_acc.current_balance
        inv_acc.investment_gain = gains
        inv_acc.investment_loss = losses
        inv_acc.net_pnl = gains - losses
        inv_acc.return_rate = (
            ((inv_acc.current_value - inv_acc.principal) / abs(inv_acc.principal) * 100)
            if inv_acc.principal != 0
            else Decimal(0)
        )

    # --- [v1.2] 통합 투자 수익률 (외부→투자 전체 기준) ---
    # 투자계좌 간 이체를 제거한, 외부에서 들어온 순수 자본만 집계
    consolidated_ext_deposits = (
        Transaction.objects.filter(
            owner=request.user, debit_account_id__in=inv_account_ids, date__lte=today
        )
        .exclude(credit_account__type__in=["수익", "비용"])
        .exclude(credit_account_id__in=inv_account_ids)
        .aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
    )
    consolidated_ext_withdrawals = (
        Transaction.objects.filter(
            owner=request.user, credit_account_id__in=inv_account_ids, date__lte=today
        )
        .exclude(debit_account__type__in=["수익", "비용"])
        .exclude(debit_account_id__in=inv_account_ids)
        .aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
    )
    consolidated_gains = Transaction.objects.filter(
        owner=request.user,
        debit_account_id__in=inv_account_ids,
        credit_account__type="수익",
        date__lte=today,
    ).aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
    consolidated_losses = Transaction.objects.filter(
        owner=request.user,
        credit_account_id__in=inv_account_ids,
        debit_account__type="비용",
        date__lte=today,
    ).aggregate(total=Coalesce(Sum("amount"), Decimal(0)))["total"]
    consolidated_net_invested = consolidated_ext_deposits - consolidated_ext_withdrawals
    consolidated_current_value = sum(a.current_balance for a in all_investment_accounts)
    consolidated_pnl = consolidated_current_value - consolidated_net_invested
    consolidated_return_rate = (
        (consolidated_pnl / abs(consolidated_net_invested) * 100)
        if consolidated_net_invested != 0
        else Decimal(0)
    )

    inv_total_principal = (
        sum(a.principal for a in investment_accounts)
        if investment_accounts
        else Decimal(0)
    )
    inv_total_current_value = (
        sum(a.current_value for a in investment_accounts)
        if investment_accounts
        else Decimal(0)
    )
    inv_total_net_pnl = (
        sum(a.net_pnl for a in investment_accounts)
        if investment_accounts
        else Decimal(0)
    )
    inv_total_return_rate = (
        (
            (inv_total_current_value - inv_total_principal)
            / abs(inv_total_principal)
            * 100
        )
        if inv_total_principal != 0
        else Decimal(0)
    )
    last_investment_tx = (
        Transaction.objects.filter(owner=request.user, date__lte=today)
        .filter(
            Q(debit_account__is_investment=True) | Q(credit_account__is_investment=True)
        )
        .order_by("-date", "-created_at")
        .first()
    )
    investment_last_update = last_investment_tx.date if last_investment_tx else None

    context = {
        "assets": assets,
        "savings": savings,
        "liabilities": liabilities,
        "current_total_assets": current_total_assets,
        "current_total_savings": current_total_savings,
        "current_total_liabilities": current_total_liabilities,
        "current_net_worth": current_net_worth,
        "total_assets": total_assets,
        "total_savings": total_savings,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "max_graph_value": max_graph_value,
        "selected_year": selected_year,
        "selected_month": selected_month,
        "monthly_income": monthly_income,
        "monthly_expense": monthly_expense,
        "monthly_savings": monthly_savings,
        "monthly_repayments": monthly_repayments,
        "monthly_net_profit": monthly_net_profit,
        "available_cash": available_cash,
        "years": range(2020, today.year + 2),
        "months": range(1, 13),
        "investment_accounts": investment_accounts,
        "inv_total_principal": inv_total_principal,
        "inv_total_current_value": inv_total_current_value,
        "inv_total_net_pnl": inv_total_net_pnl,
        "inv_total_return_rate": inv_total_return_rate,
        "investment_last_update": investment_last_update,
        # [v1.2] 통합 투자 수익률
        "consolidated_net_invested": consolidated_net_invested,
        "consolidated_current_value": consolidated_current_value,
        "consolidated_pnl": consolidated_pnl,
        "consolidated_return_rate": consolidated_return_rate,
        "consolidated_gains": consolidated_gains,
        "consolidated_losses": consolidated_losses,
    }

    # --- 차트 데이터 (Phase 1.1 활성 계정만, 1.2 현재월 마커, 1.3 미래 forecast) ---
    active_account_ids = list(accounts.values_list("id", flat=True))

    # Phase 3.1: 표시 기간 결정
    if range_value == "all":
        first_tx = (
            Transaction.objects.filter(owner=request.user)
            .filter(
                Q(debit_account_id__in=active_account_ids)
                | Q(credit_account_id__in=active_account_ids)
            )
            .order_by("date")
            .first()
        )
        start_date = first_tx.date.replace(day=1) if first_tx else today.replace(day=1)
    else:
        try:
            months_back = int(range_value)
        except (TypeError, ValueError):
            months_back = 12
        start_date = (today - relativedelta(months=months_back - 1)).replace(day=1)

    forecast_end_date = today + relativedelta(months=3)

    # 시작일 이전 누적 (활성 계정만)
    initial_assets = Transaction.objects.filter(
        owner=request.user, date__lt=start_date
    ).aggregate(
        diff=Sum(
            "amount",
            filter=Q(debit_account__type="자산")
            & Q(debit_account_id__in=active_account_ids),
        )
        - Sum(
            "amount",
            filter=Q(credit_account__type="자산")
            & Q(credit_account_id__in=active_account_ids),
        )
    )
    initial_liabilities = Transaction.objects.filter(
        owner=request.user, date__lt=start_date
    ).aggregate(
        diff=Sum(
            "amount",
            filter=Q(credit_account__type="부채")
            & Q(credit_account_id__in=active_account_ids),
        )
        - Sum(
            "amount",
            filter=Q(debit_account__type="부채")
            & Q(debit_account_id__in=active_account_ids),
        )
    )
    initial_net_worth_accum = (initial_assets["diff"] or Decimal(0)) - (
        initial_liabilities["diff"] or Decimal(0)
    )

    # actual: start_date ~ today
    actual_changes = (
        Transaction.objects.filter(owner=request.user, date__range=[start_date, today])
        .values("date__year", "date__month")
        .annotate(
            asset_diff=Sum(
                "amount",
                filter=Q(debit_account__type="자산")
                & Q(debit_account_id__in=active_account_ids),
            )
            - Sum(
                "amount",
                filter=Q(credit_account__type="자산")
                & Q(credit_account_id__in=active_account_ids),
            ),
            liab_diff=Sum(
                "amount",
                filter=Q(credit_account__type="부채")
                & Q(credit_account_id__in=active_account_ids),
            )
            - Sum(
                "amount",
                filter=Q(debit_account__type="부채")
                & Q(debit_account_id__in=active_account_ids),
            ),
        )
        .order_by("date__year", "date__month")
    )
    actual_dict = {
        (item["date__year"], item["date__month"]): (
            item["asset_diff"] or Decimal(0),
            item["liab_diff"] or Decimal(0),
        )
        for item in actual_changes
    }

    # forecast: today 이후 ~ forecast_end_date
    forecast_changes = (
        Transaction.objects.filter(
            owner=request.user, date__gt=today, date__lte=forecast_end_date
        )
        .values("date__year", "date__month")
        .annotate(
            asset_diff=Sum(
                "amount",
                filter=Q(debit_account__type="자산")
                & Q(debit_account_id__in=active_account_ids),
            )
            - Sum(
                "amount",
                filter=Q(credit_account__type="자산")
                & Q(credit_account_id__in=active_account_ids),
            ),
            liab_diff=Sum(
                "amount",
                filter=Q(credit_account__type="부채")
                & Q(credit_account_id__in=active_account_ids),
            )
            - Sum(
                "amount",
                filter=Q(debit_account__type="부채")
                & Q(debit_account_id__in=active_account_ids),
            ),
        )
        .order_by("date__year", "date__month")
    )
    forecast_dict = {
        (item["date__year"], item["date__month"]): (
            item["asset_diff"] or Decimal(0),
            item["liab_diff"] or Decimal(0),
        )
        for item in forecast_changes
    }

    chart_data = {
        "labels": [],
        "actual_data": [],
        "forecast_data": [],
        "current_month_index": None,
    }
    current_month_key = (today.year, today.month)
    actual_accum = initial_net_worth_accum
    forecast_accum = None
    idx = 0
    temp_date = start_date
    while temp_date <= forecast_end_date:
        year_month = (temp_date.year, temp_date.month)
        chart_data["labels"].append(temp_date.strftime("%Y-%m"))

        if year_month < current_month_key:
            asset_change, liab_change = actual_dict.get(
                year_month, (Decimal(0), Decimal(0))
            )
            actual_accum += asset_change - liab_change
            chart_data["actual_data"].append(float(actual_accum))
            chart_data["forecast_data"].append(None)
        elif year_month == current_month_key:
            asset_change, liab_change = actual_dict.get(
                year_month, (Decimal(0), Decimal(0))
            )
            actual_accum += asset_change - liab_change
            chart_data["actual_data"].append(float(actual_accum))
            chart_data["forecast_data"].append(float(actual_accum))
            chart_data["current_month_index"] = idx
            forecast_accum = actual_accum
            f_asset, f_liab = forecast_dict.get(year_month, (Decimal(0), Decimal(0)))
            forecast_accum += f_asset - f_liab
        else:
            f_asset, f_liab = forecast_dict.get(year_month, (Decimal(0), Decimal(0)))
            if forecast_accum is None:
                forecast_accum = actual_accum + (f_asset - f_liab)
            else:
                forecast_accum += f_asset - f_liab
            chart_data["actual_data"].append(None)
            chart_data["forecast_data"].append(float(forecast_accum))

        idx += 1
        temp_date += relativedelta(months=1)

    context["chart_data_json"] = json.dumps(chart_data)

    # Phase 3.1, 3.2, 3.3, 3.4 컨텍스트 추가
    context["range_value"] = range_value
    context["range_options"] = range_options
    context["qs_without_range"] = qs_without_range
    context["prev_net_worth"] = prev_net_worth
    context["net_worth_change"] = net_worth_change
    context["asset_distribution_json"] = json.dumps(
        asset_distribution, ensure_ascii=False
    )
    context["liability_distribution_json"] = json.dumps(
        liability_distribution, ensure_ascii=False
    )
    context["missing_presets"] = missing_presets

    return render(request, "account/asset_status.html", context)


@login_required
def budget_view(request):
    today = date.today()
    try:
        selected_year = int(request.GET.get("year", today.year))
        selected_month = int(request.GET.get("month", today.month))
        target_date = date(selected_year, selected_month, 1)
    except (ValueError, TypeError):
        target_date = today
        selected_year = today.year
        selected_month = today.month

    start_of_month = target_date.replace(day=1)
    end_of_month = start_of_month + relativedelta(months=1) - relativedelta(days=1)

    income_transactions = Transaction.objects.filter(
        owner=request.user,
        date__range=[start_of_month, end_of_month],
        credit_account__type="수익",
    )
    expense_transactions = Transaction.objects.filter(
        owner=request.user,
        date__range=[start_of_month, end_of_month],
        debit_account__type="비용",
    )

    income_actuals = {
        item["credit_account__name"]: item["total"]
        for item in income_transactions.values("credit_account__name").annotate(
            total=Sum("amount")
        )
    }
    expense_actuals = {
        item["debit_account__name"]: item["total"]
        for item in expense_transactions.values("debit_account__name").annotate(
            total=Sum("amount")
        )
    }

    all_income_accounts = Account.objects.filter(
        owner=request.user, type="수익", is_active=True
    )
    all_expense_accounts = Account.objects.filter(
        owner=request.user, type="비용", is_active=True
    )

    fixed_income_details = []
    other_income_total = 0
    for acc in all_income_accounts:
        actual = income_actuals.get(acc.name, 0)
        if acc.category == "FIXED":
            fixed_income_details.append({"name": acc.name, "actual": actual})
        else:
            other_income_total += actual

    fixed_expense_details = []
    other_expense_total = 0
    for acc in all_expense_accounts:
        actual = expense_actuals.get(acc.name, 0)
        if acc.category == "FIXED":
            fixed_expense_details.append({"name": acc.name, "actual": actual})
        else:
            other_expense_total += actual

    total_income = (
        sum(item["actual"] for item in fixed_income_details) + other_income_total
    )
    total_expense = (
        sum(item["actual"] for item in fixed_expense_details) + other_expense_total
    )

    context = {
        "year": selected_year,
        "month": selected_month,
        "years": range(2020, today.year + 2),
        "months": range(1, 13),
        "fixed_income_details": fixed_income_details,
        "other_income_total": other_income_total,
        "fixed_expense_details": fixed_expense_details,
        "other_expense_total": other_expense_total,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_total": total_income - total_expense,
    }
    return render(request, "account/budget_view.html", context)


@login_required
def settings_view(request):
    user_profile_form = UserProfileForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)
    account_form = AccountForm()
    preset_form = TransactionPresetForm(user=request.user)

    preset_form_has_errors = False

    if request.method == "POST":
        if "update_profile" in request.POST:
            user_profile_form = UserProfileForm(request.POST, instance=request.user)
            if user_profile_form.is_valid():
                user_profile_form.save()
                messages.success(request, "사용자 정보가 업데이트되었습니다.")
                return redirect(reverse("account:settings") + "#profile-section")

        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "비밀번호가 변경되었습니다.")
                return redirect(reverse("account:settings") + "#password-section")

        elif "add_account" in request.POST:
            account_form = AccountForm(request.POST)
            if account_form.is_valid():
                account = account_form.save(commit=False)
                account.owner = request.user
                account.save()
                messages.success(request, "새로운 회계 계정이 추가되었습니다.")
                return redirect(reverse("account:settings") + "#account-section")

        elif "add_preset" in request.POST:
            preset_form = TransactionPresetForm(request.POST, user=request.user)
            if preset_form.is_valid():
                preset = preset_form.save(commit=False)
                preset.owner = request.user
                preset.save()
                messages.success(request, "새로운 거래 프리셋이 추가되었습니다.")
                return redirect(reverse("account:settings") + "#preset-section")
            else:
                messages.error(
                    request, "거래 프리셋 저장 실패. 입력 항목을 확인해 주세요."
                )
                preset_form_has_errors = True

    user_accounts = Account.objects.filter(owner=request.user).order_by("type", "name")
    user_presets = TransactionPreset.objects.filter(owner=request.user).order_by(
        "preset_type", "name"
    )

    # 프리셋 생성을 위한 그룹화된 계정 목록
    debit_accounts_grouped = {}
    credit_accounts_grouped = {}
    active_accounts = Account.objects.filter(
        owner=request.user, is_active=True
    ).order_by("type", "name")

    for acc in active_accounts.exclude(type="수익"):
        if acc.type not in debit_accounts_grouped:
            debit_accounts_grouped[acc.type] = []
        debit_accounts_grouped[acc.type].append(acc)

    for acc in active_accounts.exclude(type="비용"):
        if acc.type not in credit_accounts_grouped:
            credit_accounts_grouped[acc.type] = []
        credit_accounts_grouped[acc.type].append(acc)

    context = {
        "user_profile_form": user_profile_form,
        "password_form": password_form,
        "account_form": account_form,
        "preset_form": preset_form,
        "preset_form_has_errors": preset_form_has_errors,
        "user_accounts": user_accounts,
        "user_presets": user_presets,
        "debit_accounts_grouped": debit_accounts_grouped,
        "credit_accounts_grouped": credit_accounts_grouped,
    }
    return render(request, "account/settings.html", context)


@login_required
def preset_update(request, pk):
    preset = get_object_or_404(TransactionPreset, pk=pk, owner=request.user)
    if request.method == "POST":
        form = TransactionPresetForm(request.POST, instance=preset, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "프리셋이 성공적으로 수정되었습니다.")
            return redirect(reverse("account:settings") + "#preset-section")
    else:
        form = TransactionPresetForm(instance=preset, user=request.user)

    # 프리셋 수정을 위한 그룹화된 계정 목록
    debit_accounts_grouped = {}
    credit_accounts_grouped = {}
    active_accounts = Account.objects.filter(
        owner=request.user, is_active=True
    ).order_by("type", "name")

    for acc in active_accounts.exclude(type="수익"):
        if acc.type not in debit_accounts_grouped:
            debit_accounts_grouped[acc.type] = []
        debit_accounts_grouped[acc.type].append(acc)

    for acc in active_accounts.exclude(type="비용"):
        if acc.type not in credit_accounts_grouped:
            credit_accounts_grouped[acc.type] = []
        credit_accounts_grouped[acc.type].append(acc)

    return render(
        request,
        "account/preset_form_update.html",
        {
            "form": form,
            "debit_accounts_grouped": debit_accounts_grouped,
            "credit_accounts_grouped": credit_accounts_grouped,
            "preset": preset,
        },
    )


@login_required
def preset_delete(request, pk):
    preset = get_object_or_404(TransactionPreset, pk=pk, owner=request.user)
    if request.method == "POST":
        preset.delete()
        messages.success(request, "프리셋이 삭제되었습니다.")
        return redirect(reverse("account:settings") + "#preset-section")
    return render(request, "account/confirm_delete.html", {"object": preset})


@login_required
def account_update(request, pk):
    account = get_object_or_404(Account, pk=pk, owner=request.user)
    if request.method == "POST":
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, "계정 항목이 성공적으로 수정되었습니다.")
            return redirect(reverse("account:settings") + "#account-section")
    else:
        form = AccountForm(instance=account)
    return render(request, "account/account_form_update.html", {"form": form})


@login_required
def account_delete(request, pk):
    account = get_object_or_404(Account, pk=pk, owner=request.user)
    if request.method == "POST":
        account.delete()
        messages.success(request, "계정 항목이 삭제되었습니다.")
        return redirect(reverse("account:settings") + "#account-section")
    return render(request, "account/confirm_delete.html", {"object": account})


@login_required
def reports_view(request):
    today = date.today()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except (ValueError, TypeError):
        year = today.year
        month = today.month

    # '전달 예산 가져오기' 버튼 처리
    if "copy_last_month_budget" in request.POST:
        # 1. 이전 달 날짜 계산
        current_month_start = date(year, month, 1)
        last_month_end = current_month_start - relativedelta(days=1)
        last_month_year = last_month_end.year
        last_month_month = last_month_end.month

        # 2. 이전 달 예산 조회
        last_month_budgets = Budget.objects.filter(
            owner=request.user, year=last_month_year, month=last_month_month
        )

        if last_month_budgets.exists():
            # 3. 현재 달 예산을 모두 지우고, 이전 달 예산을 새로 생성 (원자적 트랜잭션)
            with transaction.atomic():
                Budget.objects.filter(
                    owner=request.user, year=year, month=month
                ).delete()
                new_budgets = []
                for budget in last_month_budgets:
                    new_budgets.append(
                        Budget(
                            owner=request.user,
                            year=year,
                            month=month,
                            account=budget.account,
                            amount=budget.amount,
                        )
                    )
                Budget.objects.bulk_create(new_budgets)
            messages.success(
                request,
                f"{last_month_year}년 {last_month_month}월의 예산을 성공적으로 복사했습니다.",
            )
        else:
            messages.info(request, "복사할 전달 예산 데이터가 없습니다.")

        return redirect(reverse("account:reports") + f"?year={year}&month={month}")

    if request.method == "POST":
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget, created = Budget.objects.update_or_create(
                owner=request.user,
                year=year,
                month=month,
                account=form.cleaned_data["account"],
                defaults={"amount": form.cleaned_data["amount"]},
            )
            messages.success(request, "예산이 저장되었습니다.")
            return redirect(reverse("account:reports") + f"?year={year}&month={month}")
    else:
        form = BudgetForm(user=request.user)

    # --- 데이터 준비 (이전과 동일) ---
    # 예산/지출 리포트에서 제외할 비용 계정 (투자 P&L성 비용)
    EXCLUDED_EXPENSE_NAMES = ["투자 손실"]

    all_expense_accounts = (
        Account.objects.filter(owner=request.user, type="비용", is_active=True)
        .exclude(name__in=EXCLUDED_EXPENSE_NAMES)
        .order_by("name")
    )
    fixed_expense_accounts = all_expense_accounts.filter(category="FIXED")

    monthly_spending_query = (
        Transaction.objects.filter(
            owner=request.user,
            date__year=year,
            date__month=month,
            debit_account__type="비용",
        )
        .exclude(debit_account__name__in=EXCLUDED_EXPENSE_NAMES)
        .values("debit_account__name")
        .annotate(total_spent=Sum("amount"))
    )

    spending_dict = {
        item["debit_account__name"]: item["total_spent"]
        for item in monthly_spending_query
    }

    budgets = Budget.objects.filter(owner=request.user, year=year, month=month)
    budget_dict = {b.account.name: b.amount for b in budgets}

    # --- 고정 비용 세부 내역 만들기 (이전과 동일) ---
    fixed_expense_details = []
    for account in fixed_expense_accounts:
        spent = spending_dict.get(account.name, Decimal(0))
        fixed_expense_details.append(
            {
                "debit_account__name": account.name,
                "total_spent": spent,
            }
        )
    fixed_expenses_total = sum(item["total_spent"] for item in fixed_expense_details)
    for item in fixed_expense_details:
        item["percentage"] = (
            int((item["total_spent"] / fixed_expenses_total) * 100)
            if fixed_expenses_total > 0
            else 0
        )
        fixed_expense_details.sort(key=lambda x: x["total_spent"], reverse=True)

    # --- 전체 리포트 데이터 만들기 (이전과 동일) ---
    report_data = []
    chart_labels = []
    chart_budget_data = []
    chart_spent_data = []

    for account in all_expense_accounts:
        account_name = account.name
        spent = spending_dict.get(account_name, Decimal(0))
        budget = budget_dict.get(account_name, Decimal(0))
        usage_percent = int((spent / budget * 100)) if budget > 0 else 0

        report_data.append(
            {
                "name": account_name,
                "spent": spent,
                "budget": budget,
                "usage_percent": usage_percent,
            }
        )

        # 차트용 데이터 (지출이나 예산이 있는 항목만)
        if spent > 0 or budget > 0:
            chart_labels.append(account_name)
            chart_budget_data.append(float(budget))
            chart_spent_data.append(float(spent))

    # --- 월별 예산 합계 계산 ---
    total_budget = sum(budget_dict.values())
    total_spent = sum(spending_dict.values())
    remaining_budget = total_budget - total_spent

    context = {
        "year": year,
        "month": month,
        "report_data": report_data,
        "fixed_expenses_total": fixed_expenses_total,
        "fixed_expense_details": fixed_expense_details,
        "total_budget": total_budget,
        "total_spent": total_spent,
        "remaining_budget": remaining_budget,
        "years": range(today.year - 3, today.year + 2),
        "months": range(1, 13),
        "form": form,
        "budget_chart_json": json.dumps(
            {
                "labels": chart_labels,
                "budget": chart_budget_data,
                "spent": chart_spent_data,
            }
        ),
    }
    return render(request, "account/reports.html", context)


@login_required
def investment_principal_update(request, pk):
    account = get_object_or_404(Account, pk=pk, owner=request.user, is_investment=True)

    if request.method == "POST":
        value = request.POST.get("investment_principal", "").strip()
        if value == "" or value == "자동":
            account.investment_principal = None
        else:
            try:
                account.investment_principal = Decimal(value.replace(",", ""))
            except Exception:
                pass
        account.save()
        return redirect("account:asset_status")

    return render(
        request,
        "account/partials/investment_principal_form.html",
        {
            "account": account,
        },
    )
