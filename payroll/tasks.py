import logging
from celery import shared_task

from core.models import User
from payroll.models import Payroll, PayrollStatus, BenefitConsumptionStatus
from payroll.payments_registry import PaymentMethodStorage
from calculation.services import get_calculation_object
from django.db import transaction

logger = logging.getLogger(__name__)


def _select_beneficiary_based_on_location(payroll, payment_plan):
    from social_protection.models import BeneficiaryStatus, GroupBeneficiary
    return GroupBeneficiary.objects.filter(
        benefit_plan__id=payment_plan.benefit_plan.id,
        status=BeneficiaryStatus.ACTIVE,
        is_deleted=False,
        group__location__parent__id=payroll.location.id
    ) if payroll.location.id else GroupBeneficiary.objects.none()

@shared_task
def generate_benefits(payment_plan_id, date_from, date_to, payroll_id, payment_cycle_id, user_id):
    from contribution_plan.models import PaymentPlan
    from payment_cycle.models import PaymentCycle
    try:
        with transaction.atomic():
            payment_plan = PaymentPlan.objects.get(id=payment_plan_id)
            payroll = Payroll.objects.get(id=payroll_id)
            payment_cycle = PaymentCycle.objects.get(id=payment_cycle_id)
            calculation = get_calculation_object(payment_plan.calculation)
            calculation.calculate_if_active_for_object(
                payment_plan,
                user_id=user_id,
                start_date=date_from, end_date=date_to,
                beneficiaries_queryset=_select_beneficiary_based_on_location(payroll, payment_plan),
                payroll=payroll,
                payment_cycle=payment_cycle
            )
    except Exception as e:
        logger.error(f"Error in generate_benefits: {e}")
        raise


@shared_task
def send_requests_to_gateway_payment(payroll_id, user_id):
    try:
        #with transaction.atomic():
            payroll = Payroll.objects.get(id=payroll_id)
            strategy = PaymentMethodStorage.get_chosen_payment_method(payroll.payment_method )
            if strategy:
                user = User.objects.get(id=user_id)
                strategy.initialize_payment_gateway(payroll.payment_point)
                strategy.make_payment_for_payroll(payroll, user)
    except Exception as e:
        logger.error(f"Error in send_requests_to_gateway_payment: {e}")
        raise


@shared_task
def send_request_to_reconcile(payroll_id, user_id):
    payroll = Payroll.objects.get(id=payroll_id)
    user = User.objects.get(id=user_id)
    strategy = PaymentMethodStorage.get_chosen_payment_method(payroll.payment_method)
    if strategy.reconcile_payroll and strategy.reconcile_payroll.__code__.co_code != (lambda: None).__code__.co_code:
        strategy.initialize_payment_gateway(payroll.payment_point)
        strategy.change_status_of_payroll(payroll, PayrollStatus.RECONCILED, user)
        benefits = strategy.get_benefits_attached_to_payroll(payroll, BenefitConsumptionStatus.APPROVE_FOR_PAYMENT)
        payment_gateway_connector = strategy.PAYMENT_GATEWAY
        benefits_to_reconcile = []
        for benefit in benefits:
            is_reconciled = payment_gateway_connector.reconcile(benefit.code, benefit.amount)
            # Initialize json_ext if it is None
            if benefit.json_ext is None:
                benefit.json_ext = {}
            if is_reconciled:
                new_json_ext = benefit.json_ext.copy() if benefit.json_ext else {}
                new_json_ext['output_gateway'] = is_reconciled
                new_json_ext['gateway_reconciliation_success'] = True
                benefit.json_ext = {**benefit.json_ext, **new_json_ext}
                benefits_to_reconcile.append(benefit)
            else:
                # Handle the case where a benefit payment is rejected
                new_json_ext = benefit.json_ext.copy() if benefit.json_ext else {}
                new_json_ext['output_gateway'] = is_reconciled
                new_json_ext['gateway_reconciliation_success'] = False
                benefit.json_ext = {**benefit.json_ext, **new_json_ext}
                benefit.save(username=user.login_name)
                logger.info(f"Payment for benefit ({benefit.code}) was rejected.")
        if benefits_to_reconcile:
            strategy.reconcile_benefit_consumption(benefits_to_reconcile, user)

@shared_task
def send_partial_reconciliation(payroll_id, user_id):
    payroll = Payroll.objects.get(id=payroll_id)
    user = User.objects.get(id=user_id)
    strategy = PaymentMethodStorage.get_chosen_payment_method(payroll.payment_method)
    if strategy.reconcile_payroll and strategy.reconcile_payroll.__code__.co_code != (lambda: None).__code__.co_code:
        strategy.initialize_payment_gateway(payroll.payment_point)
        benefits = strategy.get_benefits_attached_to_payroll(payroll, BenefitConsumptionStatus.ACCEPTED)
        payment_gateway_connector = strategy.PAYMENT_GATEWAY
        benefits_to_reconcile = []
        for benefit in benefits:
            is_reconciled = payment_gateway_connector.reconcile(benefit.code, benefit.amount)
            # Initialize json_ext if it is None
            if benefit.json_ext is None:
                benefit.json_ext = {}
            if is_reconciled:
                new_json_ext = benefit.json_ext.copy() if benefit.json_ext else {}
                new_json_ext['output_gateway'] = is_reconciled
                new_json_ext['gateway_reconciliation_success'] = True
                benefit.json_ext = {**benefit.json_ext, **new_json_ext}
                benefits_to_reconcile.append(benefit)
        if benefits_to_reconcile:
            strategy.reconcile_benefit_consumption(benefits_to_reconcile, user)
