# account/views_internal.py
import json
import logging
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum
from .models import Account, Transaction

logger = logging.getLogger(__name__)

@csrf_exempt
def reconcile_valuation_api(request):
    """
    [v128.9] invest 시스템에서 실시간 계좌별 평가액을 수신하여
    PFM 복식부기 장부 잔액과의 차액을 '주식 수익' 또는 '투자 손실'로 자동 분개
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)
    
    token = request.headers.get('X-Internal-Token') or request.POST.get('token')
    if not token and request.body:
        try:
            body_data = json.loads(request.body)
            token = body_data.get('token')
        except Exception:
            body_data = {}
    else:
        try:
            body_data = json.loads(request.body) if request.body else {}
        except Exception:
            body_data = {}

    expected_token = getattr(settings, 'INTERNAL_SYNC_TOKEN', 'theprepared_inter_app_secret_sync_2026')
    if token != expected_token:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    valuations = body_data.get('valuations', [])
    if not valuations:
        return JsonResponse({'status': 'error', 'message': 'No valuations provided'}, status=400)
    
    results = []
    today = timezone.now().date()

    for item in valuations:
        pfm_acc_id = item.get('pfm_account_id')
        invest_asset = item.get('invest_asset')
        
        if not pfm_acc_id or invest_asset is None:
            continue

        try:
            acc = Account.objects.get(id=pfm_acc_id)
        except Account.DoesNotExist:
            results.append({
                'pfm_account_id': pfm_acc_id,
                'status': 'error',
                'message': f'Account {pfm_acc_id} not found'
            })
            continue
        
        deb_sum = Transaction.objects.filter(debit_account=acc).aggregate(s=Sum('amount'))['s'] or Decimal(0)
        cred_sum = Transaction.objects.filter(credit_account=acc).aggregate(s=Sum('amount'))['s'] or Decimal(0)
        curr_balance = deb_sum - cred_sum
        
        target_val = Decimal(str(round(float(invest_asset))))
        diff = target_val - curr_balance
        
        if diff == 0:
            results.append({
                'pfm_account_id': pfm_acc_id,
                'account_name': acc.name,
                'action': 'none',
                'diff': 0,
                'current_balance': int(curr_balance),
                'message': 'Already in sync'
            })
            continue

        if diff > 0:
            income_acc = (
                Account.objects.filter(owner=acc.owner, type='수익', name__in=['펀드,주식', '주식,펀드', '주식 수익', '펀드/주식']).first()
                or Account.objects.filter(owner=acc.owner, type='수익', name__icontains='주식').first()
                or Account.objects.filter(owner=acc.owner, type='수익', name__icontains='펀드').first()
                or Account.objects.filter(owner=acc.owner, type='수익').first()
            )
            if not income_acc:
                income_acc = Account.objects.create(owner=acc.owner, name='펀드,주식', type='수익', category='VARIABLE')
            
            t = Transaction.objects.create(
                owner=acc.owner,
                date=today,
                item=f'[투자 수익] {acc.name} 퀀트 실시간 평가익 반영',
                amount=diff,
                debit_account=acc,
                credit_account=income_acc,
                memo='The Prepared 퀀트 실시간 잔고 동기화'
            )
            action = 'profit'
            tx_id = t.id
        else:
            loss_acc = Account.objects.filter(owner=acc.owner, type='비용', name__icontains='손실').first()
            if not loss_acc:
                loss_acc = Account.objects.filter(owner=acc.owner, type='비용').first()
            if not loss_acc:
                loss_acc = Account.objects.create(owner=acc.owner, name='투자 손실', type='비용', category='VARIABLE')
            
            loss_amt = abs(diff)
            t = Transaction.objects.create(
                owner=acc.owner,
                date=today,
                item=f'[투자 손실] {acc.name} 퀀트 실시간 평가손 반영',
                amount=loss_amt,
                debit_account=loss_acc,
                credit_account=acc,
                memo='The Prepared 퀀트 실시간 잔고 동기화'
            )
            action = 'loss'
            tx_id = t.id
        
        results.append({
            'pfm_account_id': pfm_acc_id,
            'account_name': acc.name,
            'action': action,
            'diff': int(diff),
            'previous_balance': int(curr_balance),
            'new_balance': int(target_val),
            'transaction_id': tx_id
        })

    return JsonResponse({
        'status': 'ok',
        'synced_at': timezone.now().isoformat(),
        'results': results
    })
