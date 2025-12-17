
from graphene import Schema
from graphene.test import Client

from payroll.tests.data import gql_benefit_consumption_query
from core.test_helpers import create_admin_role, create_test_interactive_user, create_test_role
from payroll.schema import Query, Mutation
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext


class BenefitConsumptionGQLTestCase(openIMISGraphQLTestCase):

    user = None
    user_unauthorized = None
    gql_client = None
    gql_context = None
    gql_context_unauthorized = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user = create_test_interactive_user(username='username_authorized', roles=[create_admin_role().id])
        cls.user_unauthorized = create_test_interactive_user(username='username_unauthorized', roles=[create_test_role([], name="Empty role").id])
        gql_schema = Schema(
            query=Query,
            mutation=Mutation
        )
        cls.gql_client = Client(gql_schema)
        cls.gql_context = BaseTestContext(cls.user)
        cls.gql_context_unauthorized = BaseTestContext(cls.user_unauthorized)

    def test_query(self):
        output = self.gql_client.execute(gql_benefit_consumption_query, context=self.gql_context.get_request())
        result = output.get('data', {}).get('benefitConsumption', {})
        self.assertTrue(result)

    def test_query_unauthorized(self):
        output = self.gql_client.execute(gql_benefit_consumption_query, context=self.gql_context_unauthorized.get_request())
        error = next(iter(output.get('errors', [])), {}).get('message', None)
        self.assertTrue(error)
