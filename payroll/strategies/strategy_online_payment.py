from django.db.models import Q, Sum

from core.signals import register_service_signal
from payroll.strategies.strategy_of_payments_interface import StrategyOfPaymentInterface
from workflow.services import WorkflowService
from workflow.systems.base import WorkflowHandler


class StrategyOnlinePayment(StrategyOfPaymentInterface):
    WORKFLOW_NAME = "payment-adaptor"
    WORKFLOW_GROUP = "openimis-coremis-payment-adaptor"

    @classmethod
    def accept_payroll(cls, payroll, user, **kwargs):
        workflow = cls._get_payment_workflow(cls.WORKFLOW_NAME, cls.WORKFLOW_GROUP)
        cls._send_data_to_adaptor(workflow, payroll, user, **kwargs)

    @classmethod
    def acknowledge_of_reponse_view(cls, payroll, response_from_gateway, user, rejected_bills):
        # save response coming from payment gateway in json_ext
        cls._save_payroll_data(payroll, user, response_from_gateway)
        # update bill attached to the payroll
        cls._save_bill_data(payroll, rejected_bills)

    @classmethod
    def reconcile_payroll(cls, payroll, user):
        from invoice.models import Bill
        bills = cls._get_bill_attached_to_payroll(payroll)
        # make the new invoice based on Unpaid status
        from core import datetime
        current_date = datetime.date.today()
        # Define the common data for new 'Validated' bills
        common_data = {
            "status": Bill.Status.VALIDATED,
            "dateBill": current_date,
        }

        for bill in bills.filter(status=Bill.Status.UNPAID):
            new_data = {
                **common_data,
                "code": f"{bill.code}-{current_date}-Unpaid",
            }
            bill.replace_object(new_data)

        for bill in bills.filter(status=Bill.Status.PAID):
            cls._create_bill_payment_for_paid_bill(bill, user, current_date)

        bills = bills.filter(status=Bill.Status.PAID)
        bills.update(status=Bill.Status.RECONCILIATED)
        from payroll.models import PayrollStatus
        payroll.status = PayrollStatus.RECONCILIATED
        payroll.save(username=user.username)

    @classmethod
    def _create_bill_payment_for_paid_bill(cls, bill, user, current_date):
        from invoice.models import DetailPaymentInvoice, PaymentInvoice
        from invoice.services import PaymentInvoiceService
        # Create a BillPayment object for the 'Paid' bill
        bill_payment = {
            "bill_id": bill,
            "code_tp": bill.code_tp,
            "code_ext": bill.code_ext,
            "code_receipt": bill.code_receipt,
            "label": bill.terms,
            'reconciliation_status': PaymentInvoice.ReconciliationStatus.RECONCILIATED,
            "fees": 0.0,
            "amount_received": bill.amount_total,
            "date_payment": current_date,
            'payment_origin': bill.payment_origin,
            'payer_ref': 'payment reference',
            'payer_name': 'payer name'
        }

        bill_payment_details = {
            'subject_type': 'bill',
            'subject_id': bill.id,
            'status': DetailPaymentInvoice.DetailPaymentStatus.ACCEPTED,
            'fees': 0.0,
            'amount': bill.amount_total,
            'reconcilation_id': '',
            'reconcilation_date': current_date,
        }
        bill_payment_details = DetailPaymentInvoice(**bill_payment_details)
        payment_service = PaymentInvoiceService(user)
        payment_service.create_with_detail(bill_payment, bill_payment_details)

    @classmethod
    def _get_payment_workflow(cls, workflow_name: str, workflow_group: str):
        result = WorkflowService.get_workflows(workflow_name, workflow_group)
        workflows = result.get('data', {}).get('workflows')
        workflow = workflows[0]
        return workflow

    @classmethod
    def _get_payroll_bills_amount(cls, payroll):
        bills = cls._get_bill_attached_to_payroll(payroll)
        total_amount = str(bills.aggregate(total_amount=Sum('amount_total'))['total_amount'])
        return total_amount

    @classmethod
    def _get_bill_attached_to_payroll(cls, payroll):
        from invoice.models import Bill
        filters = [Q(payrollbill__payroll_id=payroll.uuid,
                     is_deleted=False,
                     payrollbill__is_deleted=False,
                     payrollbill__payroll__is_deleted=False,
                     status=Bill.Status.VALIDATED
                     )]
        bills = Bill.objects.filter(*filters)
        return bills

    @classmethod
    def _get_bills_to_string(cls, bills):
        bill_uuids = [str(bill.uuid) for bill in bills]
        bill_uuids_string = ",".join(bill_uuids)
        return bill_uuids_string

    @classmethod
    def _send_data_to_adaptor(cls, workflow: WorkflowHandler, payroll, user, **kwargs):
        total_amount = cls._get_payroll_bills_amount(payroll)
        bills = cls._get_bill_attached_to_payroll(payroll)
        bill_uuids_string = cls._get_bills_to_string(bills)
        workflow.run({
            'user_uuid': str(user.id),
            'payroll_uuid': str(payroll.uuid),
            'payroll_amount': total_amount,
            'bills': bill_uuids_string,
        })
        from payroll.models import PayrollStatus
        payroll.status = PayrollStatus.ONGOING
        payroll.save(username=user.login_name)

    @classmethod
    def _save_payroll_data(cls, payroll, user, response_from_gateway):
        from payroll.models import PayrollStatus
        json_ext = payroll.json_ext
        json_ext['response_from_gateway'] = response_from_gateway
        payroll.json_ext = json_ext
        payroll.status = PayrollStatus.AWAITING_FOR_RECONCILIATION
        payroll.save(username=user.username)
        cls._create_payroll_reconcilation_task(payroll, user)

    @classmethod
    def _save_bill_data(cls, payroll, rejected_bills):
        from invoice.models import Bill
        rejected_bills, bills = cls._exclude_rejected_bills(payroll, rejected_bills)
        bills.update(status=Bill.Status.PAYED)
        rejected_bills.update(status=Bill.Status.UNPAID)

    @classmethod
    def _exclude_rejected_bills(cls, payroll, rejected_bills):
        rejected_uuids = [uuid.strip() for uuid in rejected_bills.split(',') if uuid.strip()]
        include_query = Q(uuid__in=rejected_uuids)
        rejected_bills_queryset = cls._get_bill_attached_to_payroll(payroll).filter(include_query)
        bills = cls._get_bill_attached_to_payroll(payroll).exclude(include_query)
        return rejected_bills_queryset, bills

    @classmethod
    @register_service_signal('online_payments.create_task')
    def _create_payroll_reconcilation_task(cls, payroll, user):
        from payroll.apps import PayrollConfig
        from tasks_management.services import TaskService
        from tasks_management.apps import TasksManagementConfig
        from tasks_management.models import Task
        TaskService(user).create({
            'source': 'payroll_reconciliation',
            'entity': payroll,
            'status': Task.Status.RECEIVED,
            'executor_action_event': TasksManagementConfig.default_executor_event,
            'business_event': PayrollConfig.payroll_reconciliation_event,
        })
