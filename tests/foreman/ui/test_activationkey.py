"""Test class for Activation key UI

:Requirement: Activationkey

:CaseAutomation: Automated

:CaseComponent: ActivationKeys

:team: Phoenix-subscriptions

:CaseImportance: High

"""

import random
from time import sleep

from broker import Broker
from fauxfactory import gen_string
import pytest

from robottelo import constants
from robottelo.config import settings
from robottelo.hosts import ContentHost
from robottelo.utils.datafactory import parametrized, valid_data_list


@pytest.mark.e2e
@pytest.mark.upgrade
def test_positive_end_to_end_crud(session, module_org, module_target_sat):
    """Perform end to end testing for activation key component

    :id: b6b98c45-e41e-4c7a-9be4-997273b7e24d

    :expectedresults: All expected CRUD actions finished successfully

    :CaseImportance: High
    """
    name = gen_string('alpha')
    new_name = gen_string('alpha')
    cv = module_target_sat.api.ContentView(organization=module_org).create()
    cv.publish()
    with session:
        # Create activation key with content view and LCE assigned
        session.activationkey.create(
            {'name': name, 'lce': {constants.ENVIRONMENT: True}, 'content_view': cv.name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        # Verify content view and LCE are assigned
        ak_values = session.activationkey.read(name, widget_names='details')
        assert ak_values['details']['name'] == name
        assert ak_values['details']['content_view'] == cv.name
        assert ak_values['details']['lce'][constants.ENVIRONMENT][constants.ENVIRONMENT]
        # Update activation key with new name
        session.activationkey.update(name, {'details.name': new_name})
        assert session.activationkey.search(new_name)[0]['Name'] == new_name
        assert session.activationkey.search(name)[0]['Name'] != name
        # Delete activation key
        session.activationkey.delete(new_name)
        assert session.activationkey.search(new_name)[0]['Name'] != new_name


@pytest.mark.no_containers
@pytest.mark.e2e
@pytest.mark.upgrade
@pytest.mark.parametrize(
    'repos_collection',
    [
        {
            'distro': f'rhel{settings.content_host.default_rhel_version}',
            'YumRepository': {'url': settings.repos.yum_0.url},
        }
    ],
    indirect=True,
)
@pytest.mark.rhel_ver_match([settings.content_host.default_rhel_version])
def test_positive_end_to_end_register(
    session,
    function_sca_manifest_org,
    default_location,
    repos_collection,
    rhel_contenthost,
    target_sat,
):
    """Create activation key and use it during content host registering

    :id: dfaecf6a-ba61-47e1-87c5-f8966a319b41

    :expectedresults: Content host was registered successfully using activation
        key, association is reflected on webUI

    :parametrized: yes

    :CaseImportance: High
    """
    org = function_sca_manifest_org
    lce = target_sat.api.LifecycleEnvironment(organization=org).create()
    repos_collection.setup_content(org.id, lce.id)
    ak_name = repos_collection.setup_content_data['activation_key']['name']

    repos_collection.setup_virtual_machine(rhel_contenthost)
    with session:
        session.organization.select(org.name)
        session.location.select(default_location.name)
        chost = session.host_new.get_details(rhel_contenthost.hostname, widget_names='details')[
            'details'
        ]['registration_details']['details']
        assert chost['registered_by'] == f'Activation key {ak_name}'
        ak_values = session.activationkey.read(ak_name, widget_names='content_hosts')
        assert len(ak_values['content_hosts']['table']) == 1
        assert ak_values['content_hosts']['table'][0]['Name'] == rhel_contenthost.hostname


@pytest.mark.upgrade
@pytest.mark.parametrize('cv_name', **parametrized(valid_data_list('ui')))
def test_positive_create_with_cv(session, module_org, cv_name, target_sat):
    """Create Activation key for all variations of Content Views

    :id: 2ad000f1-6c80-46aa-a61b-9ea62cefe91b

    :parametrized: yes

    :expectedresults: Activation key is created
    """
    name = gen_string('alpha')
    env_name = gen_string('alpha')
    repo_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, module_org.id)
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {env_name: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['content_view'] == cv_name


@pytest.mark.upgrade
def test_positive_search_scoped(session, module_org, target_sat):
    """Test scoped search for different activation key parameters

    :id: 2c2ee1d7-0997-4a89-8f0a-b04e4b6177c0

    :customerscenario: true

    :expectedresults: Search functionality returns correct activation key

    :BZ: 1259374

    :CaseImportance: High
    """
    name = gen_string('alpha')
    env_name = gen_string('alpha')
    cv_name = gen_string('alpha')
    description = gen_string('alpha')
    repo_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, module_org.id)
    with session:
        session.activationkey.create(
            {
                'name': name,
                'description': description,
                'lce': {env_name: True},
                'content_view': cv_name,
            }
        )
        for query_type, query_value in [
            ('content_view', cv_name),
            ('environment', env_name),
            ('description', description),
        ]:
            assert session.activationkey.search(f'{query_type} = {query_value}')[0]['Name'] == name


@pytest.mark.upgrade
def test_positive_create_with_host_collection(
    session, module_org, module_target_sat, module_lce, module_promoted_cv
):
    """Create Activation key with Host Collection

    :id: 0e4ad2b4-47a7-4087-828f-2b0535a97b69

    :expectedresults: Activation key is created
    """
    name = gen_string('alpha')
    hc = module_target_sat.api.HostCollection(organization=module_org).create()
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {module_lce.name: True}, 'content_view': module_promoted_cv.name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        session.activationkey.add_host_collection(name, hc.name)
        ak = session.activationkey.read(name, widget_names='host_collections')
        assert ak['host_collections']['resources']['assigned'][0]['Name'] == hc.name


@pytest.mark.upgrade
def test_positive_create_with_envs(session, module_org, target_sat):
    """Create Activation key with lifecycle environment

    :id: f75e994a-6da1-40a3-9685-f8387388b3f0

    :expectedresults: Activation key is created
    """
    name = gen_string('alpha')
    cv_name = gen_string('alpha')
    env_name = gen_string('alphanumeric')
    # Helper function to create and sync custom repository
    repo_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    # Helper function to create and promote CV to next env
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, module_org.id)
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {env_name: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['lce'][env_name][env_name]


def test_positive_add_host_collection_non_admin(
    module_org, test_name, target_sat, module_lce, module_promoted_cv
):
    """Test that host collection can be associated to Activation Keys by
    non-admin user.

    :id: 417f0b36-fd49-4414-87ab-6f72a09696f2

    :expectedresults: Activation key is created, added host collection is
        listed

    :BZ: 1473212
    """
    ak_name = gen_string('alpha')
    hc = target_sat.api.HostCollection(organization=module_org).create()
    # Create non-admin user with specified permissions
    roles = [target_sat.api.Role().create()]
    user_permissions = {
        'Katello::ActivationKey': constants.PERMISSIONS['Katello::ActivationKey'],
        'Katello::HostCollection': constants.PERMISSIONS['Katello::HostCollection'],
    }
    viewer_role = target_sat.api.Role().search(query={'search': 'name="Viewer"'})[0]
    roles.append(viewer_role)
    target_sat.api_factory.create_role_permissions(roles[0], user_permissions)
    password = gen_string('alphanumeric')
    user = target_sat.api.User(
        admin=False, role=roles, password=password, organization=[module_org]
    ).create()
    with target_sat.ui_session(test_name, user=user.login, password=password) as session:
        session.activationkey.create(
            {
                'name': ak_name,
                'lce': {module_lce.name: True},
                'content_view': module_promoted_cv.name,
            }
        )
        assert session.activationkey.search(ak_name)[0]['Name'] == ak_name
        session.activationkey.add_host_collection(ak_name, hc.name)
        ak = session.activationkey.read(ak_name, widget_names='host_collections')
        assert ak['host_collections']['resources']['assigned'][0]['Name'] == hc.name


@pytest.mark.upgrade
def test_positive_remove_host_collection_non_admin(
    module_org, test_name, target_sat, module_lce, module_promoted_cv
):
    """Test that host collection can be removed from Activation Keys by
    non-admin user.

    :id: 187456ec-5690-4524-9701-8bdb74c7912a

    :expectedresults: Activation key is created, removed host collection is not
        listed
    """
    ak_name = gen_string('alpha')
    hc = target_sat.api.HostCollection(organization=module_org).create()
    # Create non-admin user with specified permissions
    roles = [target_sat.api.Role().create()]
    user_permissions = {
        'Katello::ActivationKey': constants.PERMISSIONS['Katello::ActivationKey'],
        'Katello::HostCollection': constants.PERMISSIONS['Katello::HostCollection'],
    }
    viewer_role = target_sat.api.Role().search(query={'search': 'name="Viewer"'})[0]
    roles.append(viewer_role)
    target_sat.api_factory.create_role_permissions(roles[0], user_permissions)
    password = gen_string('alphanumeric')
    user = target_sat.api.User(
        admin=False, role=roles, password=password, organization=[module_org]
    ).create()
    with target_sat.ui_session(test_name, user=user.login, password=password) as session:
        session.activationkey.create(
            {
                'name': ak_name,
                'lce': {module_lce.name: True},
                'content_view': module_promoted_cv.name,
            }
        )
        assert session.activationkey.search(ak_name)[0]['Name'] == ak_name
        session.activationkey.add_host_collection(ak_name, hc.name)
        ak = session.activationkey.read(ak_name, widget_names='host_collections')
        assert ak['host_collections']['resources']['assigned'][0]['Name'] == hc.name
        # remove Host Collection
        session.activationkey.remove_host_collection(ak_name, hc.name)
        ak = session.activationkey.read(ak_name, widget_names='host_collections')
        assert not ak['host_collections']['resources']['assigned']


def test_positive_delete_with_env(session, module_org, target_sat):
    """Create Activation key with environment and delete it

    :id: b6019881-3d6e-4b75-89f5-1b62aff3b1ca

    :expectedresults: Activation key is deleted
    """
    name = gen_string('alpha')
    cv_name = gen_string('alpha')
    env_name = gen_string('alpha')
    # Helper function to create and promote CV to next environment
    repo_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, module_org.id)
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {env_name: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        session.activationkey.delete(name)
        assert session.activationkey.search(name)[0]['Name'] != name


@pytest.mark.upgrade
def test_positive_delete_with_cv(session, module_org, target_sat):
    """Create Activation key with content view and delete it

    :id: 7e40e1ed-8314-406b-9451-05f64806a6e6

    :expectedresults: Activation key is deleted
    """
    name = gen_string('alpha')
    cv_name = gen_string('alpha')
    env_name = gen_string('alpha')
    # Helper function to create and promote CV to next environment
    repo_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, module_org.id)
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {env_name: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        session.activationkey.delete(name)
        assert session.activationkey.search(name)[0]['Name'] != name


@pytest.mark.run_in_one_thread
def test_positive_update_env(session, module_org, target_sat):
    """Update Environment in an Activation key

    :id: 895cda6a-bb1e-4b94-a858-95f0be78a17b

    :expectedresults: Activation key is updated
    """
    name = gen_string('alpha')
    cv_name = gen_string('alpha')
    env_name = gen_string('alphanumeric')
    # Helper function to create and promote CV to next environment
    repo_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, module_org.id)
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {constants.ENVIRONMENT: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['lce'][env_name][constants.ENVIRONMENT]
        assert not ak['details']['lce'][env_name][env_name]
        session.activationkey.update(name, {'details.lce': {env_name: True}})
        ak = session.activationkey.read(name, widget_names='details')
        assert not ak['details']['lce'][env_name][constants.ENVIRONMENT]
        assert ak['details']['lce'][env_name][env_name]


@pytest.mark.run_in_one_thread
@pytest.mark.parametrize('cv2_name', **parametrized(valid_data_list('ui')))
def test_positive_update_cv(session, module_org, cv2_name, target_sat):
    """Update Content View in an Activation key

    :id: 68880ca6-acb9-4a16-aaa0-ced680126732

    :parametrized: yes

    :steps:
        1. Create Activation key
        2. Update the Content view with another Content view which has custom
            products

    :expectedresults: Activation key is updated
    """
    name = gen_string('alpha')
    env1_name = gen_string('alpha')
    env2_name = gen_string('alpha')
    cv1_name = gen_string('alpha')
    # Helper function to create and promote CV to next environment
    repo1_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    target_sat.api_factory.cv_publish_promote(cv1_name, env1_name, repo1_id, module_org.id)
    repo2_id = target_sat.api_factory.create_sync_custom_repo(module_org.id)
    target_sat.api_factory.cv_publish_promote(cv2_name, env2_name, repo2_id, module_org.id)
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {env1_name: True}, 'content_view': cv1_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['content_view'] == cv1_name
        session.activationkey.update(
            name, {'details': {'lce': {env2_name: True}, 'content_view': cv2_name}}
        )
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['content_view'] == cv2_name


@pytest.mark.run_in_one_thread
def test_positive_update_rh_product(function_sca_manifest_org, session, target_sat):
    """Update Content View in an Activation key

    :id: 9b0ac209-45de-4cc4-97e8-e191f3f37239

    :steps:

        1. Create an activation key
        2. Update the content view with another content view which has RH
            products

    :expectedresults: Activation key is updated
    """
    name = gen_string('alpha')
    env1_name = gen_string('alpha')
    env2_name = gen_string('alpha')
    cv1_name = gen_string('alpha')
    cv2_name = gen_string('alpha')
    rh_repo1 = {
        'name': constants.REPOS['rhva6']['name'],
        'product': constants.PRDS['rhel'],
        'reposet': constants.REPOSET['rhva6'],
        'basearch': constants.DEFAULT_ARCHITECTURE,
        'releasever': constants.DEFAULT_RELEASE_VERSION,
    }
    rh_repo2 = {
        'name': ('Red Hat Enterprise Virtualization Agents for RHEL 6 Server RPMs i386 6Server'),
        'product': constants.PRDS['rhel'],
        'reposet': constants.REPOSET['rhva6'],
        'basearch': 'i386',
        'releasever': constants.DEFAULT_RELEASE_VERSION,
    }
    org = function_sca_manifest_org
    repo1_id = target_sat.api_factory.enable_sync_redhat_repo(rh_repo1, org.id)
    target_sat.api_factory.cv_publish_promote(cv1_name, env1_name, repo1_id, org.id)
    repo2_id = target_sat.api_factory.enable_sync_redhat_repo(rh_repo2, org.id)
    target_sat.api_factory.cv_publish_promote(cv2_name, env2_name, repo2_id, org.id)
    with session:
        session.organization.select(org.name)
        session.activationkey.create(
            {'name': name, 'lce': {env1_name: True}, 'content_view': cv1_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['content_view'] == cv1_name
        session.activationkey.update(
            name, {'details': {'lce': {env2_name: True}, 'content_view': cv2_name}}
        )
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['content_view'] == cv2_name


@pytest.mark.run_in_one_thread
def test_positive_add_rh_product(function_sca_manifest_org, session, target_sat):
    """Test that RH product can be associated to Activation Keys

    :id: d805341b-6d2f-4e16-8cb4-902de00b9a6c

    :expectedresults: RH products are successfully associated to Activation key
    """
    name = gen_string('alpha')
    cv_name = gen_string('alpha')
    env_name = gen_string('alpha')
    rh_repo = {
        'name': constants.REPOS['rhva6']['name'],
        'product': constants.PRDS['rhel'],
        'reposet': constants.REPOSET['rhva6'],
        'basearch': constants.DEFAULT_ARCHITECTURE,
        'releasever': constants.DEFAULT_RELEASE_VERSION,
    }
    org = function_sca_manifest_org
    # Helper function to create and promote CV to next environment
    repo_id = target_sat.api_factory.enable_sync_redhat_repo(rh_repo, org.id)
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, org.id)
    with session:
        session.organization.select(org.name)
        session.activationkey.create(
            {'name': name, 'lce': {env_name: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='repository sets')['repository sets'][
            'table'
        ][0]
        assert rh_repo['reposet'] == ak['Repository Name']


def test_positive_add_custom_product(session, module_org, target_sat):
    """Test that custom product can be associated to Activation Keys

    :id: e66db2bf-517a-46ff-ba23-9f9744bef884

    :expectedresults: Custom products are successfully associated to Activation
        key
    """
    name = gen_string('alpha')
    cv_name = gen_string('alpha')
    env_name = gen_string('alpha')
    product_name = gen_string('alpha')
    # Helper function to create and promote CV to next environment
    repo_id = target_sat.api_factory.create_sync_custom_repo(
        org_id=module_org.id, product_name=product_name
    )
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, module_org.id)
    with session:
        session.activationkey.create(
            {'name': name, 'lce': {env_name: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='repository sets')['repository sets'][
            'table'
        ][0]
        assert product_name == ak['Product Name']


@pytest.mark.run_in_one_thread
@pytest.mark.upgrade
def test_positive_add_rh_and_custom_products(target_sat, function_sca_manifest_org, session):
    """Test that RH/Custom product can be associated to Activation keys

    :id: 3d8876fa-1412-47ca-a7a4-bce2e8baf3bc

    :steps:
        1. Create Activation key
        2. Associate RH product(s) to Activation Key
        3. Associate custom product(s) to Activation Key

    :expectedresults: RH/Custom product is successfully associated to
        Activation key
    """
    name = gen_string('alpha')
    rh_repo = {
        'name': constants.REPOS['rhva6']['name'],
        'product': constants.PRDS['rhel'],
        'reposet': constants.REPOSET['rhva6'],
        'basearch': constants.DEFAULT_ARCHITECTURE,
        'releasever': constants.DEFAULT_RELEASE_VERSION,
    }
    custom_product_name = gen_string('alpha')
    repo_name = gen_string('alpha')
    org = function_sca_manifest_org
    product = target_sat.api.Product(name=custom_product_name, organization=org).create()
    repo = target_sat.api.Repository(name=repo_name, product=product).create()
    rhel_repo_id = target_sat.api_factory.enable_rhrepo_and_fetchid(
        basearch=rh_repo['basearch'],
        org_id=org.id,
        product=rh_repo['product'],
        repo=rh_repo['name'],
        reposet=rh_repo['reposet'],
        releasever=rh_repo['releasever'],
    )
    for repo_id in [rhel_repo_id, repo.id]:
        target_sat.api.Repository(id=repo_id).sync()
    with session:
        session.organization.select(org.name)
        session.activationkey.create(
            {
                'name': name,
                'lce': {constants.ENVIRONMENT: True},
                'content_view': constants.DEFAULT_CV,
            }
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        ak = session.activationkey.read(name, widget_names='repository sets')
        reposets = [reposet['Repository Name'] for reposet in ak['repository sets']['table']]
        assert {repo_name, constants.REPOSET['rhva6']} == set(reposets)


@pytest.mark.run_in_one_thread
@pytest.mark.upgrade
def test_positive_fetch_product_content(target_sat, function_sca_manifest_org, session):
    """Associate RH & custom product with AK and fetch AK's product content

    :id: 4c37fb12-ea2a-404e-b7cc-a2735e8dedb6

    :expectedresults: Both Red Hat and custom product subscriptions are
        assigned as Activation Key's product content

    :BZ: 1426386, 1432285
    """
    org = function_sca_manifest_org
    lce = target_sat.api.LifecycleEnvironment(organization=org).create()
    rh_repo_id = target_sat.api_factory.enable_rhrepo_and_fetchid(
        basearch='x86_64',
        org_id=org.id,
        product=constants.PRDS['rhel'],
        repo=constants.REPOS['rhst7']['name'],
        reposet=constants.REPOSET['rhst7'],
        releasever=None,
    )
    rh_repo = target_sat.api.Repository(id=rh_repo_id).read()
    rh_repo.sync()
    custom_product = target_sat.api.Product(organization=org).create()
    custom_repo = target_sat.api.Repository(
        name=gen_string('alphanumeric').upper(),  # first letter is always
        # uppercase on product content page, workarounding it for
        # successful checks
        product=custom_product,
    ).create()
    custom_repo.sync()
    cv = target_sat.api.ContentView(
        organization=org, repository=[rh_repo_id, custom_repo.id]
    ).create()
    cv.publish()
    cvv = cv.read().version[0].read()
    cvv.promote(data={'environment_ids': lce.id, 'force': True})
    ak = target_sat.api.ActivationKey(content_view=cv, organization=org, environment=lce).create()
    with session:
        session.organization.select(org.name)
        ak = session.activationkey.read(ak.name, widget_names='repository_sets')
        reposets = [reposet['Repository Name'] for reposet in ak['repository_sets']['table']]
        assert {custom_repo.name, constants.REPOSET['rhst7']} == set(reposets)


@pytest.mark.e2e
@pytest.mark.upgrade
def test_positive_access_non_admin_user(session, test_name, target_sat):
    """Access activation key that has specific name and assigned environment by
    user that has filter configured for that specific activation key

    :id: 358a22d1-d576-475a-b90c-98e90a2ed1a9

    :customerscenario: true

    :expectedresults: Only expected activation key can be accessed by new non
        admin user

    :BZ: 1463813
    """
    ak_name = gen_string('alpha')
    non_searchable_ak_name = gen_string('alpha')
    org = target_sat.api.Organization().create()
    envs_list = ['STAGING', 'DEV', 'IT', 'UAT', 'PROD']
    for name in envs_list:
        target_sat.api.LifecycleEnvironment(name=name, organization=org).create()
    env_name = random.choice(envs_list)
    cv = target_sat.api.ContentView(organization=org).create()
    cv.publish()
    content_view_version = cv.read().version[0]
    content_view_version.promote(
        data={
            'environment_ids': [target_sat.api.LifecycleEnvironment(name=env_name).search()[0].id]
        }
    )
    # Create new role
    role = target_sat.api.Role().create()
    # Create filter with predefined activation keys search criteria
    envs_condition = ' or '.join(['environment = ' + s for s in envs_list])
    target_sat.api.Filter(
        organization=[org],
        permission=target_sat.api.Permission().search(
            filters={'name': 'view_activation_keys'},
            query={'search': 'resource_type="Katello::ActivationKey"'},
        ),
        role=role,
        search=f'name ~ {ak_name} and ({envs_condition})',
    ).create()

    # Add permissions for Organization and Location
    target_sat.api.Filter(
        permission=target_sat.api.Permission().search(
            query={'search': 'resource_type="Organization"'}
        ),
        role=role,
    ).create()
    target_sat.api.Filter(
        permission=target_sat.api.Permission().search(query={'search': 'resource_type="Location"'}),
        role=role,
    ).create()

    # Create new user with a configured role
    default_loc = target_sat.api.Location().search(
        query={'search': f'name="{constants.DEFAULT_LOC}"'}
    )[0]
    user_login = gen_string('alpha')
    user_password = gen_string('alpha')
    target_sat.api.User(
        role=[role],
        admin=False,
        login=user_login,
        password=user_password,
        organization=[org],
        location=[default_loc],
        default_organization=org,
    ).create()

    with session:
        session.organization.select(org_name=org.name)
        session.location.select(constants.DEFAULT_LOC)
        for name in [ak_name, non_searchable_ak_name]:
            session.activationkey.create(
                {'name': name, 'lce': {env_name: True}, 'content_view': cv.name}
            )
            assert session.activationkey.read(name, widget_names='details')['details']['lce'][
                env_name
            ][env_name]

    with target_sat.ui_session(test_name, user=user_login, password=user_password) as session:
        session.organization.select(org.name)
        session.location.select(constants.DEFAULT_LOC)
        assert session.activationkey.search(ak_name)[0]['Name'] == ak_name
        assert (
            session.activationkey.search(non_searchable_ak_name)[0]['Name']
            != non_searchable_ak_name
        )


def test_positive_remove_user(
    session, module_org, test_name, module_target_sat, module_lce, module_promoted_cv
):
    """Delete any user who has previously created an activation key
    and check that activation key still exists

    :id: f0504bd8-52d2-40cd-91c6-64d71b14c876

    :expectedresults: Activation Key can be read

    :BZ: 1291271
    """
    ak_name = gen_string('alpha')
    # Create user
    password = gen_string('alpha')
    user = module_target_sat.api.User(
        admin=True, default_organization=module_org, password=password
    ).create()
    # Create Activation Key using new user credentials
    with module_target_sat.ui_session(test_name, user.login, password) as non_admin_session:
        non_admin_session.activationkey.create(
            {
                'name': ak_name,
                'lce': {module_lce.name: True},
                'content_view': module_promoted_cv.name,
            }
        )
        assert non_admin_session.activationkey.search(ak_name)[0]['Name'] == ak_name
    # Remove user and check that AK still exists
    user.delete()
    with session:
        assert session.activationkey.search(ak_name)[0]['Name'] == ak_name


def test_positive_add_docker_repo_cv(session, module_org, module_target_sat):
    """Add docker repository to a non-composite content view and
    publish it. Then create an activation key and associate it with the
    Docker content view.

    :id: e4935729-c5bc-46be-a23a-93ebde6b3506

    :expectedresults: Content view with docker repo can be added to
        activation key
    """
    lce = module_target_sat.api.LifecycleEnvironment(organization=module_org).create()
    repo = module_target_sat.api.Repository(
        content_type=constants.REPO_TYPE['docker'],
        product=module_target_sat.api.Product(organization=module_org).create(),
        url=settings.container.registry_hub,
    ).create()
    content_view = module_target_sat.api.ContentView(
        composite=False, organization=module_org, repository=[repo]
    ).create()
    module_target_sat.wait_for_tasks(
        search_query='Actions::Katello::Repository::MetadataGenerate'
        f' and resource_id = {repo.id}'
        ' and resource_type = Katello::Repository',
        max_tries=6,
        search_rate=10,
    )
    content_view.publish()
    cvv = content_view.read().version[0].read()
    cvv.promote(data={'environment_ids': lce.id, 'force': False})
    ak_name = gen_string('alphanumeric')
    with session:
        session.activationkey.create(
            {'name': ak_name, 'lce': {lce.name: True}, 'content_view': content_view.name}
        )
        ak = session.activationkey.read(ak_name, 'details')
        assert ak['details']['content_view'] == content_view.name
        assert ak['details']['lce'][lce.name][lce.name]


def test_positive_add_docker_repo_ccv(session, module_org, module_target_sat):
    """Add docker repository to a non-composite content view and publish it.
    Then add this content view to a composite content view and publish it.
    Create an activation key and associate it with the composite Docker content
    view.

    :id: 0d412f54-6333-413e-8040-4e51ae5c069c

    :expectedresults: Docker-based content view can be added to activation
        key
    """
    lce = module_target_sat.api.LifecycleEnvironment(organization=module_org).create()
    repo = module_target_sat.api.Repository(
        content_type=constants.REPO_TYPE['docker'],
        product=module_target_sat.api.Product(organization=module_org).create(),
        url=settings.container.registry_hub,
    ).create()
    content_view = module_target_sat.api.ContentView(
        composite=False, organization=module_org, repository=[repo]
    ).create()
    sleep(5)
    content_view.publish()
    cvv = content_view.read().version[0].read()
    cvv.promote(data={'environment_ids': lce.id, 'force': False})
    composite_cv = module_target_sat.api.ContentView(
        component=[cvv], composite=True, organization=module_org
    ).create()
    composite_cv.publish()
    ccvv = composite_cv.read().version[0].read()
    ccvv.promote(data={'environment_ids': lce.id, 'force': False})
    ak_name = gen_string('alphanumeric')
    with session:
        session.activationkey.create(
            {'name': ak_name, 'lce': {lce.name: True}, 'content_view': composite_cv.name}
        )
        ak = session.activationkey.read(ak_name, 'details')
        assert ak['details']['content_view'] == composite_cv.name
        assert ak['details']['lce'][lce.name][lce.name]


def test_positive_add_host(
    session, module_org, rhel_contenthost, target_sat, module_promoted_cv, module_lce
):
    """Test that hosts can be associated to Activation Keys

    :id: 886e9ea5-d917-40e0-a3b1-41254c4bf5bf

    :steps:
        1. Create Activation key
        2. Create different hosts
        3. Associate the hosts to Activation key

    :expectedresults: Hosts are successfully associated to Activation key

    :parametrized: yes
    """
    ak = target_sat.api.ActivationKey(
        content_view=module_promoted_cv,
        environment=module_lce,
        organization=module_org,
    ).create()
    result = rhel_contenthost.register(module_org, None, ak.name, target_sat)
    assert result.status == 0, f'Failed to register host: {result.stderr}'
    assert rhel_contenthost.subscribed
    with session:
        session.location.select(constants.DEFAULT_LOC)
        session.organization.select(module_org.name)
        ak = session.activationkey.read(ak.name, widget_names='content_hosts')
        assert len(ak['content_hosts']['table']) == 1
        assert ak['content_hosts']['table'][0]['Name'] == rhel_contenthost.hostname


def test_positive_delete_with_system(session, rhel_contenthost, target_sat):
    """Delete an Activation key which has registered systems

    :id: 86cd070e-cf46-4bb1-b555-e7cb42e4dc9f

    :steps:
        1. Create an Activation key
        2. Register systems to it
        3. Delete the Activation key

    :expectedresults: Activation key is deleted

    :parametrized: yes
    """
    name = gen_string('alpha')
    cv_name = gen_string('alpha')
    env_name = gen_string('alpha')
    product_name = gen_string('alpha')
    org = target_sat.api.Organization().create()
    # Helper function to create and promote CV to next environment
    repo_id = target_sat.api_factory.create_sync_custom_repo(
        product_name=product_name, org_id=org.id
    )
    target_sat.api_factory.cv_publish_promote(cv_name, env_name, repo_id, org.id)
    with session:
        session.organization.select(org_name=org.name)
        session.activationkey.create(
            {'name': name, 'lce': {env_name: True}, 'content_view': cv_name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        result = rhel_contenthost.register(org, None, name, target_sat)
        assert result.status == 0, f'Failed to register host: {result.stderr}'
        assert rhel_contenthost.subscribed
        session.activationkey.delete(name)
        assert session.activationkey.search(name)[0]['Name'] != name


@pytest.mark.rhel_ver_match('N-2')
def test_negative_usage_limit(
    session, module_org, target_sat, module_promoted_cv, module_lce, mod_content_hosts
):
    """Test that Usage limit actually limits usage

    :id: 9fe2d661-66f8-46a4-ae3f-0a9329494bdd

    :steps:
        1. Create Activation key
        2. Update Usage Limit to a finite number
        3. Register Systems to match the Usage Limit
        4. Attempt to register an other system after reaching the Usage
            Limit

    :expectedresults: System Registration fails. Appropriate error shown
    """
    name = gen_string('alpha')
    hosts_limit = '1'
    with target_sat.ui_session() as session:
        session.location.select(constants.DEFAULT_LOC)
        session.organization.select(module_org.name)
        session.activationkey.create(
            {'name': name, 'lce': {module_lce.name: True}, 'content_view': module_promoted_cv.name}
        )
        assert session.activationkey.search(name)[0]['Name'] == name
        session.activationkey.update_ak_host_limit(name, int(hosts_limit))
        ak = session.activationkey.read(name, widget_names='details')
        assert ak['details']['hosts_limit'] == hosts_limit

    vm1, vm2 = mod_content_hosts
    result = vm1.register(module_org, None, name, target_sat)
    assert result.status == 0, f'Failed to register host: {result.stderr}'
    assert vm1.subscribed
    result = vm2.register(module_org, None, name, target_sat)
    assert not vm2.subscribed
    assert result.status
    assert f'Max Hosts ({hosts_limit}) reached for activation key' in str(result.stderr)


@pytest.mark.no_containers
@pytest.mark.rhel_ver_match(r'^(?!.*fips).*$')  # all versions, excluding any 'fips'
@pytest.mark.upgrade
@pytest.mark.skipif((not settings.robottelo.repos_hosting_url), reason='Missing repos_hosting_url')
def test_positive_add_multiple_aks_to_system(session, module_org, rhel_contenthost, target_sat):
    """Check if multiple Activation keys can be attached to a system

    :id: 4d6b6b69-9d63-4180-af2e-a5d908f8adb7

    :expectedresults: Multiple Activation keys are attached to a system

    :parametrized: yes
    """
    key_1_name = gen_string('alpha')
    key_2_name = gen_string('alpha')
    cv_1_name = gen_string('alpha')
    cv_2_name = gen_string('alpha')
    env_1_name = gen_string('alpha')
    env_2_name = gen_string('alpha')
    product_1_name = gen_string('alpha')
    product_2_name = gen_string('alpha')
    repo_1_id = target_sat.api_factory.create_sync_custom_repo(
        org_id=module_org.id, product_name=product_1_name
    )
    target_sat.api_factory.cv_publish_promote(cv_1_name, env_1_name, repo_1_id, module_org.id)
    repo_2_id = target_sat.api_factory.create_sync_custom_repo(
        org_id=module_org.id, product_name=product_2_name, repo_url=settings.repos.yum_2.url
    )
    target_sat.api_factory.cv_publish_promote(cv_2_name, env_2_name, repo_2_id, module_org.id)
    with session:
        # Create 2 activation keys
        session.location.select(constants.DEFAULT_LOC)
        for key_name, env_name, cv_name, product_name in (
            (key_1_name, env_1_name, cv_1_name, product_1_name),
            (key_2_name, env_2_name, cv_2_name, product_2_name),
        ):
            session.activationkey.create(
                {'name': key_name, 'lce': {env_name: True}, 'content_view': cv_name}
            )
            assert session.activationkey.search(key_name)[0]['Name'] == key_name
            ak = session.activationkey.read(key_name, widget_names='repository sets')[
                'repository sets'
            ]['table'][0]
            assert product_name == ak['Product Name']
        # Create VM
        result = rhel_contenthost.register(module_org, None, [key_1_name, key_2_name], target_sat)
        assert result.status == 0, f'Failed to register host: {result.stderr}'
        assert rhel_contenthost.subscribed
        # Assert the content-host association with activation keys
        for key_name in [key_1_name, key_2_name]:
            ak = session.activationkey.read(key_name, widget_names='content_hosts')
            assert len(ak['content_hosts']['table']) == 1
            assert ak['content_hosts']['table'][0]['Name'] == rhel_contenthost.hostname


@pytest.mark.upgrade
@pytest.mark.skipif((not settings.robottelo.REPOS_HOSTING_URL), reason='Missing repos_hosting_url')
def test_positive_host_associations(session, target_sat):
    """Register few hosts with different activation keys and ensure proper
    data is reflected under Associations > Content Hosts tab

    :id: 111aa2af-caf4-4940-8e4b-5b071d488876

    :expectedresults: Only hosts, registered by specific AK are shown under
        Associations > Content Hosts tab

    :customerscenario: true

    :BZ: 1344033, 1372826, 1394388
    """
    org = target_sat.api.Organization().create()
    org_entities = target_sat.cli_factory.setup_org_for_a_custom_repo(
        {'url': settings.repos.yum_1.url, 'organization-id': org.id}
    )
    ak1 = target_sat.api.ActivationKey(id=org_entities['activationkey-id']).read()
    ak2 = target_sat.api.ActivationKey(
        content_view=org_entities['content-view-id'],
        environment=org_entities['lifecycle-environment-id'],
        organization=org.id,
    ).create()
    with Broker(nick='rhel7', host_class=ContentHost, _count=2) as hosts:
        vm1, vm2 = hosts
        result = vm1.register(org, None, ak1.name, target_sat)
        assert result.status == 0, f'Failed to register host: {result.stderr}'
        assert vm1.subscribed

        result = vm2.register(org, None, ak2.name, target_sat)
        assert result.status == 0, f'Failed to register host: {result.stderr}'
        assert vm2.subscribed
        with session:
            session.organization.select(org.name)
            session.location.select(constants.DEFAULT_LOC)
            ak1 = session.activationkey.read(ak1.name, widget_names='content_hosts')
            assert len(ak1['content_hosts']['table']) == 1
            assert ak1['content_hosts']['table'][0]['Name'] == vm1.hostname
            ak2 = session.activationkey.read(ak2.name, widget_names='content_hosts')
            assert len(ak2['content_hosts']['table']) == 1
            assert ak2['content_hosts']['table'][0]['Name'] == vm2.hostname


@pytest.mark.no_containers
@pytest.mark.skipif((not settings.robottelo.repos_hosting_url), reason='Missing repos_hosting_url')
@pytest.mark.rhel_ver_match([settings.content_host.default_rhel_version])
def test_positive_service_level_subscription_with_custom_product(
    session, function_sca_manifest_org, rhel_contenthost, target_sat
):
    """Subscribe a host to activation key with Premium service level and with
    custom product

    :id: 195a8049-860e-494d-b7f0-0794384194f7

    :customerscenario: true

    :steps:
        1. Create a product with custom repository synchronized
        2. Create and Publish a content view with the created repository
        3. Create an activation key and assign the created content view
        4. Set the activation service_level to Premium
        5. Register a host to activation key
        6. Assert product is listed under repository sets on the content host

    :expectedresults:
        1. The product is listed under repository sets on the content host

    :BZ: 1394357

    :parametrized: yes
    """
    org = function_sca_manifest_org
    entities_ids = target_sat.cli_factory.setup_org_for_a_custom_repo(
        {'url': settings.repos.yum_1.url, 'organization-id': org.id}
    )
    product = target_sat.api.Product(id=entities_ids['product-id']).read()
    activation_key = target_sat.api.ActivationKey(id=entities_ids['activationkey-id']).read()
    activation_key.service_level = 'Premium'
    activation_key = activation_key.update(['service_level'])

    result = rhel_contenthost.register(org, None, activation_key.name, target_sat)
    assert result.status == 0, f'Failed to register host: {result.stderr}'
    assert rhel_contenthost.subscribed
    with target_sat.ui_session() as session:
        session.organization.select(org.name)
        session.location.select(constants.DEFAULT_LOC)
        chost = session.host_new.get_details(
            rhel_contenthost.hostname, widget_names='content.repository_sets'
        )
        assert product.name == chost['content']['repository_sets']['table'][0]['Product']


def test_positive_new_ak_lce_cv_assignment(target_sat):
    """
    Test that newly created activation key which has Library and Default Org view
    assigned has it really assigned after the creation

    :id: 12e36a54-e5ba-49b9-b97a-f1827fc718a0

    :steps:
        1. Create new AK with Library and Default Org view assigned
        2. Check that created AK has Library and Default Org view assigned

    :expectedresults: Activation key has Library and Default Org view assigned after it is created

    :Verifies: SAT-28981
    """

    ak_name = gen_string('alpha')

    with target_sat.ui_session() as session:
        session.location.select(constants.DEFAULT_LOC)
        session.organization.select(constants.DEFAULT_ORG)
        session.activationkey.create(
            {'name': ak_name, 'lce': {'Library': True}, 'content_view': constants.DEFAULT_CV}
        )
        ak_values = session.activationkey.read(ak_name, widget_names='details')

        assert ak_values['details']['content_view'] == constants.DEFAULT_CV, (
            'Default Organization View is not assigned to newly created AK'
        )
        assert (
            ak_values['details']['lce']['Library']['Library'] == True  # noqa: E712, explicit comparison fits this case
        ), 'Library view is not assigned to newly created AK'
