import logging

from django.db import transaction
from django.db.models import Q
from payroll.serializers import BulkIndividualPaymentRequestUpdateSerializer, IndividualPaymentRequestSerializer, IndividualPaymentRequestUpdateSerializer
from rest_framework import views




from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from oauth2_provider.contrib.rest_framework import TokenHasScope

from core.utils import DefaultStorageFileHandler
from im_export.views import check_user_rights
from payroll.apps import PayrollConfig
from payroll.models import Payroll, CsvReconciliationUpload, BenefitConsumptionStatus, BenefitConsumption
from payroll.payments_registry import PaymentMethodStorage
from payroll.services import CsvReconciliationService, BenefitConsumptionService

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([check_user_rights(PayrollConfig.gql_payroll_create_perms, )])
def send_callback_to_openimis(request):
    try:
        user = request.user
        payroll_id, response_from_gateway, rejected_bills = \
            _resolve_send_callback_to_imis_args(request)
        payroll = Payroll.objects.get(id=payroll_id)
        strategy = PaymentMethodStorage.get_chosen_payment_method(payroll.payment_method)
        if strategy:
            # save the reponse from gateway in openIMIS
            strategy.acknowledge_of_reponse_view(
                payroll,
                response_from_gateway,
                user,
                rejected_bills
            )
        return Response({'success': True, 'error': None}, status=201)
    except ValueError as exc:
        logger.error("Error while sending callback to openIMIS", exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.error("Unexpected error while sending callback to openIMIS", exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([check_user_rights(PayrollConfig.gql_payroll_search_perms, )])
def fetch_beneficiaries_to_pay(request):
    try:
        user = request.user
        payroll_id, response_from_gateway, rejected_bills = \
            _resolve_send_callback_to_imis_args(request)
        payroll = Payroll.objects.get(id=payroll_id)
        strategy = PaymentMethodStorage.get_chosen_payment_method(payroll.payment_method)
        if strategy:
            # save the reponse from gateway in openIMIS
            strategy.acknowledge_of_reponse_view(
                payroll,
                response_from_gateway,
                user,
                rejected_bills
            )
        return Response({'success': True, 'error': None}, status=201)
    except ValueError as exc:
        logger.error("Error while sending callback to openIMIS", exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.error("Unexpected error while sending callback to openIMIS", exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=500)


def _resolve_send_callback_to_imis_args(request):
    payroll_id = request.data.get('payroll_id')
    response_from_gateway = request.data.get('response_from_gateway')
    rejected_bills = request.data.get('rejected_bills')
    if not payroll_id:
        raise ValueError('Payroll Id not provided')
    if not response_from_gateway:
        raise ValueError('Response from gateway not provided')
    if rejected_bills is None:
        raise ValueError('Rejected Bills not provided')

    return payroll_id, response_from_gateway, rejected_bills


class CSVReconciliationAPIView(views.APIView):
    permission_classes = [check_user_rights(PayrollConfig.gql_csv_reconciliation_create_perms, )]

    def get(self, request):
        try:
            payroll_id = request.GET.get('payroll_id')
            get_blank = request.GET.get('blank')
            get_blank_bool = get_blank.lower() == 'true'

            if get_blank_bool:
                service = CsvReconciliationService(request.user)
                in_memory_file = service.download_reconciliation(payroll_id)
                response = Response(headers={'Content-Disposition': f'attachment; filename="reconciliation.csv"'},
                                    content_type='text/csv')
                response.content = in_memory_file.getvalue()
                return response
            else:
                file_name = request.GET.get('payroll_file_name')
                path = PayrollConfig.get_payroll_payment_file_path(payroll_id, file_name)
                file_handler = DefaultStorageFileHandler(path)
                return file_handler.get_file_response_csv(file_name)
        except ValueError as exc:
            logger.error("Error while generating CSV reconciliation", exc_info=exc)
            return Response({'success': False, 'error': str(exc)}, status=400)
        except FileNotFoundError as exc:
            logger.error("File not found", exc_info=exc)
            return Response({'success': False, 'error': str(exc)}, status=404)
        except Exception as exc:
            logger.error("Error while generating CSV reconciliation", exc_info=exc)
            return Response({'success': False, 'error': str(exc)}, status=500)

    @transaction.atomic
    def post(self, request):
        upload = CsvReconciliationUpload()
        payroll_id = request.GET.get('payroll_id')
        try:
            upload.save(username=request.user.login_name)
            file = request.FILES.get('file')
            target_file_path = PayrollConfig.get_payroll_payment_file_path(payroll_id, file.name)
            upload.file_name = file.name
            file_handler = DefaultStorageFileHandler(target_file_path)
            file_handler.check_file_path()
            service = CsvReconciliationService(request.user)
            file_to_upload, errors, summary = service.upload_reconciliation(payroll_id, file, upload)
            if errors:
                upload.status = CsvReconciliationUpload.Status.PARTIAL_SUCCESS
                upload.error = errors
                upload.json_ext = {'extra_info': summary}
            else:
                upload.status = CsvReconciliationUpload.Status.SUCCESS
                upload.json_ext = {'extra_info': summary}
            upload.save(username=request.user.login_name)
            file_handler.save_file(file_to_upload)
            return Response({'success': True, 'error': None}, status=201)
        except Exception as exc:
            logger.error("Error while uploading CSV reconciliation", exc_info=exc)
            if upload:
                upload.error = {'error': str(exc)}
                upload.payroll = Payroll.objects.filter(id=payroll_id).first()
                upload.status = CsvReconciliationUpload.Status.FAIL
                summary = {
                    'affected_rows': 0,
                }
                upload.json_ext = {'extra_info': summary}
                upload.save(username=request.user.login_name)
            return Response({'success': False, 'error': str(exc)}, status=500)


class IndividualPaymentRequestData(views.APIView):
    """
    API view for fetching and updating payment requests
    GET: List payment requests that belong to the requestor's payment point
    POST: Update status of payment requests
    """
    permission_classes = [TokenHasScope]
    required_scopes = ['benefit_consumption:read', 'benefit_consumption:write']

    def get_required_scopes(self, request):
        """Return appropriate scopes based on request method"""
        method_scopes = {
            'GET': ['benefit_consumption:read'],
            'POST': ['benefit_consumption:write']
        }
        return method_scopes.get(request.method, [])

    def get(self, request):
        """List payment requests for the requestor's payment point"""
        application_name = request.auth.application.name
        
        # Get status filter from query params, default to ACCEPTED
        status_filter = request.query_params.get(
            'status', 
            BenefitConsumptionStatus.ACCEPTED
        )
        
        # Get benefits using service
        benefits = BenefitConsumptionService.get_benefits_by_payment_point(
            application_name, 
            status_filter
        )
        
        # Paginate results
        paginator = PageNumberPagination()
        paginator.page_size = request.query_params.get('page_size', 10)
        result_page = paginator.paginate_queryset(benefits, request)
        serializer = IndividualPaymentRequestSerializer(result_page, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        """Update payment request status"""
        serializer = IndividualPaymentRequestUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        application_name = request.auth.application.name
        benefit_id = serializer.validated_data['benefit_id']
        # Get status filter from query params, default to ACCEPTED
        status_filter = request.query_params.get(
            'status', 
            BenefitConsumptionStatus.APPROVE_FOR_PAYMENT
        )
        
        # Validate ownership using service
        unauthorized = BenefitConsumptionService.validate_benefit_ownership(
            [benefit_id], 
            application_name
        )
        
        if unauthorized:
            return Response(
                {"error": f"Unauthorized access to benefits: {unauthorized}"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get benefit using service    
        benefit = BenefitConsumptionService.get_benefit_by_id(benefit_id)
        if not benefit:
            return Response(
                {"error": f"Benefit with ID {benefit_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        try:
            # Update status using service
            result = BenefitConsumptionService.update_benefit_status(
                benefit, 
                serializer.validated_data, 
                application_name
            )
            
            # Get updated benefit data
            updated_benefit = BenefitConsumptionService.get_benefit_by_id(benefit_id)
            benefit_data = IndividualPaymentRequestSerializer(updated_benefit).data
            
            return Response({
                'update_result': result,
                'benefit_data': benefit_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BulkUpdatePaymentRequestAPI(views.APIView):
    """API view for bulk updating payment requests"""
    permission_classes = [TokenHasScope]
    required_scopes = ['benefit_consumption:write']
    
    @transaction.atomic
    def post(self, request):
        serializer = BulkIndividualPaymentRequestUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        application_name = request.auth.application.name
        updates = serializer.validated_data['updates']
        benefit_ids = [update['benefit_id'] for update in updates]
        # Get status filter from query params, default to ACCEPTED
        status_filter = request.query_params.get(
            'status', 
            BenefitConsumptionStatus.APPROVE_FOR_PAYMENT
        )
        
        # Validate ownership using service
        unauthorized = BenefitConsumptionService.validate_benefit_ownership(
            benefit_ids, 
            application_name
        )
        
        if unauthorized:
            return Response(
                {"error": f"Unauthorized access to benefits: {unauthorized}"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        results = []
        errors = []
        
        for update in updates:
            benefit = BenefitConsumptionService.get_benefit_by_id(update['benefit_id'])
            if not benefit:
                errors.append({
                    'benefit_id': str(update['benefit_id']),
                    'error': 'Benefit not found'
                })
                continue
                
            try:
                result = BenefitConsumptionService.update_benefit_status(
                    benefit,
                    update,
                    application_name
                )
                results.append(result)
            except Exception as e:
                errors.append({
                    'benefit_id': str(update['benefit_id']),
                    'error': str(e)
                })
        
        return Response({
            'results': results,
            'errors': errors,
            'success_count': len(results),
            'error_count': len(errors)
        }, status=status.HTTP_207_MULTI_STATUS if errors else status.HTTP_200_OK)