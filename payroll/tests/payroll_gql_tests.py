import json
import uuid
from datetime import datetime, timedelta
from core.models import MutationLog

from graphene import JSONString, Schema
from graphene.test import Client
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from contribution_plan.models import PaymentPlan
from individual.models import Individual
from individual.tests.data import service_add_individual_payload
from invoice.models import Bill
from payment_cycle.models import PaymentCycle
from payroll.models import Payroll, PayrollBill, PayrollStatus
from payroll.tests.data import gql_payroll_create, gql_payroll_query, gql_payroll_delete, \
    gql_payroll_create_no_json_ext
from payroll.tests.helpers import PaymentPointHelper
from core.test_helpers import LogInHelper
from payroll.schema import Query, Mutation
from social_protection.models import BenefitPlan, Beneficiary, BeneficiaryStatus
from social_protection.tests.data import service_add_payload
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext


class PayrollGQLTestCase(openIMISGraphQLTestCase):

    user = None
    user_unauthorized = None
    gql_client = None
    gql_context = None
    gql_context_unauthorized = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user = LogInHelper().get_or_create_user_api(username='username_authorized', roles=[7])
        cls.user_unauthorized = LogInHelper().get_or_create_user_api(username='username_unauthorized', roles=[1])
        gql_schema = Schema(
            query=Query,
            mutation=Mutation
        )
        cls.gql_client = Client(gql_schema)
        cls.gql_context = BaseTestContext(cls.user)
        cls.gql_context_unauthorized = BaseTestContext(cls.user_unauthorized)
        cls.name = "TestCreatePayroll"
        cls.status = PayrollStatus.PENDING_APPROVAL
        cls.payment_method = "TestPaymentMethod"
        cls.date_valid_from, cls.date_valid_to = cls.__get_start_and_end_of_current_month()
        cls.payment_point = PaymentPointHelper().get_or_create_payment_point_api()
        cls.benefit_plan = cls.__create_benefit_plan()
        cls.individual = cls.__create_individual()
        cls.subject_type = ContentType.objects.get_for_model(Beneficiary)
        cls.payment_plan = cls.__create_payment_plan(cls.benefit_plan)
        cls.payment_cycle = cls.__create_payment_cycle()
        cls.beneficiary = cls.__create_beneficiary()
        cls.bill = cls.__create_bill()
        cls.json_ext_able_bodied_false = """{"advanced_criteria": [{"custom_filter_condition": "able_bodied__boolean=False"}]}"""
        cls.json_ext_able_bodied_true = """{"advanced_criteria": [{"custom_filter_condition": "able_bodied__boolean=True"}]}"""
        cls.includedUnpaid = False

    def setup(self):
        payroll = self.payroll_from_db()
        if payroll:
            self.delete_payroll_and_check_bill(payroll)
        temp_payroll = self.payroll_from_db(f"{self.name}-tmp")
        if temp_payroll:
            self.delete_payroll_and_check_bill(temp_payroll)

    def payroll_from_db(self, name=None):
        return Payroll.objects.filter(
            name=(name or self.name),
            payment_plan_id=self.payment_plan.id,
            payment_cycle_id=self.payment_cycle.id,
            payment_point_id=self.payment_point.id,
            payment_method=self.payment_method,
            status=self.status,
            date_valid_from=self.date_valid_from,
            date_valid_to=self.date_valid_to,
            is_deleted=False,
        ).first()

    def test_query(self):
        output = self.gql_client.execute(gql_payroll_query, context=self.gql_context.get_request())
        result = output.get('data', {}).get('payroll', {})
        self.assertTrue(result)

    def test_query_unauthorized(self):
        output = self.gql_client.execute(gql_payroll_query, context=self.gql_context_unauthorized.get_request())
        error = next(iter(output.get('errors', [])), {}).get('message', None)
        self.assertTrue(error)

    def create_payroll(self, name, json_ext):
        variables = {
            "name": name,
            "paymentCycleId": str(self.payment_cycle.id),
            "paymentPlanId": str(self.payment_plan.id),
            "paymentPointId": str(self.payment_point.id),
            "paymentMethod": self.payment_method,
            "status": self.status,
            "dateValidFrom": self.date_valid_from,
            "dateValidTo": self.date_valid_to,
            "jsonExt": json_ext,
            "paymentPointId": str(self.payment_point.id),
            "clientMutationId": str(uuid.uuid4())
        }
        output = self.gql_client.execute(gql_payroll_create, context=self.gql_context.get_request(), variable_values=variables)
        self.assertEqual(output.get('errors'), None)

        return self.payroll_from_db(name)

    def create_payroll_no_json_ext(self, name):
        payload = gql_payroll_create_no_json_ext % (
            name,
            self.payment_cycle.id,
            self.payment_plan.id,
            self.payment_point.id,
            self.payment_method,
            self.status,
            self.date_valid_from,
            self.date_valid_to,
        )
        output = self.gql_client.execute(payload, context=self.gql_context.get_request())
        self.assertEqual(output.get('errors'), None)

        return self.payroll_from_db(name)

    def delete_payroll_and_check_bill(self, payroll):
        # payroll_bill = PayrollBill.objects.filter(
        #     bill=self.bill, payroll=payroll.first())
        # self.assertEqual(payroll_bill.count(), 1)
        # payroll_bill.delete()
        payroll.delete(username='username_authorized')
        # self.assertEqual(PayrollBill.objects.all().count(), 0)
        # FIXME
        # self.assertIsNone(payroll)

    # def test_create_fail_due_to_lack_of_bills_for_given_criteria(self):
    #     payroll = self.create_payroll(self.name, self.json_ext_able_bodied_false)
    #     self.assertFalse(payroll.exists())

    def test_create_no_advanced_criteria(self):
        payroll = self.create_payroll_no_json_ext(self.name)
        self.assertIsNotNone(payroll)
        self.delete_payroll_and_check_bill(payroll)

    def test_create_full(self):
        payroll = self.create_payroll(self.name, self.json_ext_able_bodied_true)
        self.assertIsNotNone(payroll)
        self.delete_payroll_and_check_bill(payroll)

    def test_create_fail_due_to_empty_name(self):
        payroll = self.create_payroll("", self.json_ext_able_bodied_true)
        self.assertIsNone(payroll)

    # def test_create_fail_due_to_one_bill_assigment(self):
    #     tmp_name = f"{self.name}-tmp"
    #     payroll_tmp = self.create_payroll(tmp_name, self.json_ext_able_bodied_true)
    #     self.assertTrue(payroll_tmp.exists())

    #     payroll = self.create_payroll(self.name, self.json_ext_able_bodied_true)
    #     self.assertFalse(payroll.exists())

    #     self.delete_payroll_and_check_bill(payroll_tmp)

    def test_create_unauthorized(self):
        variables = {
            "name": self.name,
            "paymentCycleId": str(self.payment_cycle.id),
            "paymentPlanId": str(self.payment_plan.id),
            "paymentMethod": self.payment_method,
            "status": PayrollStatus.PENDING_APPROVAL,
            "dateValidFrom": self.date_valid_from,
            "dateValidTo": self.date_valid_to,
            "jsonExt": self.json_ext_able_bodied_false,
            "clientMutationId": str(uuid.uuid4())
        }

        output = self.gql_client.execute(
            gql_payroll_create, context=self.gql_context_unauthorized.get_request(), variable_values=variables)
        self.assertFalse(
            Payroll.objects.filter(
                name=self.name,
                payment_plan_id=self.benefit_plan.id,
                payment_cycle_id=self.payment_cycle.id,
                payment_point_id=self.payment_point.id,
                payment_method=self.payment_method,
                status=self.status,
                date_valid_from=self.date_valid_from,
                date_valid_to=self.date_valid_to,
                json_ext=self.json_ext_able_bodied_false,
                is_deleted=False,
            ).exists()
        )

    def test_delete(self):
        payroll = Payroll(name=self.name,
                          payment_plan_id=self.payment_plan.id,
                          payment_point_id=self.payment_point.id,
                          payment_cycle_id=self.payment_cycle.id,
                          payment_method=self.payment_method,
                          status=self.status,
                          date_valid_from=self.date_valid_from,
                          date_valid_to=self.date_valid_to,
                          json_ext=json.loads(self.json_ext_able_bodied_false),
                          )
        payroll.save(username=self.user.username)
        # payroll_bill = PayrollBill(payroll=payroll, bill=self.bill)
        # payroll_bill.save(username=self.user.username)
        payload = gql_payroll_delete % json.dumps([str(payroll.id)])
        output = self.gql_client.execute(payload, context=self.gql_context.get_request())
        self.assertEqual(output.get('errors'), None)
        # FIXME self.assertTrue(Payroll.objects.filter(id=payroll.id, is_deleted=True).exists())
        # FIXME 
        # self.assertEqual(PayrollBill.objects.filter(payroll=payroll, bill=self.bill).count(), 0)

    def test_delete_unauthorized(self):
        payroll = Payroll(name=self.name,
                          payment_plan_id=self.payment_plan.id,
                          payment_cycle_id=self.payment_cycle.id,
                          payment_point_id=self.payment_point.id,
                          payment_method=self.payment_method,
                          status=self.status,
                          date_valid_from=self.date_valid_from,
                          date_valid_to=self.date_valid_to,
                          json_ext=json.loads(self.json_ext_able_bodied_true),
                          )
        payroll.save(username=self.user.username)
        payroll_bill = PayrollBill(payroll=payroll, bill=self.bill)
        payroll_bill.save(username=self.user.username)
        payload = gql_payroll_delete % json.dumps([str(payroll.id)])
        output = self.gql_client.execute(payload, context=self.gql_context_unauthorized.get_request())
        # FIXME look for delete task instead
        # self.assertTrue(Payroll.objects.filter(id=payroll.id, is_deleted=False).exists())
        # self.assertEqual(PayrollBill.objects.filter(payroll=payroll, bill=self.bill).count(), 1)
        # payroll_bill.delete(username=self.user.username)
        # self.assertTrue(PayrollBill.objects.filter(payroll=payroll, bill=self.bill, is_deleted=True))

    @classmethod
    def __create_benefit_plan(cls):
        object_data = {
            **service_add_payload
        }

        benefit_plan = BenefitPlan(**object_data)
        benefit_plan.save(username=cls.user.username)

        return benefit_plan

    @classmethod
    def __create_payment_plan(cls, benefit_plan):
        object_data = {
            'is_deleted': False,
            'code': "PP-E",
            'name': "Example Payment Plan",
            'benefit_plan': benefit_plan,
            'periodicity': 1,
            'calculation': "32d96b58-898a-460a-b357-5fd4b95cd87c",
            'json_ext': {
                'calculation_rule': {
                    'fixed_batch': 2,
                    'limit_per_single_transaction': 100
                } 
            },
        }

        payment_plan = PaymentPlan(**object_data)
        payment_plan.save(username=cls.user.username)
        return payment_plan

    @classmethod
    def __create_payment_cycle(cls):
        pc = PaymentCycle(
            start_date='2023-02-01', 
            end_date='2023-03-01', 
            type=ContentType.objects.get_for_model(BenefitPlan),
            code=str(datetime.now()))
        pc.save(username=cls.user.username)
        return pc

    @classmethod
    def __create_individual(cls):
        object_data = {
            **service_add_individual_payload
        }

        individual = Individual(**object_data)
        individual.save(username=cls.user.username)

        return individual

    @classmethod
    def __create_beneficiary(cls):
        object_data = {
            "individual": cls.individual,
            "benefit_plan": cls.benefit_plan,
            "json_ext": {"able_bodied": True},
            "status": BeneficiaryStatus.ACTIVE
        }
        beneficiary = Beneficiary(**object_data)
        beneficiary.save(username=cls.user.username)
        return beneficiary

    @classmethod
    def __create_bill(cls):
        object_data = {
            "subject_type": cls.subject_type,
            "subject_id": cls.beneficiary.id,
            "status": Bill.Status.VALIDATED,
            "code": str(datetime.now())
        }
        bill = Bill(**object_data)
        bill.save(username=cls.user.username)
        return bill

    @classmethod
    def __get_start_and_end_of_current_month(cls):
        today = datetime.today()
        # Set date_valid_from to the beginning of the current month
        date_valid_from = today.replace(day=1).strftime("%Y-%m-%d")

        # Calculate the last day of the current month
        next_month = today.replace(day=28) + timedelta(days=4)  # Adding 4 days to ensure we move to the next month
        date_valid_to = (next_month - timedelta(days=next_month.day)).strftime("%Y-%m-%d")

        return date_valid_from, date_valid_to
