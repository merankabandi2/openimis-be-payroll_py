import json

from graphene import Schema
from graphene.test import Client
from django.test import TestCase

from location.models import Location
from payroll.models import PaymentPoint
from payroll.tests.data import gql_payment_point_query, gql_payment_point_delete, gql_payment_point_update, \
    gql_payment_point_create
from core.test_helpers import LogInHelper
from payroll.schema import Query, Mutation
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext


class PaymentPointGQLTestCase(openIMISGraphQLTestCase):


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
        cls.location = Location.objects.filter(validity_to__isnull=True, type='V').first()

    def test_query(self):
        output = self.gql_client.execute(gql_payment_point_query, context=self.gql_context.get_request())
        result = output.get('data', {}).get('paymentPoint', {})
        self.assertTrue(result)

    def test_query_unauthorized(self):
        output = self.gql_client.execute(gql_payment_point_query, context=self.gql_context_unauthorized.get_request())
        error = next(iter(output.get('errors', [])), {}).get('message', None)
        self.assertTrue(error)

    def test_create(self):
        payload = gql_payment_point_create % (
            json.dumps("Test"),
            self.location.id,
            self.user.id
        )
        output = self.gql_client.execute(payload, context=self.gql_context.get_request())
        self.assertEqual(output.get('errors'), None)
        self.assertTrue(PaymentPoint.objects.filter(
            name="Test", location_id=self.location.id, ppm_id=self.user.id, is_deleted=False).exists())

    def test_create_unauthorized(self):
        payload = gql_payment_point_create % (
            json.dumps("Test"),
            self.location.id,
            self.user.id)
        output = self.gql_client.execute(payload, context=self.gql_context_unauthorized.get_request())
        self.assertFalse(PaymentPoint.objects.filter(
            name="Test", location_id=self.location.id, ppm_id=self.user.id, is_deleted=False).exists())

    def test_update(self):
        payment_point = PaymentPoint(name="Test", location=self.location, ppm=self.user)
        payment_point.save(username=self.user.username)
        payload = gql_payment_point_update % (
            json.dumps(str(payment_point.id)),
            json.dumps("TestUpdated"),
            payment_point.location.id,
            payment_point.ppm.id)
        output = self.gql_client.execute(payload, context=self.gql_context.get_request())
        self.assertEqual(output.get('errors'), None)
        self.assertFalse(PaymentPoint.objects.filter(id=payment_point.id, name="Test", is_deleted=False).exists())
        self.assertTrue(PaymentPoint.objects.filter(id=payment_point.id, name="TestUpdated", is_deleted=False).exists())

    def test_update_unauthorized(self):
        payment_point = PaymentPoint(name="Test", location=self.location, ppm=self.user)
        payment_point.save(username=self.user.username)
        payload = gql_payment_point_update % (
            json.dumps(str(payment_point.id)),
            json.dumps("TestUpdated"),
            payment_point.location.id,
            payment_point.ppm.id)
        output = self.gql_client.execute(payload, context=self.gql_context_unauthorized.get_request())
        self.assertTrue(PaymentPoint.objects.filter(id=payment_point.id, name="Test", is_deleted=False).exists())
        self.assertFalse(
            PaymentPoint.objects.filter(id=payment_point.id, name="TestUpdated", is_deleted=False).exists())

    def test_delete(self):
        payment_point = PaymentPoint(name="Test", location=self.location, ppm=self.user)
        payment_point.save(username=self.user.username)
        payload = gql_payment_point_delete % json.dumps([str(payment_point.id)])
        output = self.gql_client.execute(payload, context=self.gql_context.get_request())
        self.assertEqual(output.get('errors'), None)
        # FIXME self.assertTrue(PaymentPoint.objects.filter(id=payment_point.id, is_deleted=True).exists())

    def test_delete_unauthorized(self):
        payment_point = PaymentPoint(name="Test", location=self.location, ppm=self.user)
        payment_point.save(username=self.user.username)
        payload = gql_payment_point_delete % json.dumps([str(payment_point.id)])
        output = self.gql_client.execute(payload, context=self.gql_context_unauthorized.get_request())
        # FIXME self.assertTrue(PaymentPoint.objects.filter(id=payment_point.id, is_deleted=False).exists())
