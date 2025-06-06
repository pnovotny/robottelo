"""Test class for Products UI

:Requirement: Repositories

:CaseAutomation: Automated

:CaseComponent: Repositories

:team: Phoenix-content

:CaseImportance: High

"""

from datetime import timedelta

from fauxfactory import gen_choice
import pytest

from robottelo.config import settings
from robottelo.constants import REPO_TYPE, SYNC_INTERVAL, DataFile
from robottelo.utils.datafactory import (
    gen_string,
    parametrized,
    valid_cron_expressions,
    valid_data_list,
)


@pytest.fixture(scope='module')
def module_org(module_target_sat):
    return module_target_sat.api.Organization().create()


@pytest.mark.skipif((not settings.robottelo.REPOS_HOSTING_URL), reason='Missing repos_hosting_url')
def test_positive_end_to_end(session, module_org, module_target_sat):
    """Perform end to end testing for product component

    :id: d0e1f0d1-2380-4508-b270-62c1d8b3e2ff

    :expectedresults: All expected CRUD actions finished successfully

    :CaseImportance: Critical
    """
    product_name = gen_string('alpha')
    new_product_name = gen_string('alpha')
    product_label = gen_string('alpha')
    product_description = gen_string('alpha')
    gpg_key = module_target_sat.api.GPGKey(
        content=DataFile.VALID_GPG_KEY_FILE.read_text(),
        organization=module_org,
    ).create()
    sync_plan = module_target_sat.api.SyncPlan(organization=module_org).create()
    with session:
        # Create new product using different parameters
        session.product.create(
            {
                'name': product_name,
                'label': product_label,
                'gpg_key': gpg_key.name,
                'sync_plan': sync_plan.name,
                'description': product_description,
            }
        )
        assert session.product.search(product_name)[0]['Name'] == product_name
        # Verify that created entity has expected parameters
        product_values = session.product.read(product_name)
        assert product_values['details']['name'] == product_name
        assert product_values['details']['label'] == product_label
        assert product_values['details']['gpg_key'] == gpg_key.name
        assert product_values['details']['description'] == product_description
        assert product_values['details']['sync_plan'] == sync_plan.name
        # Update a product with a different name
        session.product.update(product_name, {'details.name': new_product_name})
        assert session.product.search(product_name)[0]['Name'] != product_name
        assert session.product.search(new_product_name)[0]['Name'] == new_product_name
        # Add a repo to product
        session.repository.create(
            new_product_name,
            {
                'name': gen_string('alpha'),
                'repo_type': REPO_TYPE['yum'],
                'repo_content.upstream_url': settings.repos.yum_1.url,
            },
        )
        # Synchronize the product
        result = session.product.synchronize(new_product_name)
        assert result['result'] == 'success'
        product_values = session.product.read(new_product_name)
        assert product_values['details']['repos_count'] == '1'
        assert product_values['details']['sync_state'] == 'Syncing Complete.'
        # Delete product
        session.product.delete(new_product_name)
        assert session.product.search(new_product_name)[0]['Name'] != new_product_name


@pytest.mark.parametrize('product_name', **parametrized(valid_data_list('ui')))
def test_positive_create_in_different_orgs(session, product_name, module_target_sat):
    """Create Product with same name but in different organizations

    :id: 469fc036-a48a-4c0a-9da9-33e73f903479

    :parametrized: yes

    :expectedresults: Product is created successfully in both
        organizations.
    """
    orgs = [module_target_sat.api.Organization().create() for _ in range(2)]
    with session:
        for org in orgs:
            session.organization.select(org_name=org.name)
            session.product.create({'name': product_name, 'description': org.name})
            assert session.product.search(product_name)[0]['Name'] == product_name
            product_values = session.product.read(product_name)
            assert product_values['details']['description'] == org.name


def test_positive_product_create_with_create_sync_plan(session, module_org, module_target_sat):
    """Perform Sync Plan Create from Product Create Page

    :id: 4a87b533-12b6-4d4e-8a99-4bb95efc4321

    :expectedresults: Ensure sync get created and assigned to Product.

    :CaseImportance: Medium
    """
    product_name = gen_string('alpha')
    product_description = gen_string('alpha')
    gpg_key = module_target_sat.api.GPGKey(
        content=DataFile.VALID_GPG_KEY_FILE.read_text(),
        organization=module_org,
    ).create()
    plan_name = gen_string('alpha')
    description = gen_string('alpha')
    cron_expression = gen_choice(valid_cron_expressions())
    with session:
        session.organization.select(module_org.name)
        startdate = session.browser.get_client_datetime() + timedelta(minutes=10)
        sync_plan_values = {
            'name': plan_name,
            'interval': SYNC_INTERVAL['custom'],
            'description': description,
            'cron_expression': cron_expression,
            'date_time.start_date': startdate.strftime("%Y-%m-%d"),
            'date_time.hours': startdate.strftime('%H'),
            'date_time.minutes': startdate.strftime('%M'),
        }
        session.product.create(
            {'name': product_name, 'gpg_key': gpg_key.name, 'description': product_description},
            sync_plan_values=sync_plan_values,
        )
        assert session.product.search(product_name)[0]['Name'] == product_name
        product_values = session.product.read(product_name, widget_names='details')
        assert product_values['details']['name'] == product_name
        assert product_values['details']['sync_plan'] == plan_name
        # Delete product
        session.product.delete(product_name)
        assert session.product.search(product_name)[0]['Name'] != product_name


def test_positive_bulk_action_advanced_sync(session, module_org, module_target_sat):
    """Advanced sync is available as a bulk action in the product.

    :id: 7e9bb306-452d-43b8-8725-604b4aebb222

    :customerscenario: true

    :steps:
        1. Enable or create a repository and sync it.
        2. Navigate to Content > Product > click on the product.
        3. Click Select Action > Advanced Sync.

    :expectedresults: Advanced sync for repositories can be run as a bulk action from the product.
    """
    repo_name = gen_string('alpha')
    product = module_target_sat.api.Product(organization=module_org).create()
    with session:
        session.repository.create(
            product.name,
            {
                'name': repo_name,
                'repo_type': REPO_TYPE['yum'],
                'repo_content.upstream_url': settings.repos.yum_1.url,
            },
        )
        # Repository sync
        session.repository.synchronize(product.name, repo_name)
        # Optimized Sync
        result = session.product.advanced_sync([product.name], sync_type='optimized')
        assert result['task']['result'] == 'success'
        # Complete Sync
        result = session.product.advanced_sync([product.name], sync_type='complete')
        assert result['task']['result'] == 'success'
