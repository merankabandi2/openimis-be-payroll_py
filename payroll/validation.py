from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from core.validation import BaseModelValidation
from payroll.models import PaymentPoint, Payroll, PayrollBill, BenefitConsumption


class PaymentPointValidation(BaseModelValidation):
    OBJECT_TYPE = PaymentPoint

    @classmethod
    def validate_create(cls, user, **data):
        super().validate_create(user, **data)

    @classmethod
    def validate_update(cls, user, **data):
        super().validate_update(user, **data)

    @classmethod
    def validate_delete(cls, user, **data):
        super().validate_delete(user, **data)


class PayrollValidation(BaseModelValidation):
    OBJECT_TYPE = Payroll

    @classmethod
    def validate_create(cls, user, **data):
        errors = validate_payroll(data)
        if errors:
            raise ValidationError(errors)
        super().validate_create(user, **data)


class BenefitConsumptionValidation(BaseModelValidation):
    OBJECT_TYPE = BenefitConsumption

    @classmethod
    def validate_create(cls, user, **data):
        super().validate_create(user, **data)


def validate_payroll(data):
    return [
        *are_bills_in_data(data),
        *validate_one_payroll_per_bill(data),
        *validate_payroll_unique_name(data, uuid=None),
        *validate_not_empty_field(data, 'name')
    ]


def are_bills_in_data(data):
    bills = data.get('bills', None)
    if not bills:
        return [{"message": _("payroll.validation.payroll.no_bills_for_filter_criteria")}]
    return []


def validate_one_payroll_per_bill(data):
    bills = data.get('bills', [])
    query = PayrollBill.objects.filter(bill__in=bills, is_deleted=False)
    if query.exists():
        payroll_bill_ids = list(query.values_list('id', flat=True))
        return [{"message": _("payroll.validation.payroll.bill_already_assigned") % {
            "bill_ids": payroll_bill_ids,
        }}]
    return []


def validate_payroll_unique_name(data, uuid=None):
    name = data.get("name")
    instance = Payroll.objects.filter(name=name, is_deleted=False).first()
    if instance and instance.uuid != uuid:
        return [{"message": _("payroll.validation.payroll.name_exists" % {  # noqa: F504
            'name': name
        })}]
    return []


def validate_not_empty_field(data, field):
    string = data.get('name')
    if not string:
        return [{"message": _("payroll.validation.field_empty") % {
            'field': field
        }}]
    return []
