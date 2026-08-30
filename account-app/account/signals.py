# account/signals.py
import urllib.request
import json
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Transaction

logger = logging.getLogger(__name__)

INVEST_API_URL = getattr(settings, 'INVEST_API_BASE_URL', 'http://invest-app:8000') + '/portfolio/api/internal/sync-transfer/'
INTERNAL_TOKEN = getattr(settings, 'INTERNAL_SYNC_TOKEN', 'theprepared_inter_app_secret_sync_2026')

def _send_to_invest(payload):
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            INVEST_API_URL,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Host': 'stock.theprepared.kr',
                'X-Internal-Token': INTERNAL_TOKEN,
                'User-Agent': 'PFM-Sync-Engine/1.0'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp_body = resp.read().decode('utf-8')
            logger.info(f"[PFM -> Invest Sync] Response: {resp_body}")
    except Exception as e:
        logger.warning(f"[PFM -> Invest Sync Warning] Failed to send sync payload: {e}")

@receiver(post_save, sender=Transaction)
def handle_transaction_saved(sender, instance, created, **kwargs):
    """
    [v128.9] PFM 투자계좌 입출금 거래 생성/수정 시 invest 시스템으로 자동 실시간 전송
    """
    # 1. 평가손익 정산 거래([투자 수익], [투자 손실])는 입출금 집계에서 제외 (루프 방지)
    if instance.item.startswith('[투자 수익]') or instance.item.startswith('[투자 손실]') or instance.item.startswith('[투자 정산]'):
        return

    debit_is_inv = getattr(instance.debit_account, 'is_investment', False)
    credit_is_inv = getattr(instance.credit_account, 'is_investment', False)

    # 2. 투자계좌로의 입금 (비투자계좌 -> 투자계좌)
    if debit_is_inv and not credit_is_inv and instance.credit_account.type not in ['수익', '비용']:
        payload = {
            'action': 'save',
            'pfm_transaction_id': instance.id,
            'pfm_account_id': instance.debit_account.id,
            'transfer_type': 'DEPOSIT',
            'amount': float(instance.amount),
            'transfer_date': instance.date.isoformat(),
            'note': f"PFM: {instance.item} ({instance.memo or ''})".strip()
        }
        _send_to_invest(payload)

    # 3. 투자계좌에서의 출금 (투자계좌 -> 비투자계좌)
    elif credit_is_inv and not debit_is_inv and instance.debit_account.type not in ['수익', '비용']:
        payload = {
            'action': 'save',
            'pfm_transaction_id': instance.id,
            'pfm_account_id': instance.credit_account.id,
            'transfer_type': 'WITHDRAWAL',
            'amount': float(instance.amount),
            'transfer_date': instance.date.isoformat(),
            'note': f"PFM: {instance.item} ({instance.memo or ''})".strip()
        }
        _send_to_invest(payload)

@receiver(post_delete, sender=Transaction)
def handle_transaction_deleted(sender, instance, **kwargs):
    """
    [v128.9] PFM 투자계좌 입출금 거래 삭제 시 invest 시스템에 삭제 통보
    """
    if instance.item.startswith('[투자 수익]') or instance.item.startswith('[투자 손실]') or instance.item.startswith('[투자 정산]'):
        return

    debit_is_inv = getattr(instance.debit_account, 'is_investment', False)
    credit_is_inv = getattr(instance.credit_account, 'is_investment', False)

    if debit_is_inv or credit_is_inv:
        pfm_acc_id = instance.debit_account.id if debit_is_inv else instance.credit_account.id
        payload = {
            'action': 'delete',
            'pfm_transaction_id': instance.id,
            'pfm_account_id': pfm_acc_id,
        }
        _send_to_invest(payload)
