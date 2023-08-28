import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from im_export.views import check_user_rights
from payroll.apps import PayrollConfig
from payroll.models import Payroll
from payroll.payments_registry import PaymentMethodStorage

logger = logging.getLogger(__name__)


@api_view(["POST"])
#@permission_classes([check_user_rights(PayrollConfig.gql_payroll_create_perms, )])
def send_callback_to_openimis(request):
    try:
        user = request.user
        payroll_id, response_from_gateway = _resolve_send_callback_to_imis_args(request)
        payroll = Payroll.objects.get(id=payroll_id)
        strategy = PaymentMethodStorage.get_chosen_payment_method(payroll.payment_method)
        if strategy:
            # save the reponse from gateway in openIMIS
            strategy.acknowledge_of_reponse_view(payroll, response_from_gateway, user)
        return Response('true')
    except ValueError as exc:
        logger.error("Error while sending callback to openIMIS", exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.error("Unexpected error while sending callback to openIMIS", exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=500)


def _resolve_send_callback_to_imis_args(request):
    payroll_id = request.POST.get('payroll_id')
    response_from_gateway = request.POST.get('response_from_gateway')

    if not payroll_id:
        raise ValueError(f'Payroll Id not provided')
    if not response_from_gateway:
        raise ValueError(f'Response from gateway not provided')

    return payroll_id, response_from_gateway
