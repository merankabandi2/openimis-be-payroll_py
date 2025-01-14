from payroll.strategies.strategy_of_payments_interface import StrategyOfPaymentInterface


class StrategyOfflinePayment(StrategyOfPaymentInterface):

    @classmethod
    def verify_payroll(cls, payroll, user, **kwargs):
        from payroll.models import PayrollStatus
        cls.change_status_of_payroll(payroll, PayrollStatus.PENDING_APPROVAL, user)

    @classmethod
    def accept_payroll(cls, payroll, user, **kwargs):
        from payroll.models import PayrollStatus
        cls.change_status_of_payroll(payroll, PayrollStatus.APPROVE_FOR_PAYMENT, user)

    @classmethod
    def reconcile_payroll(cls, payroll, user):
        from payroll.models import PayrollStatus
        cls.change_status_of_payroll(payroll, PayrollStatus.RECONCILED, user)
